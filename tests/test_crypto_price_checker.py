"""Tests for Crypto Price Checker."""

import math
import unittest
from unittest.mock import MagicMock, patch
import requests
from click.testing import CliRunner

from crypto_price_checker.cli import CryptoPriceChecker, _is_finite, main


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
            mock_get.side_effect = Exception("Network error")
            result = checker.get_price("bitcoin", "usd")
            self.assertIsNone(result)

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
        import time
        now = time.time()
        old_time = now - checker.CACHE_TTL - 1
        checker.CACHE["bitcoin:usd"] = (old_time, {"price": 50000.0})
        result = checker.get_price("bitcoin", "usd")
        self.assertIsNotNone(result)
        self.assertNotEqual(result.get("price"), 50000.0)


class TestIsFinite(unittest.TestCase):
    """Tests for the _is_finite helper used by the CLI to validate change_24h."""

    def test_returns_true_for_int(self):
        self.assertTrue(_is_finite(0))
        self.assertTrue(_is_finite(42))
        self.assertTrue(_is_finite(-7))

    def test_returns_true_for_finite_float(self):
        self.assertTrue(_is_finite(0.0))
        self.assertTrue(_is_finite(3.14))
        self.assertTrue(_is_finite(-2.5))

    def test_returns_false_for_none(self):
        self.assertFalse(_is_finite(None))

    def test_returns_false_for_string(self):
        # CoinGecko occasionally returns "1.5" instead of 1.5; f-string
        # format spec crashes on this, so _is_finite must reject it.
        self.assertFalse(_is_finite("1.5"))
        self.assertFalse(_is_finite(""))

    def test_returns_false_for_nan(self):
        self.assertFalse(_is_finite(float("nan")))

    def test_returns_false_for_inf(self):
        self.assertFalse(_is_finite(float("inf")))
        self.assertFalse(_is_finite(float("-inf")))

    def test_returns_false_for_bool(self):
        # bool is a subclass of int, but logically not a numeric change_24h.
        self.assertFalse(_is_finite(True))
        self.assertFalse(_is_finite(False))

    def test_returns_false_for_other_types(self):
        self.assertFalse(_is_finite([]))
        self.assertFalse(_is_finite({}))
        self.assertFalse(_is_finite(object()))


class TestCliChangeFormatting(unittest.TestCase):
    """The CLI must not crash when change_24h is a string or non-finite."""

    def _run(self, change_24h):
        from click.testing import CliRunner
        with patch.object(
            CryptoPriceChecker, "get_prices",
            return_value=[{
                "coin": "btc",
                "currency": "usd",
                "price": 67890.12345,
                "change_24h": change_24h,
            }],
        ):
            return CliRunner().invoke(main, ["btc"])

    def test_stringified_change_renders_as_na(self):
        # CoinGecko sometimes returns the 24h change as "1.5" rather than 1.5;
        # the previous code crashed with ValueError: Unknown format code 'f'
        # for object of type 'str' on this input.
        r = self._run("1.5")
        self.assertEqual(r.exit_code, 0, msg=r.output)
        self.assertIn("BTC:", r.output)
        self.assertIn("N/A", r.output)
        self.assertNotIn("+1.50", r.output)

    def test_none_change_renders_as_na(self):
        r = self._run(None)
        self.assertEqual(r.exit_code, 0, msg=r.output)
        self.assertIn("N/A", r.output)

    def test_nan_change_renders_as_na(self):
        r = self._run(float("nan"))
        self.assertEqual(r.exit_code, 0, msg=r.output)
        self.assertIn("N/A", r.output)

    def test_inf_change_renders_as_na(self):
        r = self._run(float("inf"))
        self.assertEqual(r.exit_code, 0, msg=r.output)
        self.assertIn("N/A", r.output)

    def test_normal_float_change_still_formats(self):
        r = self._run(1.5)
        self.assertEqual(r.exit_code, 0, msg=r.output)
        self.assertIn("+1.50%", r.output)


if __name__ == "__main__":
    unittest.main()