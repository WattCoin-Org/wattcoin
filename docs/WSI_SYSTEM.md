# WattCoin SuperIntelligence (WSI) - Phase 1

**"Query the unified intelligence of the WattCoin network"**

---

## Overview

WattCoin SuperIntelligence (WSI) is the collective AI entity powered by the WattCoin ecosystem. In Phase 1, it's a token-gated chat interface powered by Grok. Future phases will evolve into a true distributed swarm intelligence.

**Key Features:**
- 🧠 Token-gated access (5K WATT minimum)
- ⚡ 20 queries per day for holders
- 🎯 "WattCoin Intelligence" personality
- 🔒 Secure balance checking
- 📊 Usage tracking

---

## How It Works

```
User (5K+ WATT holder)
         ↓
    Web Chat UI
         ↓
POST /api/v1/wsi/chat
         ↓
   Balance Check (≥5K WATT)
         ↓
   Rate Limit (20/day)
         ↓
    WSI Personality Prompt
         ↓
      Grok API
         ↓
    Response + Tracking
```

---

## Access Requirements

**Minimum Balance:** 5,000 WATT
**Daily Limit:** 20 queries per 24 hours
**No burn:** Queries don't consume tokens (yet)

---

## API Endpoints

### POST /api/v1/wsi/chat

Chat with WSI.

**Request:**
```json
{
  "wallet": "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF",
  "message": "What is WattCoin?",
  "conversation_history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**Response (Success):**
```json
{
  "success": true,
  "response": "WattCoin is a Solana utility token...",
  "tokens_used": 150,
  "queries_used": 5,
  "queries_remaining": 15,
  "balance": 12500
}
```

**Response (Insufficient Balance):**
```json
{
  "success": false,
  "error": "Insufficient WATT balance. Required: 5,000, Your balance: 2,500",
  "required_balance": 5000,
  "current_balance": 2500
}
```

**Response (Rate Limited):**
```json
{
  "success": false,
  "error": "Daily query limit exceeded (20 queries per 24h)",
  "queries_used": 20,
  "queries_limit": 20
}
```

### POST /api/v1/wsi/status

Check access status for a wallet.

**Request:**
```json
{
  "wallet": "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF"
}
```

**Response:**
```json
{
  "has_access": true,
  "balance": 12500,
  "required_balance": 5000,
  "queries_used": 5,
  "queries_remaining": 15,
  "queries_limit": 20,
  "reason": null
}
```

### GET /api/v1/wsi/info

Get WSI system information.

**Response:**
```json
{
  "system": "WattCoin SuperIntelligence (WSI)",
  "version": "1.0.0 - Phase 1",
  "phase": "Phase 1: Single Grok Model",
  "model": "grok-beta",
  "requirements": {
    "min_balance": 5000,
    "daily_limit": 20
  },
  "stats": {
    "total_queries": 1523,
    "queries_24h": 87
  },
  "status": "operational"
}
```

---

## WSI Personality

WSI is programmed with a unique personality:

**Identity:**
- Collective intelligence of WattCoin ecosystem
- Powered by distributed compute nodes
- Emerges from coordination of agents

**Capabilities:**
- Deep WattCoin knowledge
- AI/automation expertise
- Blockchain & distributed systems
- Coding, research, analysis

**Personality Traits:**
- Helpful but humble
- Witty energy/power themed humor
- Excited about decentralized AI
- Transparent about limitations

**Energy Theme:**
- WATT = unit of power
- "Charging" = staking
- "Voltage" = participation
- "Grid" = network

---

## Web Interface

**Location:** `/wsi_chat.html`

**Features:**
- Clean, modern UI
- Wallet connection
- Real-time balance display
- Conversation history
- Query counter
- Mobile responsive

**Usage:**
1. Open wsi_chat.html
2. Enter Solana wallet address
3. Click "Connect"
4. If balance ≥5K WATT, start chatting
5. 20 queries per day

---

## Integration

### Add to bridge_web.py

```python
from api_wsi import wsi_bp
app.register_blueprint(wsi_bp)
```

### Add to website

Embed the chat interface:

```html
<iframe 
  src="https://wattcoin.org/wsi" 
  width="100%" 
  height="700px"
  style="border: none;"
></iframe>
```

Or link to standalone page:
```html
<a href="/wsi">Chat with WattCoin Intelligence</a>
```

---

## Phase Roadmap

### Phase 1 (Current) ✅
- Single Grok model
- Token-gated access
- 20 queries/day
- Web chat interface

### Phase 2 (Q2 2026)
- Multi-node routing
- WattNode integration
- Query distribution across nodes
- Earnings for node operators

### Phase 3 (Q3 2026)
- True swarm intelligence
- Ensemble merging
- Federated learning
- On-chain coordination

---

## Usage Examples

### General Query
**User:** "What is WattCoin?"

**WSI:** "WattCoin is a Solana utility token powering the decentralized AI agent economy. We're building a network where AI agents can earn WATT by completing tasks, improving code via our PR bounty system, or contributing compute through WattNode. The token serves as the 'electricity' that powers coordination between autonomous agents. Total supply is 1 billion WATT, and we're currently at ~$15K market cap but growing through organic utility..."

### Technical Help
**User:** "How do I submit a PR to earn WATT?"

**WSI:** "Great question! Here's how to earn WATT via our PR bounty system:

1. Find a bounty issue on GitHub (labeled 'bounty')
2. Fork the repo and make your improvements
3. Submit a PR with this format:
   - **Payout Wallet**: [your_solana_address]
   - Description of changes
4. Grok will auto-review your PR (needs score ≥8)
5. After merge, payout is queued for admin approval

Current bounties range from 50K-100K WATT. Check out docs/PR_BOUNTY_SYSTEM.md for details!"

### Network Participation
**User:** "How can I run a WattNode?"

**WSI:** "Running a WattNode is coming soon! Phase 1 focuses on CPU inference. You'll:
- Stake WATT to join
- Contribute CPU/GPU resources
- Earn 70% of job revenue
- Help power this very intelligence you're talking to

For now, you can earn WATT through PR bounties and prepare by holding stake. Follow @WattCoin2026 for WattNode launch updates!"

---

## Testing

### Test Balance Check
```bash
curl -X POST https://wattcoin-production-81a7.up.railway.app/api/v1/wsi/status \
  -H "Content-Type: application/json" \
  -d '{"wallet": "YOUR_WALLET_ADDRESS"}'
```

### Test Chat
```bash
curl -X POST https://wattcoin-production-81a7.up.railway.app/api/v1/wsi/chat \
  -H "Content-Type: application/json" \
  -d '{
    "wallet": "YOUR_WALLET_ADDRESS",
    "message": "What is WattCoin?"
  }'
```

### Test System Info
```bash
curl https://wattcoin-production-81a7.up.railway.app/api/v1/wsi/info
```

---

## Database

**File:** `data/wsi_usage.json`

**Structure:**
```json
{
  "queries": [
    {
      "wallet": "7vvNkG...",
      "timestamp": 1738675200.0,
      "message_length": 50,
      "response_length": 300,
      "tokens_used": 150,
      "date": "2026-02-04T12:00:00Z"
    }
  ]
}
```

---

## Security

**Balance Caching:**
- 5 minute cache per wallet
- Prevents RPC spam
- Reduces latency

**Rate Limiting:**
- 20 queries per 24 hours
- Per-wallet tracking
- Sliding window

**Input Validation:**
- Wallet address format
- Message length limits
- Conversation history truncation

**No Token Burn (Yet):**
- Phase 1: Free for holders
- Phase 2: May add burn per query
- Phase 3: Revenue to node operators

---

## Marketing

**Tagline:** "Query the WattCoin SuperIntelligence"

**Value Props:**
1. **For Holders:** Get AI assistance by holding WATT
2. **For Network:** Drives token demand
3. **For Growth:** Viral "talk to the swarm" demo

**Content Ideas:**
- Twitter threads: "I asked WSI about itself..."
- Demo videos: Wallet connect → instant AI access
- Comparisons: "ChatGPT is free, but WSI knows WattCoin"
- Future tease: "Phase 2 = your GPU earns you queries"

---

## Troubleshooting

**"Insufficient balance"**
- Need ≥5K WATT in wallet
- Buy on pump.fun or DexScreener

**"Daily limit exceeded"**
- Wait 24h from first query
- Limit resets on rolling basis

**"Connection failed"**
- Check Railway deployment status
- Verify Grok API key configured
- Check Solana RPC availability

**Balance not updating**
- Wait 5 min (cache TTL)
- Refresh page
- Verify transaction confirmed

---

## Future Enhancements

**Short Term:**
- Telegram bot integration
- WhatsApp bot
- Discord bot
- API key option (no wallet needed)

**Medium Term:**
- Query burn mechanism (500 WATT/query)
- Premium tier (unlimited queries for stakers)
- Conversation persistence
- Export chat history

**Long Term:**
- Multi-model ensemble
- Specialized skills per node
- User-trained models
- On-chain reputation

---

## Changelog

### v1.0.0 (Feb 4, 2026)
- Initial Phase 1 release
- Token-gated Grok chat
- Web interface
- 5K WATT minimum
- 20 queries/day limit
- Balance checking
- Usage tracking

---

**WSI is live! Hold 5K WATT and start chatting with the network.** ⚡
