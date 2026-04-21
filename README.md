# Crypto Price Checker

A simple Python CLI tool for checking cryptocurrency prices using the CoinGecko API.

## Features

- Check current price of any cryptocurrency
- Compare multiple coins in one command
- Show 24h price change
- Cache results to avoid rate limiting

## Installation

```bash
pip install crypto-price-checker
```

Or from source:

```bash
git clone https://github.com/HrachShah/crypto-price-checker.git
cd crypto-price-checker
pip install -e .
```

## Usage

```bash
# Check Bitcoin price
crypto-price bitcoin

# Check multiple coins
crypto-price bitcoin ethereum solana

# Show in specific currency
crypto-price bitcoin --currency eur
```

## License

MIT
