"""
WattNode Local Inference Service
Runs LLM inference via Ollama
"""

import requests
import os

# Default Ollama settings
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama2")
TIMEOUT = 120  # Inference can be slow

def local_inference(prompt: str, model: str = None, ollama_url: str = None) -> str:
    """
    Run inference using local Ollama instance.
    
    Args:
        prompt: The prompt/question to send
        model: Model name (default: llama2)
        ollama_url: Ollama API URL (default: http://localhost:11434)
    
    Returns:
        Model response as string
    
    Raises:
        requests.RequestException: If Ollama not available
        ValueError: If response invalid
    """
    url = ollama_url or OLLAMA_URL
    model = model or DEFAULT_MODEL
    
    endpoint = f"{url}/api/generate"
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    
    try:
        resp = requests.post(endpoint, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        
        data = resp.json()
        return data.get("response", "")
    
    except requests.ConnectionError:
        raise ValueError(f"Cannot connect to Ollama at {url}. Is it running?")
    except requests.Timeout:
        raise ValueError(f"Ollama request timed out after {TIMEOUT}s")


def check_ollama_available(ollama_url: str = None) -> bool:
    """Check if Ollama is running and accessible"""
    url = ollama_url or OLLAMA_URL
    try:
        resp = requests.get(f"{url}/api/tags", timeout=5)
        return resp.status_code == 200
    except:
        return False


def list_models(ollama_url: str = None) -> list:
    """List available models in Ollama"""
    url = ollama_url or OLLAMA_URL
    try:
        resp = requests.get(f"{url}/api/tags", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return [m.get("name") for m in data.get("models", [])]
    except:
        return []


if __name__ == "__main__":
    # Test
    import sys
    
    print(f"Checking Ollama at {OLLAMA_URL}...")
    if check_ollama_available():
        print("✅ Ollama is running")
        models = list_models()
        print(f"   Available models: {models}")
        
        if len(sys.argv) > 1:
            prompt = " ".join(sys.argv[1:])
            print(f"\nPrompt: {prompt}")
            print(f"Response: {local_inference(prompt)}")
    else:
        print("❌ Ollama not available")
        print("   Install: https://ollama.ai")
        print("   Run: ollama serve")
