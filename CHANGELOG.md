# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-21

### Added
- Initial release
- `CryptoPriceChecker` class for CoinGecko API interaction
- CLI with `crypto-price` command
- Support for multiple coins in a single command
- 24h price change display
- In-memory caching with 60-second TTL
- Currency conversion support (USD, EUR, etc.)

### Features
- Check current price of any cryptocurrency
- Compare multiple coins in one command
- Show 24h price change percentage
- Cache results to avoid rate limiting
- Configurable output currency