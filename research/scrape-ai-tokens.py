#!/usr/bin/env python3
"""
Scrape top 50 AI/agent tokens from DexScreener API
Task: #142 (2,000 WATT)
"""

import requests
import json
from datetime import datetime

def fetch_ai_tokens():
    """Fetch AI/agent tokens from DexScreener"""
    search_terms = ["AI", "agent", "artificial intelligence", "autonomous", "neural"]
    all_pairs = []
    
    for term in search_terms:
        try:
            url = f"https://api.dexscreener.com/latest/dex/search?q={term}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                pairs = data.get('pairs', [])
                # Filter for Solana and filter out duplicates
                for pair in pairs:
                    if pair.get('chainId') == 'solana':
                        pair['searchTerm'] = term
                        all_pairs.append(pair)
        except Exception as e:
            print(f"Error fetching {term}: {e}")
    
    return all_pairs

def process_tokens(pairs):
    """Process and deduplicate tokens"""
    seen = set()
    unique_tokens = []
    
    for pair in pairs:
        address = pair.get('baseToken', {}).get('address', '')
        if address and address not in seen:
            seen.add(address)
            unique_tokens.append(pair)
    
    # Sort by market cap (if available) or liquidity
    unique_tokens.sort(key=lambda x: x.get('liquidity', {}).get('usd', 0), reverse=True)
    
    return unique_tokens[:50]  # Top 50

def format_token(pair):
    """Format token data for output"""
    base = pair.get('baseToken', {})
    quote = pair.get('quoteToken', {})
    liquidity = pair.get('liquidity', {})
    volume = pair.get('volume', {})
    price_change = pair.get('priceChange', {})
    
    return {
        "name": base.get('name', 'Unknown'),
        "ticker": base.get('symbol', 'UNKNOWN'),
        "contract_address": base.get('address', ''),
        "market_cap": pair.get('fdv', 0),  # Fully diluted valuation as proxy
        "price_usd": float(pair.get('priceUsd', 0)),
        "liquidity_usd": float(liquidity.get('usd', 0)),
        "volume_24h": float(volume.get('h24', 0)),
        "price_change_24h": float(price_change.get('h24', 0)),
        "pair_address": pair.get('pairAddress', ''),
        "dex_url": f"https://dexscreener.com/solana/{pair.get('pairAddress', '')}",
        "chain": "Solana"
    }

def generate_markdown(tokens):
    """Generate markdown summary table"""
    md = "# Top 50 AI/Agent Tokens on Solana\n\n"
    md += "**Source:** DexScreener API  \n"
    md += f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}  \n"
    md += "**Task:** WattCoin #142 (2,000 WATT)\n\n"
    md += "## Summary Table\n\n"
    md += "| Rank | Ticker | Name | Price (USD) | Market Cap | Liquidity | Volume 24h | 24h Change |\n"
    md += "|------|--------|------|-------------|------------|-----------|------------|------------|\n"
    
    for i, token in enumerate(tokens, 1):
        price = f"${token['price_usd']:,.8f}" if token['price_usd'] < 0.01 else f"${token['price_usd']:,.4f}"
        market_cap = f"${token['market_cap']:,.0f}" if token['market_cap'] else "N/A"
        liquidity = f"${token['liquidity_usd']:,.0f}" if token['liquidity_usd'] else "N/A"
        volume = f"${token['volume_24h']:,.0f}" if token['volume_24h'] else "N/A"
        change = f"{token['price_change_24h']:+.2f}%" if token['price_change_24h'] else "N/A"
        
        md += f"| {i} | {token['ticker']} | {token['name'][:30]} | {price} | {market_cap} | {liquidity} | {volume} | {change} |\n"
    
    md += "\n## Notes\n\n"
    md += "- Data sourced from DexScreener API\n"
    md += "- Filtered for Solana chain only\n"
    md += "- Sorted by liquidity (descending)\n"
    md += "- Market cap shown is FDV (Fully Diluted Valuation)\n"
    md += "- **Payout Wallet:** `RTC53fdf727dd301da40ee79cdd7bd740d8c04d2fb4`\n"
    md += "- **GitHub:** @zhuzhushiwojia\n"
    
    return md

def main():
    print("Fetching AI/agent tokens from DexScreener...")
    pairs = fetch_ai_tokens()
    print(f"Found {len(pairs)} total pairs")
    
    tokens = process_tokens(pairs)
    print(f"Processed {len(tokens)} unique tokens")
    
    # Format tokens
    formatted = [format_token(t) for t in tokens]
    
    # Save JSON
    with open('ai-tokens-solana.json', 'w') as f:
        json.dump({
            "metadata": {
                "source": "DexScreener API",
                "generated": datetime.now().isoformat(),
                "chain": "Solana",
                "count": len(formatted),
                "task": "WattCoin #142"
            },
            "tokens": formatted
        }, f, indent=2)
    print("Saved ai-tokens-solana.json")
    
    # Save Markdown
    md = generate_markdown(formatted)
    with open('ai-tokens-summary.md', 'w') as f:
        f.write(md)
    print("Saved ai-tokens-summary.md")
    
    print(f"\nTop 5 tokens by liquidity:")
    for i, t in enumerate(formatted[:5], 1):
        print(f"  {i}. {t['ticker']} - ${t['liquidity_usd']:,.0f} liquidity")

if __name__ == "__main__":
    main()
