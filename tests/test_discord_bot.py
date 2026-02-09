import unittest
from unittest.mock import patch, MagicMock
from discord_bot.bot import is_valid_solana_address

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

    def test_type_validation(self):
        # 6. Strict type check
        self.assertFalse(is_valid_solana_address(123456789))
        self.assertFalse(is_valid_solana_address({"key": "value"}))

    def test_malicious_input(self):
        # 7. Injection patterns
        self.assertFalse(is_valid_solana_address("Dv4QWv74JaAWuQPecptgTDsfYnSw5HKwYuCMNaG6CxFM; DROP TABLE nodes;"))
        self.assertFalse(is_valid_solana_address("<script>alert(1)</script>"))

    def test_regex_matching(self):
        # 8. Non-base58 symbols
        self.assertFalse(is_valid_solana_address("Dv4QWv74JaAWuQPecptgTDsfYnSw5HKwYuCMNaG6CxFM!"))
        self.assertFalse(is_valid_solana_address("Dv4QWv74JaAWuQPecptgTDsfYnSw5HKwYuCMNaG6CxFM_"))

if __name__ == '__main__':
    unittest.main()
