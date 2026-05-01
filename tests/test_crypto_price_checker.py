"""Tests for Crypto Price Checker."""

import unittest
from unittest.mock import MagicMock, patch
import requests

from crypto_price_checker.cli import CryptoPriceChecker


class TestCryptoPriceChecker(unittest.TestCase):
    """Tests for CryptoPriceChecker."""

    def test_checker_init(self):
        """Checker initializes correctly."""
        checker = CryptoPriceChecker()
        self.assertEqual(checker.BASE_URL, "https://api.coingecko.com/api/v3")
        self.assertEqual(checker.CACHE_TTL, 60)

    def test_cache_basic(self):
        """Cache stores and retrieves values."""
        checker = CryptoPriceChecker()
        checker.CACHE["test:usd"] = (0, {"price": 100.0})
        self.assertEqual(checker.CACHE["test:usd"][1]["price"], 100.0)

    def test_cache_ttl_expiry(self):
        """Cache entries expire after CACHE_TTL seconds."""
        checker = CryptoPriceChecker()
        old_time = 0
        checker.CACHE["test:usd"] = (old_time, {"price": 100.0})
        self.assertIn("test:usd", checker.CACHE)

    def test_get_price_returns_none_on_error(self):
        """get_price returns None when API fails."""
        checker = CryptoPriceChecker()
        with patch.object(checker.session, "get") as mock_get:
            mock_get.side_effect = requests.RequestException("Network error")
            result = checker.get_price("bitcoin", "usd")
            self.assertIsNone(result)

    def test_get_prices_filters_none(self):
        """get_prices returns empty list when API call fails entirely."""
        checker = CryptoPriceChecker()
        with patch.object(checker.session, "get") as mock_get:
            mock_get.side_effect = requests.RequestException("Network error")
            results = checker.get_prices(["bitcoin", "invalid-coin"], "usd")
            self.assertEqual(results, [])

    def test_get_prices_returns_valid_results(self):
        """get_prices parses and returns successful price lookups from API."""
        checker = CryptoPriceChecker()
        with patch.object(checker.session, "get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {
                    "bitcoin": {"usd": 50000.0, "usd_24h_change": 2.5},
                    "ethereum": {"usd": 3000.0, "usd_24h_change": -1.2},
                },
            )
            results = checker.get_prices(["bitcoin", "invalid", "ethereum"], "usd")
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]["coin"], "bitcoin")
            self.assertEqual(results[1]["coin"], "ethereum")


class TestCryptoPriceCheckerCache(unittest.TestCase):
    """Tests for caching behavior."""

    def test_cache_key_format(self):
        """Cache keys are formatted as coin_id:currency."""
        checker = CryptoPriceChecker()
        key = "bitcoin:usd"
        checker.CACHE[key] = (0, {"price": 50000.0})
        self.assertIn(key, checker.CACHE)

    def test_cache_rejects_expired_entries(self):
        """Expired cache entries are not returned."""
        checker = CryptoPriceChecker()
        import time
        now = time.time()
        old_time = now - checker.CACHE_TTL - 1
        checker.CACHE["bitcoin:usd"] = (old_time, {"price": 50000.0})
        with patch.object(checker.session, "get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {"bitcoin": {"usd": 48000.0, "usd_24h_change": 1.5}},
            )
            result = checker.get_price("bitcoin", "usd")
            self.assertIsNotNone(result)
            self.assertEqual(result.get("price"), 48000.0)
            self.assertNotEqual(result.get("price"), 50000.0)


if __name__ == "__main__":
    unittest.main()