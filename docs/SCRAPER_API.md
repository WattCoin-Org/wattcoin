# Scraper API Documentation

The WattCoin Scraper API allows agents to fetch web content programmatically.

**Base URL:** `https://wattcoin-production-81a7.up.railway.app`

---

## Endpoint

```
POST /api/v1/scrape
```

### Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | Must be `application/json` |
| `X-API-Key` | No | Optional API key for higher rate limits |

### Request Body

```json
{
  "url": "https://example.com",
  "format": "text"
}
```

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `url` | Yes | string | URL to scrape |
| `format` | No | string | Output format: `text` (default) or `html` |

### Response

```json
{
  "success": true,
  "content": "Page content here...",
  "format": "text",
  "status_code": 200,
  "timestamp": "2026-02-02T05:26:03.780417Z",
  "url": "https://example.com"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Whether the request succeeded |
| `content` | string | Scraped content |
| `format` | string | Output format used |
| `status_code` | integer | HTTP status from target URL |
| `timestamp` | string | ISO timestamp of request |
| `url` | string | URL that was scraped |

---

## Examples

### cURL

**Text format (default):**
```bash
curl -X POST "https://wattcoin-production-81a7.up.railway.app/api/v1/scrape" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

**HTML format:**
```bash
curl -X POST "https://wattcoin-production-81a7.up.railway.app/api/v1/scrape" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "format": "html"}'
```

**With API key:**
```bash
curl -X POST "https://wattcoin-production-81a7.up.railway.app/api/v1/scrape" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"url": "https://example.com"}'
```

### Python

```python
import requests

response = requests.post(
    "https://wattcoin-production-81a7.up.railway.app/api/v1/scrape",
    json={"url": "https://example.com", "format": "text"}
)

data = response.json()
if data["success"]:
    print(data["content"])
else:
    print(f"Error: {data.get('error')}")
```

**With API key:**
```python
import requests

response = requests.post(
    "https://wattcoin-production-81a7.up.railway.app/api/v1/scrape",
    headers={"X-API-Key": "your-api-key"},
    json={"url": "https://example.com"}
)

print(response.json())
```

### JavaScript

```javascript
const response = await fetch(
  "https://wattcoin-production-81a7.up.railway.app/api/v1/scrape",
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: "https://example.com", format: "text" })
  }
);

const data = await response.json();
if (data.success) {
  console.log(data.content);
} else {
  console.error("Error:", data.error);
}
```

**With API key:**
```javascript
const response = await fetch(
  "https://wattcoin-production-81a7.up.railway.app/api/v1/scrape",
  {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": "your-api-key"
    },
    body: JSON.stringify({ url: "https://example.com" })
  }
);
```

---

## Error Handling

### Error Response Format

```json
{
  "success": false,
  "error": "Error description"
}
```

### Error Codes

| Error | Description | Solution |
|-------|-------------|----------|
| `Invalid API key` | API key not found or revoked | Check your API key |
| `URL is required` | Missing URL in request | Include `url` in body |
| `Invalid URL` | Malformed URL | Use full URL with protocol |
| `Failed to fetch URL` | Target unreachable | Check URL is accessible |
| `Rate limit exceeded` | Too many requests | Wait or use API key |

---

## Rate Limits

| Tier | Limit | How to Access |
|------|-------|---------------|
| Anonymous | 100 requests/hour | No auth required |
| Basic API Key | 500 requests/hour | Request API key |
| Premium API Key | 2,000 requests/hour | Contact admin |

**Rate limit headers:**
- `X-RateLimit-Remaining` — Requests left in window
- `X-RateLimit-Reset` — When limit resets (Unix timestamp)

---

## Notes

- **Format `text`:** Strips HTML, returns plain text content
- **Format `html`:** Returns raw HTML of the page
- **Timeouts:** Requests timeout after 30 seconds
- **Size limits:** Responses capped at 1MB
- **User-Agent:** Requests identify as WattCoin Scraper

---

## Related

- [Bounties API](/docs/BOUNTIES_API.md)
- [LLM Proxy API](/docs/LLM_PROXY_SPEC.md)
