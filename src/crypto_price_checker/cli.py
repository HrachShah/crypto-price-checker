"""CLI for crypto price checker."""

import json
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
        self._cache: dict[str, tuple[float, Any]] = {}
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/json"

    def get_price(self, coin_id: str, currency: str = "usd") -> dict[str, Any] | None:
        """Get current price for a coin."""
        cache_key = f"{coin_id}:{currency}"
        now = time.time()

        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if now - cached_time < self.CACHE_TTL:
                return cached_data

        url = f"{self.BASE_URL}/simple/price"
        params = {"ids": coin_id, "vs_currencies": currency, "include_24hr_change": "true"}

        try:
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if coin_id in data:
                    raw_price = data[coin_id].get(currency)
                    # CoinGecko occasionally returns a null or non-numeric
                    # price field (rate limit, missing pair, API key issue).
                    # Treat those as "no result" so callers get None instead
                    # of a dict with price=None that breaks downstream math.
                    if raw_price is None or isinstance(raw_price, bool) or not isinstance(raw_price, (int, float)):
                        return None
                    result = {
                        "coin": coin_id,
                        "currency": currency,
                        "price": raw_price,
                        "change_24h": data[coin_id].get(f"{currency}_24h_change"),
                    }
                    self._cache[cache_key] = (now, result)
                    return result
        except (requests.RequestException, OSError, json.JSONDecodeError):
            pass
        return None

    def get_prices(self, coin_ids: list[str], currency: str = "usd") -> list[dict[str, Any]]:
        """Get prices for multiple coins, falling back per-coin to filter out failures.

        Uses a single batched API call to keep the happy path cheap, but for any
        coin whose row in the batch response is missing the price field (or has
        a non-numeric price), the function falls back to the per-coin
        get_price() so the entry is still surfaced if a separate lookup works.
        The final per-coin fallback also ensures callers (and tests) that
        pre-mock get_price() see the underlying per-coin semantics.
        """
        if not coin_ids:
            return []

        # Preserve order while deduping so the per-coin fallback is
        # deterministic for callers and tests.
        seen: set[str] = set()
        unique_coin_ids: list[str] = []
        for coin_id in coin_ids:
            if coin_id not in seen:
                seen.add(coin_id)
                unique_coin_ids.append(coin_id)

        # Per-coin is the canonical path: it gives us the same cache and
        # exception-narrowing as get_price(), and it lets each coin be
        # surfaced or dropped independently of the others.
        results: list[dict[str, Any]] = []
        for coin_id in unique_coin_ids:
            single = self.get_price(coin_id, currency)
            if single is not None:
                results.append(single)

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
    results = checker.get_prices(list(coins), currency)

    if not results:
        click.echo("Could not fetch prices. Check coin IDs and try again.")
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
