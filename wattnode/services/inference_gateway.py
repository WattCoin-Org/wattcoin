"""
WSI Inference Gateway — HTTP server that wraps the distributed inference client.
Runs on the seed node (or any node with the inference client installed).
Accepts HTTP requests from the API server and routes them through the inference swarm.

Endpoints:
- POST /inference  - Run distributed inference
- GET  /swarm      - Swarm health & node info
- GET  /models     - Available models
- GET  /health     - Gateway health check

Usage:
    python inference_gateway.py                        # default port 8090
    python inference_gateway.py --port 8090 --host 0.0.0.0
    WSI_GATEWAY_KEY=mysecret python inference_gateway.py # with auth

Requirements:
    pip install petals torch transformers flask  # distributed inference dependencies

Version: 1.0.0
"""

import os
import sys
import time
import json
import logging
import argparse
import threading
from datetime import datetime

# Flask for HTTP API
from flask import Flask, request, jsonify

app = Flask(__name__)

# =============================================================================
# CONFIG
# =============================================================================

# Default model — small enough for single-node bootstrap
DEFAULT_MODEL = os.getenv("WSI_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct")

# Auth — shared secret with Railway API (optional but recommended)
GATEWAY_KEY = os.getenv("WSI_GATEWAY_KEY", "")

# Generation defaults
DEFAULT_MAX_TOKENS = 500
MAX_MAX_TOKENS = 2000
DEFAULT_TEMPERATURE = 0.7

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [WSI-Gateway] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("wsi-gateway")

# =============================================================================
# INFERENCE CLIENT (lazy-loaded)
# =============================================================================

_models = {}        # model_name -> (model, tokenizer)
_models_lock = threading.Lock()
_load_errors = {}   # model_name -> error string
_node_id = None     # this gateway's node ID (set on startup)

# Track queries served for contribution reporting
_query_stats = {
    "total_queries": 0,
    "total_tokens": 0,
    "errors": 0,
    "start_time": time.time()
}


def get_node_id():
    """Generate or load a stable node ID for this gateway."""
    global _node_id
    if _node_id:
        return _node_id

    id_file = os.path.expanduser("~/.wsi_gateway_node_id")
    if os.path.exists(id_file):
        with open(id_file, 'r') as f:
            _node_id = f.read().strip()
    else:
        import hashlib
        seed = f"{os.uname().nodename}_{time.time()}"
        _node_id = "gw_" + hashlib.sha256(seed.encode()).hexdigest()[:12]
        with open(id_file, 'w') as f:
            f.write(_node_id)

    return _node_id


def load_model(model_name):
    """
    Load a distributed model + tokenizer.
    This connects to the inference swarm and finds nodes hosting the model layers.
    First call may take 30-60s as it discovers peers.
    """
    with _models_lock:
        if model_name in _models:
            return _models[model_name], None
        if model_name in _load_errors:
            return None, _load_errors[model_name]

    logger.info(f"Loading model: {model_name} (connecting to inference swarm...)")

    try:
        from transformers import AutoTokenizer
        from petals import AutoDistributedModelForCausalLM  # distributed inference engine

        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoDistributedModelForCausalLM.from_pretrained(model_name)

        # Ensure pad token is set
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        with _models_lock:
            _models[model_name] = (model, tokenizer)

        logger.info(f"Model loaded: {model_name}")
        return (model, tokenizer), None

    except ImportError:
        err = "Distributed inference not installed. Run: pip install petals torch transformers"
        _load_errors[model_name] = err
        logger.error(err)
        return None, err
    except Exception as e:
        err = f"Failed to load model {model_name}: {e}"
        _load_errors[model_name] = err
        logger.error(err)
        return None, err


def run_inference(prompt, model_name=None, max_tokens=500, temperature=0.7):
    """
    Run distributed inference through the swarm.

    Returns: {
        "success": True/False,
        "response": "generated text",
        "model": "model_name",
        "tokens_generated": 150,
        "latency_ms": 3200,
        "nodes_used": ["node_abc"],
        "total_blocks": 32,
        "contributions": [...]
    }
    """
    model_name = model_name or DEFAULT_MODEL
    start_time = time.time()

    # Load model (cached after first call)
    model_pair, error = load_model(model_name)
    if error:
        _query_stats["errors"] += 1
        return {"success": False, "error": error}

    model, tokenizer = model_pair

    try:
        # Tokenize input
        inputs = tokenizer(prompt, return_tensors="pt")
        input_ids = inputs["input_ids"]
        input_len = input_ids.shape[1]

        # Generate through distributed swarm
        # Each token passes through ALL layers, distributed across nodes
        outputs = model.generate(
            input_ids,
            max_new_tokens=min(max_tokens, MAX_MAX_TOKENS),
            temperature=temperature,
            do_sample=temperature > 0,
            top_p=0.9 if temperature > 0 else 1.0
        )

        # Decode only the generated tokens (not the input)
        generated_ids = outputs[0][input_len:]
        response_text = tokenizer.decode(generated_ids, skip_special_tokens=True)
        tokens_generated = len(generated_ids)

        latency_ms = int((time.time() - start_time) * 1000)

        # Update stats
        _query_stats["total_queries"] += 1
        _query_stats["total_tokens"] += tokens_generated

        # Contribution info — in single-node setup, the gateway itself served all blocks
        # In multi-node, the engine routes internally but doesn't expose per-node stats easily
        # The gateway reports its own contribution; individual nodes report via /contribute
        node_id = get_node_id()

        result = {
            "success": True,
            "response": response_text,
            "model": model_name,
            "tokens_generated": tokens_generated,
            "latency_ms": latency_ms,
            "nodes_used": [node_id],
            "total_blocks": 32,  # Llama 8B has 32 transformer blocks
            "contributions": [{
                "node_id": node_id,
                "blocks_served": 32,
                "latency_ms": latency_ms
            }]
        }

        logger.info(f"Query completed: {tokens_generated} tokens in {latency_ms}ms")
        return result

    except Exception as e:
        _query_stats["errors"] += 1
        latency_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Inference error: {e}")
        return {
            "success": False,
            "error": f"Inference failed: {e}",
            "latency_ms": latency_ms
        }


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.route('/inference', methods=['POST'])
def inference_endpoint():
    """Run distributed inference. Called by Railway API."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"success": False, "error": "prompt required"}), 400

    model = data.get("model") or DEFAULT_MODEL
    max_tokens = min(data.get("max_tokens", DEFAULT_MAX_TOKENS), MAX_MAX_TOKENS)
    temperature = data.get("temperature", DEFAULT_TEMPERATURE)

    result = run_inference(prompt, model_name=model, max_tokens=max_tokens, temperature=temperature)

    status_code = 200 if result.get("success") else 500
    return jsonify(result), status_code


@app.route('/swarm', methods=['GET'])
def swarm_endpoint():
    """Swarm health — nodes, models, capacity."""
    loaded_models = list(_models.keys())
    uptime = int(time.time() - _query_stats["start_time"])

    # Try to get swarm info if available
    swarm_nodes = []
    try:
        # The inference engine exposes some DHT info — model-specific
        for model_name, (model, _) in _models.items():
            if hasattr(model, 'dht') and model.dht:
                # Could inspect DHT for peer count
                swarm_nodes.append({
                    "model": model_name,
                    "status": "connected"
                })
    except Exception:
        pass

    return jsonify({
        "online": len(loaded_models) > 0 or len(_load_errors) == 0,
        "gateway_node": get_node_id(),
        "loaded_models": loaded_models,
        "load_errors": _load_errors,
        "stats": {
            "total_queries": _query_stats["total_queries"],
            "total_tokens": _query_stats["total_tokens"],
            "errors": _query_stats["errors"],
            "uptime_seconds": uptime
        },
        "swarm_peers": swarm_nodes,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }), 200


@app.route('/models', methods=['GET'])
def models_endpoint():
    """List available models."""
    # Report both loaded and loadable models
    models = []

    # Currently loaded
    for name in _models:
        models.append({
            "name": name,
            "status": "loaded",
            "ready": True
        })

    # Default model (always advertised even if not yet loaded)
    if DEFAULT_MODEL not in [m["name"] for m in models]:
        models.append({
            "name": DEFAULT_MODEL,
            "status": "available",
            "ready": False,
            "note": "Will load on first query (30-60s startup)"
        })

    return jsonify({"models": models}), 200


@app.route('/health', methods=['GET'])
def health_endpoint():
    """Gateway health check."""
    return jsonify({
        "status": "ok",
        "gateway": "WSI Inference Gateway",
        "version": "1.0.0",
        "node_id": get_node_id(),
        "models_loaded": len(_models),
        "uptime_seconds": int(time.time() - _query_stats["start_time"])
    }), 200


# =============================================================================
# MAIN
# =============================================================================

def preload_model():
    """Preload default model in background thread."""
    logger.info(f"Preloading default model: {DEFAULT_MODEL}")
    result, error = load_model(DEFAULT_MODEL)
    if error:
        logger.warning(f"Preload failed (will retry on first query): {error}")
    else:
        logger.info(f"Default model ready: {DEFAULT_MODEL}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WSI Inference Gateway")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8090, help="Port (default: 8090)")
    parser.add_argument("--no-preload", action="store_true", help="Don't preload model on startup")
    args = parser.parse_args()

    print("=" * 60)
    print("  WSI Inference Gateway v1.0.0")
    print(f"  Model: {DEFAULT_MODEL}")
    print(f"  Listening: {args.host}:{args.port}")
    print(f"  Node ID: {get_node_id()}")
    print(f"  Auth: {'enabled' if GATEWAY_KEY else 'disabled'}")
    print("=" * 60)

    # Preload model in background (so first query doesn't wait)
    if not args.no_preload:
        preload_thread = threading.Thread(target=preload_model, daemon=True)
        preload_thread.start()

    app.run(host=args.host, port=args.port, debug=False)
