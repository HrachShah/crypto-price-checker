"""CLI for crypto price checker."""

import sys
import time
from typing import Any

import click
import requests


class CryptoPriceChecker:
    """Check cryptocurrency prices via CoinGecko API."""

    BASE_URL = "https://api.coingecko.com/api/v3"
    CACHE_TTL = 60  # seconds

    def __init__(self):
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/json"
        # Per-instance cache: a class-level dict would be shared across all
        # CryptoPriceChecker instances in the same process, but each CLI
        # invocation is a fresh process so the class-level cache is always
        # empty when get_price is called and never serves a hit. A per-
        # instance dict also lets callers (e.g. tests) use isolated caches.
        self.cache: dict[str, tuple[float, dict[str, Any] | list[dict[str, Any]]]] = {}

    def get_price(self, coin_id: str, currency: str = "usd") -> dict[str, Any] | None:
        """Get current price for a coin.

        Returns None if the coin was unknown to CoinGecko (the API returns
        200 with an empty body for unknown ids). Raises requests.HTTPError
        for any non-2xx response so the caller can distinguish "the API
        said no" (HTTP 4xx, e.g. rate limited at 429 or bad coin id at
        404) from "the network is down" (a connection / timeout error).
        Previously both cases returned None silently and the CLI printed
        the same generic "Could not fetch prices" message, which left
        users unable to tell whether they had a bad coin id or were
        hitting CoinGecko's free-tier rate limit.
        """
        cache_key = f"{coin_id}:{currency}"
        now = time.time()

        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if now - cached_time < self.CACHE_TTL:
                return cached_data

        url = f"{self.BASE_URL}/simple/price"
        params = {"ids": coin_id, "vs_currencies": currency, "include_24hr_change": "true"}

        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException:
            raise

        if coin_id in data:
            result = {
                "coin": coin_id,
                "currency": currency,
                "price": data[coin_id].get(currency),
                "change_24h": data[coin_id].get(f"{currency}_24h_change"),
            }
            self.cache[cache_key] = (now, result)
            return result
        return None

    def get_prices(self, coin_ids: list[str], currency: str = "usd") -> list[dict[str, Any]]:
        """Get prices for multiple coins in a single API call.

        See get_price for the HTTP-error contract: a 4xx/5xx response
        raises requests.HTTPError so the CLI can show an actionable
        message instead of the previous generic failure.
        """
        if not coin_ids:
            return []

        url = f"{self.BASE_URL}/simple/price"
        cache_key_parts = sorted(set(coin_ids))  # dedupe for consistent cache key
        cache_key = f"{','.join(cache_key_parts)}:{currency}"
        now = time.time()

        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if now - cached_time < self.CACHE_TTL:
                return cached_data

        params = {
            "ids": ",".join(coin_ids),
            "vs_currencies": currency,
            "include_24hr_change": "true",
        }

        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException:
            raise

        results = []
        for coin_id in coin_ids:
            if coin_id in data:
                results.append({
                    "coin": coin_id,
                    "currency": currency,
                    "price": data[coin_id].get(currency),
                    "change_24h": data[coin_id].get(f"{currency}_24h_change"),
                })
        if results:
            self.cache[cache_key] = (now, results)
        return results


@click.command()
@click.argument("coins", nargs=-1)
@click.option("--currency", "-c", default="usd", help="Currency to show price in (default: usd)")
def main(coins: tuple[str, ...], currency: str) -> None:
    """Check cryptocurrency prices."""
    if not coins:
        click.echo("Usage: crypto-price COIN [COIN ...]")
        click.echo("Example: crypto-price bitcoin ethereum")
        sys.exit(1)

    checker = CryptoPriceChecker()
    try:
        results = checker.get_prices(list(coins), currency)
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        if status == 429:
            click.echo(
                "CoinGecko rate limit reached (HTTP 429). "
                "Wait a minute and try again, or check the free-tier quota."
            )
        elif status == 404:
            click.echo("CoinGecko API endpoint not found (HTTP 404).")
        elif 500 <= status < 600:
            click.echo(f"CoinGecko is having an outage (HTTP {status}). Try again later.")
        else:
            click.echo(f"CoinGecko returned HTTP {status}: {e}")
        sys.exit(1)
    except requests.RequestException as e:
        click.echo(f"Network error talking to CoinGecko: {e}")
        sys.exit(1)

    if not results:
        click.echo(
            "No prices returned. Check that the coin ids are valid "
            "(e.g. 'bitcoin', 'ethereum')."
        )
        sys.exit(1)

    for r in results:
        price = r["price"]
        change = r["change_24h"]
        change_str = f"{change:+.2f}%" if change is not None else "N/A"
        symbol = r["coin"].upper()
        if price is None:
            click.echo(f"{symbol}: N/A {currency.upper()} ({change_str})")
        else:
            click.echo(f"{symbol}: {price:.6f} {currency.upper()} ({change_str})")


if __name__ == "__main__":
    main()
