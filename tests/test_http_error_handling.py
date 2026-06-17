"""Tests for HTTP error surfacing in CryptoPriceChecker.

The fix changes the contract of get_price / get_prices: a 4xx or 5xx
HTTP response now raises requests.HTTPError so the CLI can distinguish
"the API rejected our request" (e.g. HTTP 429 rate-limit, HTTP 404 bad
coin id) from "the network is down" (a connection / timeout error).
Previously both cases silently returned None and the CLI printed the
same generic "Could not fetch prices" message, leaving users unable to
tell whether they had a bad coin id or were hitting CoinGecko's free-
tier rate limit.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests
from click.testing import CliRunner

from crypto_price_checker.cli import CryptoPriceChecker, main


def _mock_response(status_code: int, json_data=None, raise_for_status_exc=None):
    """Build a MagicMock that mimics a requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    if raise_for_status_exc is None and status_code >= 400:
        err = requests.HTTPError(f"{status_code} HTTP Error")
        err.response = resp
        resp.raise_for_status.side_effect = err
    else:
        resp.raise_for_status.side_effect = raise_for_status_exc
    return resp


class TestGetPriceHttpErrors:
    """get_price must raise HTTPError on 4xx/5xx instead of returning None."""

    def test_rate_limit_raises_http_error(self):
        checker = CryptoPriceChecker()
        with patch.object(checker.session, "get", return_value=_mock_response(429)):
            with pytest.raises(requests.HTTPError):
                checker.get_price("bitcoin", "usd")

    def test_server_error_raises_http_error(self):
        checker = CryptoPriceChecker()
        with patch.object(checker.session, "get", return_value=_mock_response(503)):
            with pytest.raises(requests.HTTPError):
                checker.get_price("bitcoin", "usd")

    def test_not_found_raises_http_error(self):
        checker = CryptoPriceChecker()
        with patch.object(checker.session, "get", return_value=_mock_response(404)):
            with pytest.raises(requests.HTTPError):
                checker.get_price("bitcoin", "usd")

    def test_connection_error_still_raises_request_exception(self):
        checker = CryptoPriceChecker()
        with patch.object(
            checker.session, "get", side_effect=requests.ConnectionError("dns")
        ):
            with pytest.raises(requests.RequestException):
                checker.get_price("bitcoin", "usd")

    def test_timeout_still_raises_request_exception(self):
        checker = CryptoPriceChecker()
        with patch.object(
            checker.session, "get", side_effect=requests.Timeout("slow")
        ):
            with pytest.raises(requests.RequestException):
                checker.get_price("bitcoin", "usd")

    def test_success_returns_result(self):
        checker = CryptoPriceChecker()
        payload = {"bitcoin": {"usd": 50000.0, "usd_24h_change": 1.5}}
        with patch.object(
            checker.session, "get", return_value=_mock_response(200, json_data=payload)
        ):
            result = checker.get_price("bitcoin", "usd")
        assert result is not None
        assert result["price"] == 50000.0
        assert result["change_24h"] == 1.5

    def test_unknown_coin_returns_none_not_raises(self):
        # CoinGecko returns 200 with an empty body for unknown ids. That
        # is not an HTTP error — the request succeeded, the API just has
        # no data for this id. We must keep returning None for this case
        # so callers can distinguish "unknown coin" from "rate-limited".
        checker = CryptoPriceChecker()
        with patch.object(
            checker.session, "get", return_value=_mock_response(200, json_data={})
        ):
            result = checker.get_price("not-a-coin", "usd")
        assert result is None


class TestGetPricesHttpErrors:
    """get_prices must also raise HTTPError on 4xx/5xx."""

    def test_rate_limit_raises_http_error(self):
        checker = CryptoPriceChecker()
        with patch.object(checker.session, "get", return_value=_mock_response(429)):
            with pytest.raises(requests.HTTPError):
                checker.get_prices(["bitcoin", "ethereum"], "usd")

    def test_server_error_raises_http_error(self):
        checker = CryptoPriceChecker()
        with patch.object(checker.session, "get", return_value=_mock_response(500)):
            with pytest.raises(requests.HTTPError):
                checker.get_prices(["bitcoin"], "usd")


class TestCliErrorMessages:
    """The CLI must print actionable messages instead of the generic failure."""

    def test_rate_limit_message(self):
        runner = CliRunner()
        with patch("crypto_price_checker.cli.CryptoPriceChecker.get_prices") as mock:
            err = requests.HTTPError("429 Too Many Requests")
            err.response = MagicMock(spec=requests.Response)
            err.response.status_code = 429
            mock.side_effect = err
            result = runner.invoke(main, ["bitcoin"])
        assert result.exit_code == 1
        assert "rate limit" in result.output.lower()
        assert "429" in result.output

    def test_server_error_message(self):
        runner = CliRunner()
        with patch("crypto_price_checker.cli.CryptoPriceChecker.get_prices") as mock:
            err = requests.HTTPError("503 Service Unavailable")
            err.response = MagicMock(spec=requests.Response)
            err.response.status_code = 503
            mock.side_effect = err
            result = runner.invoke(main, ["bitcoin"])
        assert result.exit_code == 1
        assert "503" in result.output

    def test_not_found_message(self):
        runner = CliRunner()
        with patch("crypto_price_checker.cli.CryptoPriceChecker.get_prices") as mock:
            err = requests.HTTPError("404 Not Found")
            err.response = MagicMock(spec=requests.Response)
            err.response.status_code = 404
            mock.side_effect = err
            result = runner.invoke(main, ["bitcoin"])
        assert result.exit_code == 1
        assert "404" in result.output

    def test_connection_error_message(self):
        runner = CliRunner()
        with patch("crypto_price_checker.cli.CryptoPriceChecker.get_prices") as mock:
            mock.side_effect = requests.ConnectionError("Name or service not known")
            result = runner.invoke(main, ["bitcoin"])
        assert result.exit_code == 1
        assert "network" in result.output.lower() or "error" in result.output.lower()

    def test_unknown_coin_message_says_check_ids(self):
        # Empty results must NOT exit with the old generic "Could not fetch
        # prices" message — that wording was misleading because the request
        # succeeded but the API had no data for the coin id. Now the message
        # tells the user to check their coin ids.
        runner = CliRunner()
        with patch(
            "crypto_price_checker.cli.CryptoPriceChecker.get_prices", return_value=[]
        ):
            result = runner.invoke(main, ["bitcoin"])
        assert result.exit_code == 1
        assert "check" in result.output.lower()
        assert "could not fetch prices" not in result.output.lower()