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

    def test_cache_isolated_between_instances(self):
        """Cache entries are not shared between checker instances."""
        first = CryptoPriceChecker()
        second = CryptoPriceChecker()
        first.CACHE["test:usd"] = (0, {"price": 100.0})
        self.assertNotIn("test:usd", second.CACHE)

    def test_get_price_returns_none_on_error(self):
        """get_price returns None when API fails."""
        checker = CryptoPriceChecker()
        with patch.object(checker.session, "get") as mock_get:
            mock_get.side_effect = requests.RequestException("Network error")
            result = checker.get_price("bitcoin", "usd")
            self.assertIsNone(result)

    def test_get_price_returns_none_for_invalid_json(self):
        """get_price returns None when the response is not valid JSON."""
        checker = CryptoPriceChecker()
        with patch.object(checker.session, "get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.side_effect = ValueError("invalid JSON")
            self.assertIsNone(checker.get_price("bitcoin", "usd"))

    def test_get_prices_filters_none(self):
        """get_prices filters out failed price lookups."""
        checker = CryptoPriceChecker()
        with patch.object(checker, "get_price") as mock_get_price:
            mock_get_price.return_value = None
            results = checker.get_prices(["bitcoin", "invalid-coin"], "usd")
            self.assertEqual(results, [])

    def test_get_prices_returns_valid_results(self):
        """get_prices returns only successful price lookups."""
        checker = CryptoPriceChecker()
        with patch.object(checker, "get_price") as mock_get_price:
            mock_get_price.side_effect = [
                {"coin": "bitcoin", "currency": "usd", "price": 50000.0, "change_24h": 2.5},
                None,
                {"coin": "ethereum", "currency": "usd", "price": 3000.0, "change_24h": -1.2},
            ]
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
        checker.CACHE["bitcoin:usd"] = (0, {"price": 50000.0})
        with patch("crypto_price_checker.cli.time.time", return_value=checker.CACHE_TTL + 1):
            with patch.object(checker.session, "get") as mock_get:
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = {
                    "bitcoin": {"usd": 51000.0, "usd_24h_change": 1.0}
                }
                result = checker.get_price("bitcoin", "usd")
        self.assertEqual(result["price"], 51000.0)


if __name__ == "__main__":
    unittest.main()