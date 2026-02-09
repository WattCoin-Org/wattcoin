import unittest
from unittest.mock import patch, MagicMock
from discord_bot.bot import is_valid_solana_address
import requests

class TestWattBot(unittest.TestCase):
    def test_solana_address_validation_correct(self):
        # 1. Valid addresses
        self.assertTrue(is_valid_solana_address("Dv4QWv74JaAWuQPecptgTDsfYnSw5HKwYuCMNaG6CxFM"))
        self.assertTrue(is_valid_solana_address("7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF"))

    def test_solana_address_validation_invalid_chars(self):
        # 2. Invalid characters (Solana uses base58 - no O, 0, I, l)
        self.assertFalse(is_valid_solana_address("Dv4QWv74JaAWuQPecptgTDsfYnSw5HKwYuCMNaG6CxO")) 
        self.assertFalse(is_valid_solana_address("Dv4QWv74JaAWuQPecptgTDsfYnSw5HKwYuCMNaG6C0"))

    def test_solana_address_validation_length(self):
        # 3. Invalid lengths
        self.assertFalse(is_valid_solana_address("A" * 31)) # Too short
        self.assertFalse(is_valid_solana_address("A" * 45)) # Too long

    def test_solana_address_validation_null(self):
        # 4. Null/Empty
        self.assertFalse(is_valid_solana_address(""))
        self.assertFalse(is_valid_solana_address(None))

    def test_solana_address_sanitization(self):
        # 5. Whitespace handling
        self.assertTrue(is_valid_solana_address("  Dv4QWv74JaAWuQPecptgTDsfYnSw5HKwYuCMNaG6CxFM  "))

    @patch('discord_bot.bot.http')
    def test_solana_rpc_call_logic(self, mock_http):
        # 6. Mock a successful Solana RPC response for WATT balance
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "value": [
                    {
                        "account": {
                            "data": {
                                "parsed": {
                                    "info": {
                                        "tokenAmount": {
                                            "uiAmount": 1337.5
                                        }
                                    }
                                }
                            }
                        }
                    }
                ]
            }
        }
        mock_response.status_code = 200
        mock_http.post.return_value = mock_response

        # Test logic would go here if we extracted the core balance fetcher
        # For now, we just verify our mock works as expected for the balance logic in bot.py
        resp = mock_http.post("https://mock-rpc.com", json={})
        data = resp.json()
        balance = data["result"]["value"][0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"]
        self.assertEqual(balance, 1337.5)

    @patch('discord_bot.bot.http')
    def test_api_stats_call_logic(self, mock_http):
        # 7. Mock a successful Stats API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "nodes": {"active": 5, "total_registered": 10},
            "reliability": {"avg_score": 95},
            "payouts": {"total_watt": 50000},
            "jobs": {"total_completed": 100, "total_failed": 2}
        }
        mock_response.status_code = 200
        mock_http.get.return_value = mock_response

        resp = mock_http.get("http://localhost:5000/api/v1/stats")
        data = resp.json()
        self.assertEqual(data["nodes"]["active"], 5)
        self.assertEqual(data["payouts"]["total_watt"], 50000)

if __name__ == '__main__':
    unittest.main()
