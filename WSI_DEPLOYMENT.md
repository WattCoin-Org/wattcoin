# WSI Phase 1 - Deployment Checklist

**Feature:** WattCoin SuperIntelligence
**Branch:** `wsi-phase1`
**Estimated Time:** 20 minutes

---

## ✅ COMPLETED (by Claude)

- [x] Created `api_wsi.py` - WSI backend API
- [x] Created `data/wsi_usage.json` - Usage tracking
- [x] Created `wsi_chat.html` - Web chat interface
- [x] Created `docs/WSI_SYSTEM.md` - Complete documentation
- [x] Uploaded to GitHub branch `wsi-phase1`

---

## 🚀 DEPLOYMENT STEPS

### Step 1: Merge Branch (2 min)

1. Go to: https://github.com/WattCoin-Org/wattcoin/tree/wsi-phase1
2. Create PR: `wsi-phase1` → `main`
3. Title: "Add WSI Phase 1 - Token-Gated SuperIntelligence"
4. Merge

### Step 2: Integrate in bridge_web.py (Already Done!)

The code is already integrated. File modified:
- `bridge_web.py` - Added WSI blueprint

### Step 3: Deploy to Railway (Auto - 3 min)

Railway auto-deploys on merge to main.

Watch: Railway → Deployments

### Step 4: Verify Deployment (1 min)

Test endpoints:

```bash
# System info
curl https://wattcoin-production-81a7.up.railway.app/api/v1/wsi/info

# Should return:
# {"system": "WattCoin SuperIntelligence (WSI)", ...}
```

### Step 5: Deploy Web Interface (10 min)

**Option A: Add to wattcoin.org (Recommended)**

Add route in Vercel deployment:

```javascript
// In your Next.js/React app
import WSIChat from './components/WSIChat'

// Create new page: /wsi
export default function WSI() {
  return <WSIChat />
}
```

Or serve the HTML directly:

```
/public/wsi.html (copy wsi_chat.html)
```

**Option B: Standalone Page**

Upload `wsi_chat.html` to:
- Vercel: `wattcoin.org/wsi`
- GitHub Pages
- IPFS

### Step 6: Test with Real Wallet (5 min)

1. Open chat interface
2. Enter a wallet with ≥5K WATT
3. Click "Connect"
4. Should show: "Connected" + balance + queries
5. Send message: "What is WattCoin?"
6. Verify WSI responds

---

## 🧪 TESTING CHECKLIST

- [ ] `/api/v1/wsi/info` returns system info
- [ ] `/api/v1/wsi/status` checks balance correctly
- [ ] Chat endpoint works with valid wallet
- [ ] Rejects wallet with <5K WATT
- [ ] Rate limiting works (try 21 queries)
- [ ] Conversation history maintains context
- [ ] Web interface displays correctly
- [ ] Mobile responsive

---

## 📊 MONITORING

**Watch these metrics:**

1. **Usage:** Check `data/wsi_usage.json`
2. **Queries:** Track daily volume
3. **Errors:** Railway logs for failures
4. **Balance checks:** RPC performance

**Query stats:**
```bash
curl https://wattcoin-production-81a7.up.railway.app/api/v1/wsi/info
# Check: total_queries, queries_24h
```

---

## 🎯 LAUNCH PLAN

### Soft Launch (Day 1)

1. Deploy to production ✅
2. Test with your wallet
3. Share in small group (Discord/Telegram)
4. Collect feedback

### Public Launch (Day 2)

**Twitter Thread:**

```
🧠⚡ Introducing WattCoin SuperIntelligence (WSI)

The unified AI of the WattCoin network is now LIVE.

What is it?
→ Token-gated Grok chat
→ Hold 5K WATT = instant access
→ 20 queries/day for holders
→ "WattCoin Intelligence" personality

Try it: wattcoin.org/wsi

🧵 Thread (1/7)
```

**Content Ideas:**
- Demo video: Wallet → WSI chat
- "Ask WSI about WattCoin" screenshots
- Comparison: ChatGPT vs WSI (WSI knows project)
- Tease Phase 2 (swarm intelligence)

### Growth Tactics

1. **Airdrop holders get early access**
2. **Create bounty:** "Improve WSI personality - 100K WATT"
3. **Daily highlights:** "Best WSI queries of the day"
4. **Challenge:** "Stump the WSI - win 50K WATT"

---

## 🔄 INTEGRATION WITH OTHER FEATURES

### PR Bounty System
- Agents can ask WSI: "How do I earn WATT?"
- WSI explains PR bounty process
- Directs to GitHub issues

### WattNode (Future)
- WSI becomes the frontend
- WattNode becomes the backend
- Phase 2: Queries routed to swarm

### Moltbook
- Post WSI responses as content
- "Asked the WattCoin AI about..."
- Cross-platform engagement

---

## 🚨 TROUBLESHOOTING

**WSI returns "Not configured":**
```
Check: GROK_API_KEY set in Railway env vars
```

**Balance check fails:**
```
Check: Solana RPC responding
curl https://api.mainnet-beta.solana.com -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"getHealth"}'
```

**Rate limit not working:**
```
Check: data/wsi_usage.json exists and is writable
```

**Web UI not loading:**
```
Check: wsi_chat.html served correctly
Check: API_URL in HTML matches Railway URL
```

---

## 💡 QUICK WINS

**Day 1 Actions:**

1. ✅ Deploy WSI
2. 📱 Post Twitter announcement
3. 🎥 Record demo video
4. 💬 Share in Discord/Telegram
5. 📊 Monitor first queries

**Week 1 Goals:**

- 100+ WSI queries
- 10+ unique wallets using it
- 3+ Twitter threads about it
- Content: "WSI vs ChatGPT" comparison

---

## ⏭️ NEXT: Phase 2 Planning

Once Phase 1 is stable:

**Phase 2 Features:**
- Multi-node query routing
- WattNode integration
- Node earnings (70% of fees)
- Query burn mechanism (500 WATT/query)

**Timeline:** Q2 2026

**Prep work:**
- Test WattNode Lite with CPU inference
- Design query routing algorithm
- Build node reputation system

---

## 📝 NOTES

- No token burn in Phase 1 (free for holders)
- 5K WATT minimum encourages holding
- 20 queries/day prevents spam
- Balance cached 5 min (reduces RPC load)

---

## 🎉 SUCCESS METRICS

You'll know WSI Phase 1 is successful when:

✅ 100+ daily queries
✅ 50+ unique wallets using it
✅ Positive feedback on Twitter
✅ "Hold WATT to chat with WSI" meme spreads
✅ Requests for Telegram/Discord bots

---

**Ready to launch WattCoin SuperIntelligence!** ⚡🧠

Next step: Merge `wsi-phase1` branch and watch it auto-deploy.
