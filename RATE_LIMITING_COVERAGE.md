# Rate Limiting Coverage (Bounty #88)

## Endpoints Protected: 13 total

### Public API Endpoints (6)
| Endpoint | Method | Rate Limit | Reason |
|----------|--------|------------|--------|
| `/api/v1/scrape` | POST | 60/min | Scraping is expensive |
| `/api/v1/pricing` | GET | 60/min | Public info |
| `/api/v1/bounty-stats` | GET | 60/min | Public stats |
| `/proxy` | POST | 60/min | Proxy egress |
| `/proxy/moltbook` | POST | 60/min | Moltbook API calls |

### LLM/AI Endpoints (1) - Higher Security
| Endpoint | Method | Rate Limit | Reason |
|----------|--------|------------|--------|
| `/api/v1/llm` | POST | 10/min | LLM calls cost tokens |

### UI Endpoints (6)
| Endpoint | Method | Rate Limit | Reason |
|----------|--------|------------|--------|
| `/` | GET | 60/min | Homepage |
| `/query` | POST | 60/min | AI queries |
| `/send-to-claude` | POST | 60/min | Message routing |
| `/skip-claude` | POST | 60/min | UI action |
| `/send-to-ai` | POST | 60/min | AI interaction |
| `/clear` | GET | 60/min | Clear history |

## Endpoints Excluded
| Endpoint | Method | Reason |
|----------|--------|--------|
| `/health` | GET | Monitoring - should never be rate limited |

## Implementation Details
- Default: `PUBLIC_RATE_LIMIT=60 per minute`
- Configurable via environment variable
- Uses Flask-Limiter with Redis/memory storage
- Headers: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
- 429 response with Retry-After header

## Test Coverage
- `tests/test_rate_limiting.py` verifies:
  - All public endpoints have rate limit
  - Env var is used
  - 429 response triggered
