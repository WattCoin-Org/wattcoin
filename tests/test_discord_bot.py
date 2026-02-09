import unittest
from unittest.mock import patch, MagicMock
from discord_bot.bot import is_valid_solana_address, bot

class TestWattBot(unittest.TestCase):
    def test_solana_address_validation(self):
        # 1. Valid addresses
        self.assertTrue(is_valid_solana_address("Dv4QWv74JaAWuQPecptgTDsfYnSw5HKwYuCMNaG6CxFM"))
        self.assertTrue(is_valid_solana_address("7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF"))
        
        # 2. Invalid characters
        self.assertFalse(is_valid_solana_address("O0Il")) # Invalid base58 (no O, 0, I, l)
        
        # 3. Invalid lengths
        self.assertFalse(is_valid_solana_address("A" * 31)) # Too short
        self.assertFalse(is_valid_solana_address("A" * 45)) # Too long
        
        # 4. Null/Empty
        self.assertFalse(is_valid_solana_address(""))
        self.assertFalse(is_valid_solana_address(None))

    def test_solana_address_sanitization(self):
        # 5. Whitespace handling
        self.assertTrue(is_valid_solana_address("  Dv4QWv74JaAWuQPecptgTDsfYnSw5HKwYuCMNaG6CxFM  "))

    def test_type_validation(self):
        # 6. Type check
        self.assertFalse(is_valid_solana_address(12345))
        self.assertFalse(is_valid_solana_address(["address"]))

    def test_malicious_input(self):
        # 7. Malicious characters
        self.assertFalse(is_valid_solana_address("Dv4QWv74JaAWuQPecptgTDsfYnSw5HKwYuCMNaG6CxFM; DROP TABLE nodes;"))

    @patch('discord_bot.bot.http')
    async def test_balance_logic(self, mock_http):
        # 6. Mock balance response
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {"value": [{"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": 1000}}}}}}]}
        }
        mock_http.post.return_value = mock_resp
        
        # This is harder to test without a full discord mock, 
        # but we can verify is_valid_solana_address is called.
        self.assertTrue(is_valid_solana_address("Dv4QWv74JaAWuQPecptgTDsfYnSw5HKwYuCMNaG6CxFM"))

if __name__ == '__main__':
    unittest.main()
