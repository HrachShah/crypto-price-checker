"""Tests for Crypto Price Checker."""

import time
import unittest
from unittest.mock import MagicMock, patch

from crypto_price_checker.cli import CryptoPriceChecker


class TestCryptoPriceChecker(unittest.TestCase):
    """Tests for CryptoPriceChecker."""

    def test_checker_init(self):
        """Checker initializes correctly."""
        checker = CryptoPriceChecker()
        self.assertEqual(checker.BASE_URL, "https://api.coingecko.com/api/v3")
        self.assertEqual(checker.CACHE_TTL, 60)

    def test_cache_is_not_shared_between_checkers(self):
        """One checker instance must not reuse another instance's cache."""
        first = CryptoPriceChecker()
        second = CryptoPriceChecker()
        first.CACHE["bitcoin:usd"] = (0, {"price": 100.0})
        self.assertNotIn("bitcoin:usd", second.CACHE)

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

    def test_get_price_returns_none_for_invalid_json(self):
        """Malformed API responses should be treated as unavailable prices."""
        checker = CryptoPriceChecker()
        response = MagicMock(status_code=200)
        response.json.side_effect = ValueError("invalid JSON")
        with patch.object(checker.session, "get", return_value=response):
            self.assertIsNone(checker.get_price("bitcoin", "usd"))

    def test_get_price_returns_none_on_error(self):
        """get_price returns None when API fails."""
        checker = CryptoPriceChecker()
        with patch.object(checker.session, "get") as mock_get:
            mock_get.side_effect = Exception("Network error")
            result = checker.get_price("bitcoin", "usd")
            self.assertIsNone(result)

    def test_get_price_returns_none_for_malformed_payload(self):
        """Malformed successful responses should be treated as unavailable."""
        checker = CryptoPriceChecker()
        response = MagicMock(status_code=200)
        response.json.return_value = {"bitcoin": None}
        with patch.object(checker.session, "get", return_value=response):
            self.assertIsNone(checker.get_price("bitcoin", "usd"))


    def test_get_prices_returns_empty_for_scalar_payload(self):
        """A successful scalar response cannot contain coin prices."""
        checker = CryptoPriceChecker()
        response = MagicMock(status_code=200)
        response.json.return_value = []
        with patch.object(checker.session, "get", return_value=response):
            self.assertEqual(checker.get_prices(["bitcoin"], "usd"), [])

    def test_get_prices_returns_empty_for_missing_coins(self):
        """A batch response without requested coins produces no results."""
        checker = CryptoPriceChecker()
        response = MagicMock(status_code=200)
        response.json.return_value = {}
        with patch.object(checker.session, "get", return_value=response):
            self.assertEqual(checker.get_prices(["bitcoin", "invalid-coin"], "usd"), [])

    def test_get_prices_returns_valid_results(self):
        """get_prices returns only coins present in the API response."""
        checker = CryptoPriceChecker()
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "bitcoin": {"usd": 50000.0, "usd_24h_change": 2.5},
            "ethereum": {"usd": 3000.0, "usd_24h_change": -1.2},
        }
        with patch.object(checker.session, "get", return_value=response):
            results = checker.get_prices(["bitcoin", "invalid", "ethereum"], "usd")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["coin"], "bitcoin")
        self.assertEqual(results[1]["coin"], "ethereum")

    def test_get_prices_cache_hit_preserves_requested_order(self):
        """A canonical batch cache key must not change display order."""
        checker = CryptoPriceChecker()
        checker.CACHE["bitcoin,ethereum:usd"] = (time.time(), [
            {"coin": "bitcoin", "currency": "usd", "price": 50000.0, "change_24h": 2.5},
            {"coin": "ethereum", "currency": "usd", "price": 3000.0, "change_24h": -1.2},
        ])
        with patch.object(checker.session, "get") as mock_get:
            results = checker.get_prices(["ethereum", "bitcoin"], "usd")

        self.assertEqual([result["coin"] for result in results], ["ethereum", "bitcoin"])
        mock_get.assert_not_called()


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
        response = MagicMock(status_code=200)
        response.json.return_value = {"bitcoin": {"usd": 51000.0}}
        with patch.object(checker.session, "get", return_value=response):
            result = checker.get_price("bitcoin", "usd")
        self.assertEqual(result["price"], 51000.0)


if __name__ == "__main__":
    unittest.main()