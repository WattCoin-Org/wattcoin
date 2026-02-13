"""
WattNode Inference Service
Supports two backends:
  - Ollama (local, lightweight, CPU-friendly)
  - Distributed (P2P swarm via WSI gateway, GPU recommended)

Backend selection via config or environment:
  INFERENCE_BACKEND=auto|ollama|distributed (default: auto)
  Auto: tries distributed gateway first, falls back to Ollama.

Version: 2.0.0
"""

import os
import requests
import logging

logger = logging.getLogger("wattnode.inference")

# =============================================================================
# CONFIG
# =============================================================================

INFERENCE_BACKEND = os.environ.get("INFERENCE_BACKEND", "auto")  # auto|ollama|distributed

# Ollama
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama2")
OLLAMA_TIMEOUT = 120

# Distributed inference gateway (runs on seed node alongside inference server)
DISTRIBUTED_GATEWAY_URL = os.environ.get("DISTRIBUTED_GATEWAY_URL", "http://localhost:8090")
DISTRIBUTED_GATEWAY_KEY = os.environ.get("WSI_GATEWAY_KEY", "")
DISTRIBUTED_MODEL = os.environ.get("DISTRIBUTED_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct")
DISTRIBUTED_TIMEOUT = 180  # Distributed inference can be slower


# =============================================================================
# OLLAMA BACKEND
# =============================================================================

class OllamaBackend:
    """Local inference via Ollama."""

    def __init__(self, base_url=None, default_model=None):
        self.base_url = base_url or OLLAMA_URL
        self.default_model = default_model or OLLAMA_MODEL

    def is_available(self):
        """Check if Ollama is running."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def list_models(self):
        """List available Ollama models."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=10)
            resp.raise_for_status()
            return [m.get("name") for m in resp.json().get("models", [])]
        except Exception:
            return []

    def generate(self, prompt, model=None, max_tokens=500, temperature=0.7):
        """Run inference through Ollama."""
        model = model or self.default_model
        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature
                    }
                },
                timeout=OLLAMA_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "success": True,
                "response": data.get("response", ""),
                "model": model,
                "backend": "ollama",
                "eval_count": data.get("eval_count", 0)
            }
        except requests.ConnectionError:
            return {"success": False, "error": f"Cannot connect to Ollama at {self.base_url}"}
        except requests.Timeout:
            return {"success": False, "error": f"Ollama timed out after {OLLAMA_TIMEOUT}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# =============================================================================
# DISTRIBUTED BACKEND
# =============================================================================

class DistributedBackend:
    """Distributed inference via WSI gateway (HTTP wrapper around inference client)."""

    def __init__(self, gateway_url=None, gateway_key=None, default_model=None):
        self.gateway_url = gateway_url or DISTRIBUTED_GATEWAY_URL
        self.gateway_key = gateway_key or DISTRIBUTED_GATEWAY_KEY
        self.default_model = default_model or DISTRIBUTED_MODEL

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.gateway_key:
            headers["Authorization"] = f"Bearer {self.gateway_key}"
        return headers

    def is_available(self):
        """Check if distributed gateway is reachable."""
        try:
            resp = requests.get(
                f"{self.gateway_url}/health",
                headers=self._headers(),
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("status") == "ok"
            return False
        except Exception:
            return False

    def list_models(self):
        """List models available on the distributed swarm."""
        try:
            resp = requests.get(
                f"{self.gateway_url}/models",
                headers=self._headers(),
                timeout=10
            )
            resp.raise_for_status()
            return resp.json().get("models", [])
        except Exception:
            return []

    def get_swarm_status(self):
        """Get swarm health info (nodes, blocks, capacity)."""
        try:
            resp = requests.get(
                f"{self.gateway_url}/swarm",
                headers=self._headers(),
                timeout=10
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def generate(self, prompt, model=None, max_tokens=500, temperature=0.7):
        """Run inference through the distributed swarm."""
        model = model or self.default_model
        try:
            resp = requests.post(
                f"{self.gateway_url}/inference",
                headers=self._headers(),
                json={
                    "prompt": prompt,
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature
                },
                timeout=DISTRIBUTED_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("success"):
                return {
                    "success": True,
                    "response": data.get("response", ""),
                    "model": data.get("model", model),
                    "backend": "distributed",
                    "tokens_generated": data.get("tokens_generated", 0),
                    "generation_time": data.get("generation_time", 0),
                    "node_id": data.get("node_id", ""),
                    "query_id": data.get("query_id", "")
                }
            else:
                return {"success": False, "error": data.get("error", "Unknown gateway error")}

        except requests.ConnectionError:
            return {"success": False, "error": f"Cannot connect to distributed gateway at {self.gateway_url}"}
        except requests.Timeout:
            return {"success": False, "error": f"Distributed inference timed out after {DISTRIBUTED_TIMEOUT}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# =============================================================================
# UNIFIED INTERFACE
# =============================================================================

def get_backend(backend=None):
    """Get the configured inference backend instance."""
    backend = backend or INFERENCE_BACKEND
    if backend == "ollama":
        return OllamaBackend()
    elif backend in ("distributed",):
        return DistributedBackend()
    else:  # auto
        return None  # Handled by generate()


def generate(prompt, model=None, max_tokens=500, temperature=0.7, backend=None):
    """
    Run inference through the best available backend.

    Auto mode: tries distributed gateway first, falls back to Ollama.
    Returns dict with 'success', 'response', 'backend', etc.
    """
    backend_name = backend or INFERENCE_BACKEND

    if backend_name in ("distributed",):
        return DistributedBackend().generate(prompt, model=model, max_tokens=max_tokens, temperature=temperature)

    if backend_name == "ollama":
        return OllamaBackend().generate(prompt, model=model, max_tokens=max_tokens, temperature=temperature)

    # Auto: try distributed first, fall back to Ollama
    distributed = DistributedBackend()
    if distributed.is_available():
        logger.info("Using distributed backend (gateway reachable)")
        result = distributed.generate(prompt, model=model, max_tokens=max_tokens, temperature=temperature)
        if result.get("success"):
            return result
        logger.warning(f"Distributed backend failed: {result.get('error')} — falling back to Ollama")

    ollama = OllamaBackend()
    if ollama.is_available():
        logger.info("Using Ollama backend (local)")
        return ollama.generate(prompt, model=model, max_tokens=max_tokens, temperature=temperature)

    return {"success": False, "error": "No inference backend available (distributed gateway down, Ollama not running)"}


def check_available():
    """Check if any inference backend is available."""
    if INFERENCE_BACKEND in ("distributed",):
        return DistributedBackend().is_available()
    if INFERENCE_BACKEND == "ollama":
        return OllamaBackend().is_available()
    # Auto: either works
    return DistributedBackend().is_available() or OllamaBackend().is_available()


# =============================================================================
# LEGACY COMPAT — used by wattnode.py execute_job()
# =============================================================================

def local_inference(prompt, model=None, ollama_url=None):
    """
    Legacy wrapper — maintains backward compatibility with existing WattNode job handler.
    Returns response string or None.
    """
    result = generate(prompt, model=model)
    if result.get("success"):
        return result["response"]
    return None


def check_ollama_available(ollama_url=None):
    """Legacy compat — check Ollama specifically."""
    return OllamaBackend(base_url=ollama_url).is_available()


def list_models(ollama_url=None):
    """Legacy compat — list Ollama models."""
    return OllamaBackend(base_url=ollama_url).list_models()


# =============================================================================
# CLI TEST
# =============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    print(f"Inference backend: {INFERENCE_BACKEND}")
    print()

    # Check distributed
    distributed = DistributedBackend()
    print(f"Distributed gateway ({dist.gateway_url}):")
    if distributed.is_available():
        print("  ✅ Reachable")
        models = dist.list_models()
        print(f"  Models: {models}")
        swarm = dist.get_swarm_status()
        if swarm:
            print(f"  Swarm: {swarm.get('total_nodes', '?')} nodes, {swarm.get('total_blocks', '?')} blocks")
    else:
        print("  ❌ Not available")

    print()

    # Check Ollama
    ollama = OllamaBackend()
    print(f"Ollama ({ollama.base_url}):")
    if ollama.is_available():
        print("  ✅ Running")
        models = ollama.list_models()
        print(f"  Models: {models}")
    else:
        print("  ❌ Not available")

    print()

    # Test inference if requested
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        print(f"Prompt: {prompt}")
        print(f"Running via '{INFERENCE_BACKEND}' backend...")
        result = generate(prompt)
        if result.get("success"):
            print(f"Backend: {result['backend']}")
            print(f"Response: {result['response']}")
        else:
            print(f"Error: {result['error']}")

