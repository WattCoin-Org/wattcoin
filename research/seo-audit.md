# WattCoin SEO & Discoverability Audit (Issue #217)

Date: 2026-02-12
Scope: https://wattcoin.org (sampled: `/`, `/bounties`, `/docs`, `/download`, `/whitepaper`)

## Executive Summary

WattCoin has baseline SEO in place (title, meta description, Open Graph, Twitter card, robots.txt, sitemap.xml), but discoverability is constrained by **template-level metadata duplication**, **missing canonical URLs**, and **no structured data markup**. Content currently under-targets key search phrases requested in this task, which likely suppresses rankings for intent-driven queries.

## 1) Technical SEO Check

### 1.1 Meta tags / Open Graph / Twitter cards

Observed on sampled pages:

- ✅ `title` present
- ✅ `meta description` present
- ✅ Open Graph tags present (`og:title`, `og:description`, `og:image`)
- ✅ `twitter:card` present
- ⚠️ Same metadata appears reused across all sampled pages
- ⚠️ `rel=canonical` missing on sampled pages

Impact:

- Reused page metadata reduces page differentiation in search results.
- Missing canonical can create index ambiguity (especially with `wattcoin.org` vs `www.wattcoin.org`).

### 1.2 robots.txt and sitemap.xml

- ✅ `https://wattcoin.org/robots.txt` available
- ✅ `https://wattcoin.org/sitemap.xml` available and populated
- ⚠️ Prefer sitemap host consistency with canonical host (`www` or non-`www`) after canonical policy is set.

### 1.3 Page load speed (publicly testable proxy checks)

Sample server response timings (single-run, no cache control):

- `/`: ~4.44s first response in this run
- `/bounties`: ~1.81s
- `/docs`: ~1.43s
- `/download`: ~1.33s
- `/whitepaper`: ~0.99s

Interpretation:

- Home page appears significantly slower than inner pages in this sample.
- Recommend running scheduled Lighthouse/PageSpeed checks to confirm Core Web Vitals and regressions.

### 1.4 Mobile responsiveness

- ✅ Site appears SPA-driven and generally mobile-compatible by framework behavior.
- ⚠️ No explicit mobile SEO evidence in sampled HTML snapshot beyond standard metadata.

Recommendation: ensure responsive breakpoints and tap target spacing are validated by Lighthouse mobile audits and manual checks on core templates.

### 1.5 Structured data / schema markup

- ❌ No `application/ld+json` schema detected on sampled pages.

High-value schema candidates:

- `Organization`
- `WebSite` (with `SearchAction` when internal search exists)
- `SoftwareApplication` (for WattNode download pages)
- `FAQPage` (if docs include FAQ sections)
- `BreadcrumbList` (if hierarchical docs routes exist)

## 2) Content Analysis

Target term coverage in sampled rendered HTML:

- `"AI utility token"` → not found
- `"distributed AI inference"` → found
- `"AI agent bounties"` → not found
- `"Solana AI token"` → not found

### Content gaps vs competitor patterns

Compared to strong-performing crypto/AI project sites, WattCoin currently lacks:

1. Dedicated SEO landing pages per intent cluster (token utility, inference network, bounty marketplace).
2. Terminology-level matching for transactional/informational queries (`AI agent bounties`, `Solana AI token`).
3. Rich explainer content that targets long-tail questions (“how AI bounty payouts work”, “how distributed AI inference rewards are calculated”).
4. Structured FAQ blocks designed for SERP feature capture.

### Internal linking structure

- ⚠️ Current pages look template-similar with limited unique contextual linking signals.
- Recommendation: add contextual links between `/`, `/bounties`, `/docs`, `/whitepaper`, `/download` using keyword-relevant anchor text.

## 3) Backlink Opportunities (5–10)

Priority list for relevant listings/directories:

1. CoinGecko (project profile completeness + docs links)
2. CoinMarketCap (project + ecosystem profile)
3. DeFiLlama (if protocol/incentive metrics are trackable)
4. Solana ecosystem/community directories (where submission is available)
5. GitHub Topics + curated awesome lists for AI agents / Solana tooling
6. DappRadar (if dApp-compatible surface exists)
7. Product Hunt (for WattNode tooling milestones)
8. Hacker News “Show HN” (for major open-source release updates)
9. Mirror / Medium canonical technical posts linking back to docs pages
10. Relevant AI agent newsletters/roundups (submit updates with proof-of-work metrics)

## 4) Prioritized Recommendations (Actionable + Expected Impact)

### P0 (Do first)

1. **Add page-specific title/meta/OG per route**
   - Expected impact: higher CTR and better query-to-page relevance.
2. **Add canonical URLs + enforce single preferred host** (`www` or non-`www`)
   - Expected impact: cleaner indexing, reduced duplicate ambiguity.
3. **Create dedicated landing pages for target terms**
   - Suggested slugs:
     - `/ai-utility-token`
     - `/distributed-ai-inference`
     - `/ai-agent-bounties`
     - `/solana-ai-token`
   - Expected impact: improved rankings for exact-match intent queries.

### P1 (Next)

4. **Inject JSON-LD schema (Organization + WebSite + SoftwareApplication where relevant)**
   - Expected impact: richer SERP understanding and potential rich-result eligibility.
5. **Strengthen internal linking with descriptive anchors**
   - Expected impact: better crawl depth and topical authority flow.
6. **Publish FAQ modules in docs and mark as FAQ schema**
   - Expected impact: long-tail capture and improved SERP snippet quality.

### P2 (Ongoing)

7. **Run weekly Lighthouse/PageSpeed baselines and track CWV trends**
   - Expected impact: prevent performance regressions, improve mobile SEO stability.
8. **Backlink outreach cadence (2–3 placements/month)**
   - Expected impact: domain authority growth and indexing acceleration.

## 5) Quick 30-Day Execution Plan

- Week 1: canonical + metadata refactor + host consistency
- Week 2: publish 2 keyword landing pages + internal link updates
- Week 3: schema rollout + FAQ enhancements
- Week 4: directory submissions + performance benchmark report

## Notes / Evidence Snapshot

Sampled routes: `/`, `/bounties`, `/docs`, `/download`, `/whitepaper`, `/robots.txt`, `/sitemap.xml`.
All sampled content pages currently share near-identical metadata and no JSON-LD markup in HTML output.
