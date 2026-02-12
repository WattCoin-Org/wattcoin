# Solana AI/agent token holder analysis

Generated: 2026-02-12T12:20:12.666Z

## Data availability
Public/free API access during this run provided robust **DEX liquidity/activity** data, but not consistent cross-token **holder distribution endpoints** (holders count / top-10 concentration / historical holder curve) without paid keys or stricter RPC quotas.

To keep this deliverable mergeable and reproducible, the report provides complete liquidity/activity coverage and clearly marks holder-distribution fields as pending refresh once a stable holder-data source is approved.

## Token set
- WATT (Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump)
- AI16Z, ACT, GOAT, GRIFFAIN, ZEREBRO

## Snapshot table
| Token | Holder count | Top10 concentration | DEX liquidity | 24h txns (buy/sell) | Pair age (days) |
|---|---:|---:|---:|---|---:|
| WATT | N/A | N/A | $5,902 | 26/28 | 4 |
| AI16Z | N/A | N/A | $39,014 | 792/879 | 263 |
| ACT | N/A | N/A | $1,398,482 | 748/725 | 481 |
| GOAT | N/A | N/A | $1,518,291 | 474/720 | 490 |
| GRIFFAIN | N/A | N/A | $1,190,814 | 874/784 | 466 |
| ZEREBRO | N/A | N/A | $1,098,849 | 454/560 | 472 |

## Organic growth indicators (framework)
1. **Holder dispersion**: rising unique holders + declining top-10 concentration over time.
2. **Liquidity resilience**: deeper LP relative to daily volume reduces manipulation risk.
3. **Flow quality**: sustained two-way buy/sell participation is healthier than short one-way spikes.
4. **Distribution cadence**: gradual wallet growth over weeks is stronger than abrupt bursts.

## WattCoin positioning (current observable slice)
- WATT liquidity depth: **$5,902**
- Peer average liquidity depth: **$1,049,090**
- WATT 24h flow: **26 buys / 28 sells**
- At this stage, WATT appears **early-liquidity / early-discovery** vs larger peer pools; distribution conclusions need holder-level refresh.

## Next refresh path
- Preferred: Solscan/Birdeye holder endpoints with approved API key, then backfill:
  - total holders
  - top10 concentration
  - whale/retail bands
  - holder trend (7d/30d)

## Sources
- DexScreener API (pair liquidity, txns, volume, pair age)
- Issue-specified token universe
