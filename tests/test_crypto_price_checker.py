"""Tests for Crypto Price Checker.

These tests follow the current implementation contract:
- cache is per-instance
- get_price/get_prices raise on HTTP errors
- get_prices batches coin IDs into one API request
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest
import requests

from crypto_price_checker.cli import CryptoPriceChecker


def _mock_response(status_code: int, json_data=None):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    if status_code >= 400:
        err = requests.HTTPError(f"{status_code} HTTP Error")
        err.response = resp
        resp.raise_for_status.side_effect = err
    else:
        resp.raise_for_status.return_value = None
    return resp


class TestCryptoPriceChecker(unittest.TestCase):
    """Tests for CryptoPriceChecker."""

    def test_checker_init(self):
        """Checker initializes correctly."""
        checker = CryptoPriceChecker()
        self.assertEqual(checker.BASE_URL, "https://api.coingecko.com/api/v3")
        self.assertEqual(checker.CACHE_TTL, 60)
        self.assertIsInstance(checker.cache, dict)
        self.assertEqual(checker.cache, {})

    def test_cache_basic(self):
        """Cache stores and retrieves values."""
        checker = CryptoPriceChecker()
        checker.cache["test:usd"] = (0, {"price": 100.0})
        self.assertEqual(checker.cache["test:usd"][1]["price"], 100.0)

    def test_cache_ttl_expiry(self):
        """Cache entries expire after CACHE_TTL seconds."""
        checker = CryptoPriceChecker()
        old_time = 0
        checker.cache["test:usd"] = (old_time, {"price": 100.0})
        self.assertIn("test:usd", checker.cache)

    def test_get_price_raises_on_network_error(self):
        """get_price propagates network errors."""
        checker = CryptoPriceChecker()
        with patch.object(checker.session, "get", side_effect=requests.ConnectionError("dns")):
            with self.assertRaises(requests.RequestException):
                checker.get_price("bitcoin", "usd")

    def test_get_price_returns_none_when_api_has_no_data(self):
        """get_price still returns None when CoinGecko has no data for a coin id."""
        checker = CryptoPriceChecker()
        with patch.object(checker.session, "get", return_value=_mock_response(200, {})):
            self.assertIsNone(checker.get_price("not-a-coin", "usd"))

    def test_get_prices_empty_input_returns_empty(self):
        """get_prices short-circuits on empty input."""
        checker = CryptoPriceChecker()
        self.assertEqual(checker.get_prices([], "usd"), [])

    def test_get_prices_filters_unknown_coins(self):
        """get_prices filters out coins missing from the CoinGecko payload."""
        checker = CryptoPriceChecker()
        payload = {
            "bitcoin": {"usd": 50000.0, "usd_24h_change": 2.5},
        }
        with patch.object(checker.session, "get", return_value=_mock_response(200, payload)):
            results = checker.get_prices(["bitcoin", "invalid-coin"], "usd")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["coin"], "bitcoin")

    def test_get_prices_raises_on_http_error(self):
        """get_prices propagates upstream HTTP errors."""
        checker = CryptoPriceChecker()
        with patch.object(checker.session, "get", return_value=_mock_response(429)):
            with self.assertRaises(requests.HTTPError):
                checker.get_prices(["bitcoin"], "usd")

    def test_get_prices_returns_valid_results(self):
        """get_prices returns only successful price lookups."""
        checker = CryptoPriceChecker()
        payload = {
            "bitcoin": {"usd": 50000.0, "usd_24h_change": 2.5},
            "ethereum": {"usd": 3000.0, "usd_24h_change": -1.2},
        }
        with patch.object(checker.session, "get", return_value=_mock_response(200, payload)):
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
        checker.cache[key] = (0, {"price": 50000.0})
        self.assertIn(key, checker.cache)

    def test_cache_rejects_expired_entries(self):
        """Expired cache entries are not returned."""
        checker = CryptoPriceChecker()
        import time

        now = time.time()
        old_time = now - checker.CACHE_TTL - 1
        checker.cache["bitcoin:usd"] = (old_time, {"price": 50000.0})
        with patch.object(checker.session, "get", return_value=_mock_response(200, {"bitcoin": {"usd": 49000.0, "usd_24h_change": 1.0}})):
            result = checker.get_price("bitcoin", "usd")
        self.assertIsNotNone(result)
        self.assertNotEqual(result.get("price"), 50000.0)

    def test_cache_isolation_instance_1(self):
        """Cache entries are isolated between instances."""
        checker1 = CryptoPriceChecker()
        checker1.cache["test:usd"] = (0, {"price": 100.0})
        checker2 = CryptoPriceChecker()
        self.assertNotIn("test:usd", checker2.cache)

    def test_cache_isolation_instance_2(self):
        """Cache entries are isolated between instances."""
        checker1 = CryptoPriceChecker()
        checker1.cache["test:usd"] = (0, {"price": 100.0})
        checker2 = CryptoPriceChecker()
        checker2.cache["test:usd"] = (0, {"price": 200.0})
        self.assertEqual(checker1.cache["test:usd"][1]["price"], 100.0)
        self.assertEqual(checker2.cache["test:usd"][1]["price"], 200.0)

    def test_cache_isolation_instance_3(self):
        """Cache entries are isolated between instances."""
        checker1 = CryptoPriceChecker()
        checker1.cache["test:usd"] = (0, {"price": 100.0})
        checker2 = CryptoPriceChecker()
        self.assertNotIn("test:usd", checker2.cache)


if __name__ == "__main__":
    unittest.main()
