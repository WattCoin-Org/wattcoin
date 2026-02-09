import unittest
from bot import is_valid_solana_address

class TestWattBot(unittest.TestCase):
    def test_solana_address_validation(self):
        # Valid addresses (random Solana addresses)
        self.assertTrue(is_valid_solana_address("Dv4QWv74JaAWuQPecptgTDsfYnSw5HKwYuCMNaG6CxFM"))
        self.assertTrue(is_valid_solana_address("7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF"))
        
        # Invalid addresses
        self.assertFalse(is_valid_solana_address("invalid_address"))
        self.assertFalse(is_valid_solana_address("12345"))
        self.assertFalse(is_valid_solana_address("O0Il")) # Invalid base58 characters
        self.assertFalse(is_valid_solana_address(""))

if __name__ == '__main__':
    unittest.main()
