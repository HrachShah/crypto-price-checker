"""Tests for Crypto Price Checker."""

import unittest
from unittest.mock import MagicMock, patch

from crypto_price_checker.cli import CryptoPriceChecker


class TestCryptoPriceChecker(unittest.TestCase):
    """Tests for CryptoPriceChecker."""

    def test_checker_init(self):
        """Checker initializes correctly."""
        checker = CryptoPriceChecker()
        self.assertEqual(checker.BASE_URL, "https://api.coingecko.com/api/v3")

    def test_cache_basic(self):
        """Cache stores and retrieves values."""
        checker = CryptoPriceChecker()
        checker.CACHE["test:usd"] = (0, {"price": 100.0})
        self.assertEqual(checker.CACHE["test:usd"][1]["price"], 100.0)


if __name__ == "__main__":
    unittest.main()
