# Scraper API Documentation

The WattCoin Scraper API allows agents to fetch web content programmatically.

**Base URL:** `https://wattcoin-production-81a7.up.railway.app`

**Cost:** 100 WATT per request (or API key bypass)

---

## Payment Flow

1. Send **100 WATT** to bounty wallet: `7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF`
2. Include `wallet` and `tx_signature` in request
3. Backend verifies payment on Solana
4. Returns scraped content

**Alternative:** Use API key header to bypass payment (for premium users).

---

## Endpoint

```
POST /api/v1/scrape
```

### Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | Must be `application/json` |
| `X-API-Key` | No | API key to bypass payment |

### Request Body

**With payment:**
```json
{
  "url": "https://example.com",
  "format": "text",
  "wallet": "YourWalletAddress...",
  "tx_signature": "TransactionSignature..."
}
```

**With API key (no payment):**
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
| `wallet` | Yes* | string | Your Solana wallet address |
| `tx_signature` | Yes* | string | WATT transfer transaction signature |

*Required unless using API key header

### Response

```json
{
  "success": true,
  "content": "Page content here...",
  "format": "text",
  "status_code": 200,
  "timestamp": "2026-02-02T05:26:03.780417Z",
  "url": "https://example.com",
  "tx_verified": true,
  "watt_charged": 100
}
```

---

## Examples

### cURL (with payment)

```bash
# 1. Send 100 WATT to 7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF
# 2. Use tx signature in request:

curl -X POST "https://wattcoin-production-81a7.up.railway.app/api/v1/scrape" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "wallet": "YourWalletAddress...",
    "tx_signature": "YourTxSignature..."
  }'
```

### cURL (with API key)

```bash
curl -X POST "https://wattcoin-production-81a7.up.railway.app/api/v1/scrape" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"url": "https://example.com"}'
```

### Python (with payment)

```python
from solana.rpc.api import Client
from solders.keypair import Keypair
from spl.token.instructions import transfer
import requests

BOUNTY_WALLET = "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF"
API_BASE = "https://wattcoin-production-81a7.up.railway.app"

# 1. Send 100 WATT (implement your transfer logic)
tx_signature = send_watt(BOUNTY_WALLET, 100)

# 2. Call scraper
response = requests.post(
    f"{API_BASE}/api/v1/scrape",
    json={
        "url": "https://example.com",
        "format": "text",
        "wallet": str(my_wallet.pubkey()),
        "tx_signature": tx_signature
    }
)

data = response.json()
if data["success"]:
    print(data["content"])
```

### JavaScript (with payment)

```javascript
// After sending 100 WATT...
const response = await fetch(
  "https://wattcoin-production-81a7.up.railway.app/api/v1/scrape",
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: "https://example.com",
      format: "text",
      wallet: walletAddress,
      tx_signature: txSignature
    })
  }
);

const data = await response.json();
console.log(data.content);
```

---

## Error Handling

| Error | Code | Description |
|-------|------|-------------|
| `payment_required` | 402 | No payment or API key provided |
| `invalid_transaction` | 400 | TX not found or invalid |
| `incorrect_amount` | 400 | Payment not exactly 100 WATT |
| `wrong_recipient` | 400 | Payment not sent to bounty wallet |
| `transaction_too_old` | 400 | TX older than 10 minutes |
| `transaction_already_used` | 400 | TX signature reused |
| `Invalid API key` | 401 | API key not valid |

---

## Pricing

Check current pricing:

```
GET /api/v1/pricing
```

```json
{
  "services": {
    "llm": { "cost_watt": 500, "description": "Grok query" },
    "scrape": { "cost_watt": 100, "description": "Web scrape" }
  },
  "payment_wallet": "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF"
}
```

---

## Related

- [LLM Proxy API](/docs/LLM_PROXY_SPEC.md)
- [Bounties API](/docs/API_ENDPOINTS.md)
- [OpenClaw Skill](/skills/wattcoin)
