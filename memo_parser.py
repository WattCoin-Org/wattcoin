#!/usr/bin/env python3
"""
WattCoin Transaction Memo Parser

Scans Solana blockchain for WATT token transactions and extracts/categorizes payment memos.

Usage:
    python3 memo_parser.py [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD] [--wallet ADDRESS] [--output report.json]

Author: hello46871574
Task: https://github.com/WattCoin-Org/wattcoin/issues/240
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

# Solana libraries
try:
    from solders.rpc.requests import GetSignaturesForAddress, GetTransaction
    from solders.rpc.responses import RpcConfirmedTransactionStatusWithSignature
    from solders.signature import Signature
    from solders.pubkey import Pubkey
    from solders.transaction import VersionedTransaction
except ImportError:
    print("Installing required packages...")
    os.system("pip3 install solders base58 -q")
    from solders.rpc.requests import GetSignaturesForAddress, GetTransaction
    from solders.rpc.responses import RpcConfirmedTransactionStatusWithSignature
    from solders.signature import Signature
    from solders.pubkey import Pubkey
    from solders.transaction import VersionedTransaction

import base58
import requests


# =============================================================================
# CONSTANTS
# =============================================================================

WATT_MINT = "Gpmbh4PoQnL1kNgpMYDED3iv4fczcr7d3qNBLf8rpump"
MEMO_PROGRAM_ID = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
MEMO_PROGRAM_ID_V2 = "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo"
SOLANA_RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://solana.publicnode.com")

# Transaction categories
class TxCategory(str, Enum):
    BOUNTY_PAYMENT = "bounty_payment"
    SWARMSOLVE_PAYMENT = "swarmsolve_payment"
    SWARMSOLVE_REFUND = "swarmsolve_refund"
    TASK_PAYOUT = "task_payout"
    WSI_PAYOUT = "wsi_payout"
    OTHER = "other"
    UNKNOWN = "unknown"


@dataclass
class ParsedMemo:
    """Represents a parsed transaction memo."""
    tx_signature: str
    timestamp: str
    category: str
    raw_memo: str
    amount_watt: Optional[float] = None
    issue_number: Optional[str] = None
    pr_number: Optional[str] = None
    score: Optional[float] = None
    task_id: Optional[str] = None
    solution_id: Optional[str] = None
    sender: Optional[str] = None
    receiver: Optional[str] = None


@dataclass
class ReportSummary:
    """Summary statistics for the report."""
    total_transactions: int
    total_watt: float
    by_category: Dict[str, Dict[str, Any]]
    date_range: Dict[str, str]
    wallet_filter: Optional[str]


# =============================================================================
# SOLANA RPC CLIENT
# =============================================================================

class SolanaRPCClient:
    """Simple Solana RPC client for transaction queries."""
    
    def __init__(self, rpc_url: str = SOLANA_RPC_URL):
        self.rpc_url = rpc_url
        self.session = requests.Session()
        
    def _make_request(self, method: str, params: list, retries: int = 3) -> dict:
        """Make a JSON-RPC request to Solana with retry logic."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }
        
        for attempt in range(retries):
            try:
                response = self.session.post(self.rpc_url, json=payload, timeout=30)
                response.raise_for_status()
                result = response.json()
                
                # Check for RPC error
                if "error" in result:
                    raise Exception(f"RPC error: {result['error'].get('message', 'Unknown')}")
                
                return result
            except requests.exceptions.HTTPError as e:
                if response.status_code == 429:  # Rate limited
                    wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s, 6s
                    print(f"   Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    if attempt == retries - 1:
                        raise Exception(f"RPC request failed after {retries} retries: {e}")
                else:
                    raise Exception(f"RPC request failed: {e}")
            except requests.exceptions.RequestException as e:
                if attempt == retries - 1:
                    raise Exception(f"RPC request failed after {retries} retries: {e}")
                time.sleep(1)
        
        raise Exception("RPC request failed")
    
    def get_token_accounts_by_mint(self, mint: str, limit: int = 1000) -> List[str]:
        """Get all token accounts for a specific mint (limited)."""
        result = self._make_request("getTokenAccountsByOwner", [
            "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",  # Token program ID as owner filter
            {"mint": mint},
            {"encoding": "jsonParsed"}
        ])
        
        accounts = []
        if "result" in result and "value" in result["result"]:
            for account in result["result"]["value"][:limit]:
                accounts.append(account["pubkey"])
        return accounts
    
    def get_signatures_for_mint(self, mint: str, limit: int = 100) -> List[dict]:
        """Get transaction signatures for a token mint (tracks minting/transfers)."""
        return self.get_signatures_for_address(mint, limit=limit)
    
    def get_signatures_for_address(self, address: str, limit: int = 100, before: Optional[str] = None) -> List[dict]:
        """Get transaction signatures for an address."""
        params = [address, {"limit": limit}]
        if before:
            params[1]["before"] = before
        
        result = self._make_request("getSignaturesForAddress", params)
        
        if "result" in result:
            return result["result"]
        return []
    
    def get_transaction(self, signature: str) -> Optional[dict]:
        """Get full transaction details."""
        result = self._make_request("getTransaction", [
            signature,
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0
            }
        ])
        
        if "result" in result:
            return result["result"]
        return None


# =============================================================================
# MEMO PARSER
# =============================================================================

class MemoParser:
    """Parses WattCoin transaction memos."""
    
    # Memo patterns
    PATTERNS = {
        "bounty": r"WattCoin Bounty\s*\|\s*PR\s*#?(\d+)\s*\|\s*Issue\s*#?(\d+)\s*\|\s*Score:\s*([\d.]+)\s*\|\s*([\d.]+)\s*WATT",
        "swarmsolve_payment": r"swarmsolve:payment:([A-Za-z0-9_-]+)",
        "swarmsolve_refund": r"swarmsolve:expired:([A-Za-z0-9_-]+)",
        "task_payout": r"task:payout:([A-Za-z0-9_-]+)",
        "wsi_payout": r"wsi:payout:([A-Za-z0-9_-]+)",
    }
    
    def __init__(self):
        self.parsed_count = 0
        self.unknown_count = 0
    
    def parse_memo(self, raw_memo: str, tx_data: dict, tx_signature: str = None) -> ParsedMemo:
        """Parse a raw memo string into structured data."""
        import re
        
        raw_memo = raw_memo.strip() if raw_memo else ""
        
        # tx_signature 可能在调用时传入，也可能在 tx_data 中
        if not tx_signature:
            tx_signature = tx_data.get("signature", "unknown")
        
        # 尝试从不同位置获取时间戳
        timestamp = tx_data.get("blockTime", 0)
        if not timestamp and "transaction" in tx_data:
            timestamp = tx_data["transaction"].get("blockTime", 0)
        timestamp_str = datetime.fromtimestamp(timestamp).isoformat() if timestamp else "unknown"
        
        # Try to extract amount from transaction
        amount_watt = self._extract_amount_from_tx(tx_data)
        
        # Extract sender/receiver
        sender, receiver = self._extract_participants(tx_data)
        
        # Match against patterns
        category = TxCategory.UNKNOWN
        parsed = ParsedMemo(
            tx_signature=tx_signature,
            timestamp=timestamp_str,
            category=category.value,
            raw_memo=raw_memo,
            amount_watt=amount_watt,
            sender=sender,
            receiver=receiver
        )
        
        if not raw_memo:
            self.unknown_count += 1
            return parsed
        
        # Bounty payment
        match = re.search(self.PATTERNS["bounty"], raw_memo, re.IGNORECASE)
        if match:
            parsed.category = TxCategory.BOUNTY_PAYMENT.value
            parsed.pr_number = match.group(1)
            parsed.issue_number = match.group(2)
            parsed.score = float(match.group(3))
            if amount_watt is None:
                parsed.amount_watt = float(match.group(4))
            self.parsed_count += 1
            return parsed
        
        # SwarmSolve payment
        match = re.search(self.PATTERNS["swarmsolve_payment"], raw_memo, re.IGNORECASE)
        if match:
            parsed.category = TxCategory.SWARMSOLVE_PAYMENT.value
            parsed.solution_id = match.group(1)
            self.parsed_count += 1
            return parsed
        
        # SwarmSolve refund/expired
        match = re.search(self.PATTERNS["swarmsolve_refund"], raw_memo, re.IGNORECASE)
        if match:
            parsed.category = TxCategory.SWARMSOLVE_REFUND.value
            parsed.solution_id = match.group(1)
            self.parsed_count += 1
            return parsed
        
        # Task payout
        match = re.search(self.PATTERNS["task_payout"], raw_memo, re.IGNORECASE)
        if match:
            parsed.category = TxCategory.TASK_PAYOUT.value
            parsed.task_id = match.group(1)
            self.parsed_count += 1
            return parsed
        
        # WSI payout
        match = re.search(self.PATTERNS["wsi_payout"], raw_memo, re.IGNORECASE)
        if match:
            parsed.category = TxCategory.WSI_PAYOUT.value
            parsed.task_id = match.group(1)
            self.parsed_count += 1
            return parsed
        
        # Unknown format
        self.unknown_count += 1
        return parsed
    
    def _extract_amount_from_tx(self, tx_data: dict) -> Optional[float]:
        """Extract WATT amount from transaction data."""
        try:
            if "meta" not in tx_data or tx_data["meta"] is None:
                return None
            
            post_balances = tx_data["meta"].get("postTokenBalances", [])
            pre_balances = tx_data["meta"].get("preTokenBalances", [])
            
            # Find WATT token balance changes
            for post in post_balances:
                if post.get("mint") == WATT_MINT:
                    post_amount = float(post.get("uiTokenAmount", {}).get("uiAmount", 0))
                    
                    # Find corresponding pre balance
                    pre_amount = 0
                    for pre in pre_balances:
                        if pre.get("mint") == WATT_MINT and pre.get("owner") == post.get("owner"):
                            pre_amount = float(pre.get("uiTokenAmount", {}).get("uiAmount", 0))
                            break
                    
                    # Calculate change
                    change = post_amount - pre_amount
                    if change != 0:
                        return abs(change)
            
            return None
        except Exception as e:
            return None
    
    def _extract_participants(self, tx_data: dict) -> tuple:
        """Extract sender and receiver from transaction."""
        try:
            if "transaction" not in tx_data:
                return None, None
            
            message = tx_data["transaction"].get("message", {})
            account_keys = message.get("accountKeys", [])
            
            if not account_keys:
                return None, None
            
            # First account is usually the sender (fee payer)
            sender = account_keys[0].get("pubkey") if isinstance(account_keys[0], dict) else str(account_keys[0])
            
            # Try to find receiver from token transfers
            meta = tx_data.get("meta", {})
            pre_balances = meta.get("preTokenBalances", [])
            post_balances = meta.get("postTokenBalances", [])
            
            # Find accounts with WATT balance changes
            watt_accounts = set()
            for bal in pre_balances + post_balances:
                if bal.get("mint") == WATT_MINT:
                    watt_accounts.add(bal.get("owner"))
            
            # If we have exactly 2 WATT accounts, one is sender, one is receiver
            if len(watt_accounts) == 2:
                accounts = list(watt_accounts)
                if sender in accounts:
                    accounts.remove(sender)
                    return sender, accounts[0] if accounts else None
            
            return sender, None
        except Exception:
            return None, None


# =============================================================================
# MAIN SCANNER
# =============================================================================

class WattCoinMemoScanner:
    """Main scanner for WattCoin transaction memos."""
    
    def __init__(self, rpc_url: str = SOLANA_RPC_URL):
        self.rpc = SolanaRPCClient(rpc_url)
        self.parser = MemoParser()
        self.watt_mint = WATT_MINT
    
    def scan(self, 
             start_date: Optional[datetime] = None,
             end_date: Optional[datetime] = None,
             wallet_filter: Optional[str] = None,
             max_transactions: int = 1000,
             verbose: bool = True) -> List[ParsedMemo]:
        """
        Scan WATT transactions and parse memos.
        
        Args:
            start_date: Start date for scan
            end_date: End date for scan
            wallet_filter: Filter by specific wallet address
            max_transactions: Maximum transactions to scan
            verbose: Print progress
        
        Returns:
            List of parsed memos
        """
        print(f"🔍 Starting WATT memo scan...")
        print(f"   RPC: {self.rpc.rpc_url}")
        print(f"   WATT Mint: {self.watt_mint}")
        if start_date:
            print(f"   From: {start_date.isoformat()}")
        if end_date:
            print(f"   To: {end_date.isoformat()}")
        if wallet_filter:
            print(f"   Wallet filter: {wallet_filter}")
        print(f"   Max transactions: {max_transactions}")
        print()
        
        # Scan directly from WATT mint address transaction history
        print("📊 Fetching WATT mint transaction history...")
        
        all_memos = []
        scanned = 0
        before_signature = None
        
        while scanned < max_transactions:
            if verbose:
                print(f"   Fetching batch... (scanned: {scanned})")
            
            # Get transaction signatures for mint
            signatures = self.rpc.get_signatures_for_address(self.watt_mint, limit=100, before=before_signature)
            
            if not signatures:
                print("   No more transactions found")
                break
            
            for sig_info in signatures:
                if scanned >= max_transactions:
                    break
                
                sig = sig_info.get("signature")
                if not sig:
                    continue
                
                # Check date range
                sig_time = sig_info.get("blockTime", 0)
                if sig_time:
                    sig_datetime = datetime.fromtimestamp(sig_time)
                    if start_date and sig_datetime < start_date:
                        continue
                    if end_date and sig_datetime > end_date:
                        continue
                
                # Get full transaction (with rate limiting)
                try:
                    tx_data = self.rpc.get_transaction(sig)
                    time.sleep(0.5)  # Rate limiting: 500ms between requests
                except Exception as e:
                    if verbose:
                        print(f"   Failed to fetch tx {sig[:20]}...: {e}")
                    continue
                if not tx_data:
                    continue
                
                # Extract memo from transaction
                raw_memo = self._extract_memo_from_tx(tx_data)
                
                # Parse memo if it's a WATT transfer
                if raw_memo or self._is_watt_transfer(tx_data):
                    parsed = self.parser.parse_memo(raw_memo, tx_data, tx_signature=sig)
                    all_memos.append(parsed)
                    scanned += 1
            
            # Update before_signature for next batch
            if signatures:
                before_signature = signatures[-1].get("signature")
            else:
                break
        
        print(f"\n✅ Scan complete!")
        print(f"   Total transactions scanned: {scanned}")
        print(f"   Memos parsed: {self.parser.parsed_count}")
        print(f"   Unknown format: {self.parser.unknown_count}")
        
        return all_memos
    
    def _extract_memo_from_tx(self, tx_data: dict) -> Optional[str]:
        """Extract memo instruction data from transaction."""
        try:
            if "transaction" not in tx_data:
                return None
            
            message = tx_data["transaction"].get("message", {})
            instructions = message.get("instructions", [])
            
            for instr in instructions:
                program_id = instr.get("programId", "")
                
                # Check if this is a memo instruction
                if program_id in [MEMO_PROGRAM_ID, MEMO_PROGRAM_ID_V2]:
                    memo_data = instr.get("parsed", {})
                    if "info" in memo_data:
                        return memo_data["info"].get("memo")
            
            return None
        except Exception:
            return None
    
    def _is_watt_transfer(self, tx_data: dict) -> bool:
        """Check if transaction involves WATT token transfer."""
        try:
            meta = tx_data.get("meta", {})
            pre_balances = meta.get("preTokenBalances", [])
            post_balances = meta.get("postTokenBalances", [])
            
            for bal in pre_balances + post_balances:
                if bal.get("mint") == WATT_MINT:
                    return True
            
            return False
        except Exception:
            return False
    
    def generate_report(self, memos: List[ParsedMemo], output_file: str = "memo_report.json") -> dict:
        """Generate a JSON report from parsed memos."""
        
        # Calculate summary statistics
        by_category = {}
        total_watt = 0.0
        
        for memo in memos:
            cat = memo.category
            if cat not in by_category:
                by_category[cat] = {
                    "count": 0,
                    "total_watt": 0.0,
                    "transactions": []
                }
            
            by_category[cat]["count"] += 1
            if memo.amount_watt:
                by_category[cat]["total_watt"] += memo.amount_watt
                total_watt += memo.amount_watt
            
            by_category[cat]["transactions"].append(asdict(memo))
        
        # Create summary
        summary = ReportSummary(
            total_transactions=len(memos),
            total_watt=total_watt,
            by_category=by_category,
            date_range={
                "start": min((m.timestamp for m in memos if m.timestamp != "unknown"), default="unknown"),
                "end": max((m.timestamp for m in memos if m.timestamp != "unknown"), default="unknown")
            },
            wallet_filter=None
        )
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "summary": asdict(summary),
            "parser_stats": {
                "parsed_count": self.parser.parsed_count,
                "unknown_count": self.parser.unknown_count,
                "parse_rate": f"{(self.parser.parsed_count / len(memos) * 100) if memos else 0:.1f}%"
            },
            "transactions": [asdict(m) for m in memos]
        }
        
        # Write to file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Report saved to: {output_file}")
        
        # Print summary
        print("\n" + "="*60)
        print("📊 REPORT SUMMARY")
        print("="*60)
        print(f"Total Transactions: {summary.total_transactions}")
        print(f"Total WATT: {summary.total_watt:,.2f}")
        print("\nBy Category:")
        for cat, data in sorted(by_category.items()):
            print(f"  {cat}: {data['count']} txns, {data['total_watt']:,.2f} WATT")
        print("="*60)
        
        return report


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="WattCoin Transaction Memo Parser")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--wallet", type=str, help="Filter by wallet address")
    parser.add_argument("--max-txns", type=int, default=1000, help="Maximum transactions to scan")
    parser.add_argument("--output", type=str, default="memo_report.json", help="Output file path")
    parser.add_argument("--rpc-url", type=str, default=SOLANA_RPC_URL, help="Solana RPC URL")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    
    args = parser.parse_args()
    
    # Parse dates
    start_date = None
    end_date = None
    
    if args.start_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    if args.end_date:
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d")
        # Include the entire end day
        end_date = end_date + timedelta(days=1)
    
    # Create scanner and run
    scanner = WattCoinMemoScanner(rpc_url=args.rpc_url)
    
    memos = scanner.scan(
        start_date=start_date,
        end_date=end_date,
        wallet_filter=args.wallet,
        max_transactions=args.max_txns,
        verbose=not args.quiet
    )
    
    # Generate report
    scanner.generate_report(memos, output_file=args.output)


if __name__ == "__main__":
    main()
