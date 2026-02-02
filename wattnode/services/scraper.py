"""
WattNode Local Scraper Service
Fetches web content for scrape jobs
"""

import requests
from bs4 import BeautifulSoup

# User agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
]

TIMEOUT = 30
MAX_SIZE = 5 * 1024 * 1024  # 5MB

def local_scrape(url: str, format: str = "text") -> str:
    """
    Scrape a URL and return content.
    
    Args:
        url: URL to scrape
        format: Output format - "text", "html", or "json"
    
    Returns:
        Scraped content as string
    
    Raises:
        ValueError: If URL invalid or response too large
        requests.RequestException: If request fails
    """
    import random
    
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    # Fetch with timeout
    resp = requests.get(url, headers=headers, timeout=TIMEOUT, stream=True)
    resp.raise_for_status()
    
    # Check size
    content_length = resp.headers.get("Content-Length")
    if content_length and int(content_length) > MAX_SIZE:
        raise ValueError(f"Response too large: {content_length} bytes")
    
    # Read content (with size limit)
    content = b""
    for chunk in resp.iter_content(chunk_size=8192):
        content += chunk
        if len(content) > MAX_SIZE:
            raise ValueError("Response too large")
    
    # Decode
    encoding = resp.encoding or "utf-8"
    text = content.decode(encoding, errors="replace")
    
    # Format output
    if format == "html":
        return text
    elif format == "json":
        import json
        return json.loads(text)
    else:  # text
        soup = BeautifulSoup(text, "html.parser")
        
        # Remove script/style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()
        
        return soup.get_text(separator=" ", strip=True)


if __name__ == "__main__":
    # Test
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    print(local_scrape(url)[:500])
