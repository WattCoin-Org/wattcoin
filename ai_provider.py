"""
AI Provider Helper — vendor-neutral wrapper for AI API calls.
Auto-detects auth headers and response format from API URL.
No vendor-specific names in this module.

Env vars (set in Railway):
  AI_REVIEW_API_KEY   - API key for the AI provider
  AI_REVIEW_API_URL   - Full endpoint URL
  AI_REVIEW_MODEL     - Model identifier
"""

import os
import json
import requests

AI_API_KEY = os.getenv("AI_REVIEW_API_KEY", "")
AI_API_URL = os.getenv("AI_REVIEW_API_URL", "")
AI_MODEL = os.getenv("AI_REVIEW_MODEL", "")
AI_AUTH_STYLE = os.getenv("AI_REVIEW_AUTH_STYLE", "bearer")  # "bearer" or "header"
AI_EXTRA_HEADERS = os.getenv("AI_REVIEW_EXTRA_HEADERS", "")  # JSON string of extra headers


def _build_headers():
    """Build auth headers based on configured auth style."""
    headers = {"Content-Type": "application/json"}

    if AI_AUTH_STYLE == "header":
        # Auth via dedicated key header
        headers["x-api-key"] = AI_API_KEY
    else:
        # Auth via bearer token (default)
        headers["Authorization"] = f"Bearer {AI_API_KEY}"

    # Add any extra provider-specific headers from env
    if AI_EXTRA_HEADERS:
        try:
            extras = json.loads(AI_EXTRA_HEADERS)
            headers.update(extras)
        except json.JSONDecodeError:
            pass

    return headers


def _parse_response(resp_json):
    """Extract text from AI response based on format."""
    # Style A: {"content": [{"text": "..."}]}
    if "content" in resp_json and isinstance(resp_json["content"], list):
        return resp_json["content"][0].get("text", "")

    # Style B: {"choices": [{"message": {"content": "..."}}]}
    if "choices" in resp_json:
        return resp_json["choices"][0]["message"]["content"]

    return ""


def call_ai(prompt, temperature=0.3, max_tokens=1000, timeout=60):
    """
    Send prompt to configured AI provider.
    Returns: (response_text, error)
    """
    if not AI_API_KEY or not AI_API_URL or not AI_MODEL:
        return None, "AI API not configured (missing key, URL, or model)"

    try:
        payload = {
            "model": AI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        resp = requests.post(
            AI_API_URL,
            headers=_build_headers(),
            json=payload,
            timeout=timeout,
        )

        if resp.status_code != 200:
            return None, f"AI API error: {resp.status_code} - {resp.text[:200]}"

        text = _parse_response(resp.json()).strip()
        if not text:
            return None, "AI returned empty response"

        return text, None

    except requests.Timeout:
        return None, "AI API timeout"
    except Exception as e:
        return None, f"AI API error: {e}"

