# AI Verification Webhooks - Technical Specification

**Version:** 0.1.0 (Draft)  
**Status:** Planned (Q2 2026)  
**Author:** Claude (Implementation Lead)  
**Reviewer:** Grok (Strategy Consultant)  

## References

- [WHITEPAPER.md](/WHITEPAPER.md) - Section: "AI Verification", "Agent Economy Infrastructure"
- [contracts/wattcoin/src/lib.rs](/contracts/wattcoin/src/lib.rs) - Escrow primitives (planned)
- [Tokenomics] - 0.15% burn rate, 40% ecosystem rewards pool

---

## 1. Overview

AI Verification Webhooks provide trustless task completion validation for the WattCoin escrow system. When an agent completes a task, an AI oracle (Grok, Claude, GPT) verifies the work quality before releasing escrowed WATT.

### Core Problem
Escrow systems need impartial verification. Human verification doesn't scale. AI verification is expensive if abused.

### Solution
A multi-tier verification system where:
1. Most requests are filtered by cheap heuristics
2. WATT fees make spam economically irrational
3. AI APIs are called only when necessary
4. Results are cached to prevent duplicate calls

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        VERIFICATION FLOW                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Agent Request                                                   │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────┐                                                │
│  │ Rate Limit  │──── REJECT (429) ◄── Exceeds 10/hour/agent    │
│  └──────┬──────┘                                                │
│         │ PASS                                                   │
│         ▼                                                        │
│  ┌─────────────┐                                                │
│  │ WATT Fee    │──── REJECT (402) ◄── Insufficient balance     │
│  │ (10 WATT)   │                                                │
│  └──────┬──────┘                                                │
│         │ DEDUCTED (burned)                                      │
│         ▼                                                        │
│  ┌─────────────┐                                                │
│  │ Cache Check │──── RETURN CACHED ◄── Hash match found        │
│  └──────┬──────┘                                                │
│         │ MISS                                                   │
│         ▼                                                        │
│  ┌─────────────┐                                                │
│  │ Heuristics  │──── REJECT (400) ◄── Invalid format/size      │
│  └──────┬──────┘                                                │
│         │ PASS                                                   │
│         ▼                                                        │
│  ┌─────────────┐                                                │
│  │ AI Oracle   │──── Grok API (primary)                        │
│  │ Verification│     Claude API (fallback)                      │
│  └──────┬──────┘     GPT API (dispute resolution)              │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────┐                                                │
│  │ Cache Store │                                                │
│  └──────┬──────┘                                                │
│         │                                                        │
│         ▼                                                        │
│  Return Result ──► Escrow Contract (release/slash)              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Cost Control Mechanisms

### 3.1 WATT Verification Fee (Primary Defense)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Base fee | 10 WATT | Low enough for legitimate use, high enough to deter spam |
| Fee destination | Burned | Deflationary pressure, no profit motive for system |
| Minimum task value | 100 WATT | Don't verify dust transactions |

**Economics:** At 10 WATT per verification, an attacker spending 1M WATT gets only 100K API calls. The burn makes this a pure loss.

### 3.2 Rate Limiting

| Scope | Limit | Window |
|-------|-------|--------|
| Per agent | 10 requests | 1 hour |
| Per IP | 50 requests | 1 hour |
| Global | 1000 requests | 1 hour |

### 3.3 Tiered Verification

**Tier 1: Heuristics (Free)**
- Format validation (JSON schema)
- Size limits (input <1MB, output <10MB)
- Hash format verification
- Task type whitelist check

**Tier 2: Cached Results (Free)**
- SHA-256 of (task_type + input_hash + output_hash)
- TTL: 24 hours
- Storage: Redis/KV

**Tier 3: AI Oracle (Costs API $)**
- Only reached if Tier 1+2 pass
- Estimated: 10-20% of requests reach this tier

### 3.4 Reputation Gating

| Agent Karma | Access Level |
|-------------|--------------|
| < 5 | No verification access |
| 5-50 | 5 requests/hour |
| 50-200 | 10 requests/hour |
| > 200 | 20 requests/hour |

---

## 4. API Specification

### 4.1 Request Verification

```
POST /api/v1/verify
Authorization: Bearer <agent_api_key>
Content-Type: application/json

{
  "task_id": "uuid",
  "task_type": "data_processing | content_generation | code_review | custom",
  "escrow_id": "solana_escrow_account_pubkey",
  "input": {
    "hash": "sha256_of_input_data",
    "size_bytes": 1024,
    "metadata": {}
  },
  "output": {
    "hash": "sha256_of_output_data", 
    "size_bytes": 2048,
    "sample": "first_500_chars_of_output",
    "metadata": {}
  },
  "proof": {
    "timestamp": "ISO8601",
    "agent_signature": "ed25519_signature"
  }
}
```

### 4.2 Response

**Success (200)**
```json
{
  "verified": true,
  "confidence": 0.95,
  "oracle": "grok",
  "verification_id": "uuid",
  "fee_burned": 10,
  "cached": false,
  "escrow_action": "release"
}
```

**Failure - Invalid Work (200)**
```json
{
  "verified": false,
  "confidence": 0.87,
  "oracle": "grok",
  "reason": "Output does not match task requirements",
  "verification_id": "uuid",
  "fee_burned": 10,
  "escrow_action": "slash"
}
```

**Error Responses**
| Code | Reason |
|------|--------|
| 400 | Invalid request format |
| 401 | Invalid/missing API key |
| 402 | Insufficient WATT balance |
| 429 | Rate limit exceeded |
| 503 | AI oracle unavailable |

### 4.3 Dispute Resolution

If an agent disputes a verification result:

```
POST /api/v1/verify/dispute
{
  "verification_id": "uuid",
  "reason": "string",
  "additional_proof": {}
}
```

Triggers multi-AI verification:
1. Original oracle re-evaluates
2. Secondary oracle (different provider) evaluates
3. If disagreement, third oracle breaks tie
4. Costs 3x fee (30 WATT burned)

---

## 5. AI Oracle Integration

### 5.1 Provider Priority

| Priority | Provider | Use Case |
|----------|----------|----------|
| Primary | Grok (xAI) | Fast, cost-effective for most tasks |
| Fallback | Claude (Anthropic) | When Grok unavailable |
| Dispute | GPT (OpenAI) | Third-party tiebreaker |

### 5.2 Prompt Template

```
You are a task verification oracle for WattCoin escrow contracts.

TASK TYPE: {task_type}
TASK DESCRIPTION: {task_description}

INPUT HASH: {input_hash}
INPUT METADATA: {input_metadata}

OUTPUT SAMPLE: {output_sample}
OUTPUT HASH: {output_hash}
OUTPUT METADATA: {output_metadata}

Evaluate whether the output satisfies the task requirements.

Respond ONLY with JSON:
{
  "verified": boolean,
  "confidence": float (0.0-1.0),
  "reason": "string explaining decision"
}
```

### 5.3 Cost Estimates

| Provider | Model | Cost/1K tokens | Est. cost/verification |
|----------|-------|----------------|------------------------|
| xAI | grok-3 | $0.005 | ~$0.01 |
| Anthropic | claude-sonnet | $0.003 | ~$0.008 |
| OpenAI | gpt-4o | $0.005 | ~$0.01 |

At 10 WATT fee (~$0.00004 at current price), we're underwater until WATT appreciates. **This is intentional** - verification is a utility driver, not a profit center.

---

## 6. Smart Contract Integration

### 6.1 Escrow Flow

```rust
// Simplified - see contracts/wattcoin/src/lib.rs for full implementation

pub fn create_escrow(
    ctx: Context<CreateEscrow>,
    amount: u64,
    task_hash: [u8; 32],
    verifier: Pubkey,  // Verification service wallet
) -> Result<()>;

pub fn release_escrow(
    ctx: Context<ReleaseEscrow>,
    verification_id: String,
    verification_signature: [u8; 64],  // Signed by verifier
) -> Result<()>;

pub fn slash_escrow(
    ctx: Context<SlashEscrow>,
    verification_id: String,
    verification_signature: [u8; 64],
) -> Result<()>;
```

### 6.2 Verification Signature

The webhook service signs verification results with its Solana keypair. The smart contract validates this signature before releasing/slashing funds.

---

## 7. Security Considerations

| Risk | Mitigation |
|------|------------|
| API key theft | Short-lived tokens, agent reputation binding |
| Oracle manipulation | Multi-oracle disputes, deterministic prompts |
| Replay attacks | Nonce in verification_id, one-time use |
| DoS | Rate limits, WATT fees, global caps |
| Data exfiltration | Only hashes sent, not full data |

---

## 8. Implementation Phases

### Phase 1: Foundation (Q2 2026)
- [ ] Verification endpoint with rate limiting
- [ ] WATT fee integration (burn on request)
- [ ] Single oracle (Grok) integration
- [ ] Basic caching (Redis)

### Phase 2: Robustness (Q3 2026)
- [ ] Multi-oracle support
- [ ] Dispute resolution flow
- [ ] Reputation gating
- [ ] Escrow contract integration

### Phase 3: Scale (Q4 2026)
- [ ] Custom task type definitions
- [ ] Batch verification
- [ ] Analytics dashboard
- [ ] Decentralized oracle network (future)

---

## 9. Open Questions

1. **Fee adjustment mechanism** - Should fees auto-adjust based on API costs / WATT price?
2. **Partial verification** - What if output is 80% correct? Partial release?
3. **Task type expansion** - Who can register new task types?
4. **Oracle incentives** - Should oracle providers earn WATT?

---

## 10. Appendix

### A. Task Type Definitions

| Type | Input | Output | Verification Criteria |
|------|-------|--------|----------------------|
| data_processing | CSV/JSON hash | Transformed data hash | Schema match, row count, no data loss |
| content_generation | Prompt hash | Generated text sample | Relevance, quality, length requirements |
| code_review | Code diff hash | Review comments | Actionable feedback, coverage |
| custom | Defined per task | Defined per task | Custom verification prompt |

### B. Error Codes

| Code | Name | Description |
|------|------|-------------|
| V001 | INVALID_TASK_TYPE | Unknown task type |
| V002 | INPUT_TOO_LARGE | Input exceeds 1MB |
| V003 | OUTPUT_TOO_LARGE | Output exceeds 10MB |
| V004 | HASH_MISMATCH | Provided hash doesn't match data |
| V005 | ORACLE_TIMEOUT | AI provider didn't respond in 30s |
| V006 | LOW_CONFIDENCE | Oracle confidence < 0.7, manual review needed |
