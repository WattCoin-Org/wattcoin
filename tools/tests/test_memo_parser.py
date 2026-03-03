import unittest

from tools.memo_parser import classify_memo, extract_memo_texts, extract_watt_amount, tx_mentions_wallet


class MemoParserTests(unittest.TestCase):
    def test_classify_memo(self):
        self.assertEqual(classify_memo("WattCoin Bounty | PR #2"), "bounty_payment")
        self.assertEqual(classify_memo("swarmsolve:payment:abc"), "swarmsolve_payment")
        self.assertEqual(classify_memo("swarmsolve:expired:abc"), "swarmsolve_refund")
        self.assertEqual(classify_memo("task:payout:task_123"), "task_payout")
        self.assertEqual(classify_memo("wsi:payout:job_77"), "wsi_payout")
        self.assertEqual(classify_memo("unknown format"), "other")

    def test_extract_memo_texts(self):
        tx = {
            "transaction": {
                "message": {
                    "instructions": [
                        {"program": "spl-memo", "parsed": "task:payout:TASK_1"},
                        {"program": "system", "parsed": {"type": "transfer", "info": {}}},
                    ]
                }
            },
            "meta": {},
        }
        self.assertEqual(extract_memo_texts(tx), ["task:payout:TASK_1"])

    def test_extract_watt_amount(self):
        tx = {
            "meta": {
                "preTokenBalances": [
                    {
                        "accountIndex": 3,
                        "mint": "MINT",
                        "uiTokenAmount": {"amount": "1000000", "decimals": 6},
                    },
                    {
                        "accountIndex": 4,
                        "mint": "MINT",
                        "uiTokenAmount": {"amount": "0", "decimals": 6},
                    },
                ],
                "postTokenBalances": [
                    {
                        "accountIndex": 3,
                        "mint": "MINT",
                        "uiTokenAmount": {"amount": "250000", "decimals": 6},
                    },
                    {
                        "accountIndex": 4,
                        "mint": "MINT",
                        "uiTokenAmount": {"amount": "750000", "decimals": 6},
                    },
                ],
            }
        }
        self.assertAlmostEqual(extract_watt_amount(tx, "MINT"), 0.75)

    def test_wallet_filter(self):
        tx = {
            "transaction": {
                "message": {
                    "accountKeys": [
                        {"pubkey": "wallet_a"},
                        {"pubkey": "wallet_b"},
                    ]
                }
            }
        }
        self.assertTrue(tx_mentions_wallet(tx, "wallet_a"))
        self.assertFalse(tx_mentions_wallet(tx, "wallet_c"))


if __name__ == "__main__":
    unittest.main()
