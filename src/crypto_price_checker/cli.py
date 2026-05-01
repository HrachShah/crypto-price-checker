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
    CACHE = {}
    CACHE_TTL = 60  # seconds

    def __init__(self):
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/json"

    def get_price(self, coin_id: str, currency: str = "usd") -> dict[str, Any] | None:
        """Get current price for a coin."""
        cache_key = f"{coin_id}:{currency}"
        now = time.time()

        if cache_key in self.CACHE:
            cached_time, cached_data = self.CACHE[cache_key]
            if now - cached_time < self.CACHE_TTL:
                return cached_data

        url = f"{self.BASE_URL}/simple/price"
        params = {"ids": coin_id, "vs_currencies": currency, "include_24hr_change": "true"}

        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if coin_id in data:
                result = {
                    "coin": coin_id,
                    "currency": currency,
                    "price": data[coin_id].get(currency),
                    "change_24h": data[coin_id].get(f"{currency}_24h_change"),
                }
                self.CACHE[cache_key] = (now, result)
                return result
        except requests.RequestException as e:
            print(f"API request failed for {coin_id}: {e}", file=sys.stderr)
        except ValueError as e:
            print(f"Failed to parse response for {coin_id}: {e}", file=sys.stderr)
        return None

    def _format_price(self, price: float | None, currency: str) -> str:
        """Format a price with an appropriate number of decimal places."""
        if price is None:
            return "N/A"
        if price >= 1000:
            return f"{price:.2f}"
        if price >= 1:
            return f"{price:.4f}"
        if price >= 0.01:
            return f"{price:.6f}"
        if price >= 0.00000001:
            return f"{price:.8f}"
        return repr(price)

    def get_prices(self, coin_ids: list[str], currency: str = "usd") -> list[dict[str, Any]]:
        """Get prices for multiple coins in a single API call."""
        if not coin_ids:
            return []
        
        url = f"{self.BASE_URL}/simple/price"
        cache_key = f"{','.join(sorted(coin_ids))}:{currency}"
        now = time.time()

        if cache_key in self.CACHE:
            cached_time, cached_data = self.CACHE[cache_key]
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
            results = []
            for coin_id in coin_ids:
                if coin_id in data:
                    results.append({
                        "coin": coin_id,
                        "currency": currency,
                        "price": data[coin_id].get(currency),
                        "change_24h": data[coin_id].get(f"{currency}_24h_change"),
                    })
            # Only cache if all requested coins were found
            if len(results) == len(coin_ids):
                self.CACHE[cache_key] = (now, results)
            return results
        except requests.RequestException as e:
            print(f"API request failed for batch price lookup: {e}", file=sys.stderr)
        except ValueError as e:
            print(f"Failed to parse response for batch price lookup: {e}", file=sys.stderr)
        return []


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
        click.echo(f"{symbol}: {checker._format_price(price, currency)} {currency.upper()} ({change_str})")


if __name__ == "__main__":
    main()
