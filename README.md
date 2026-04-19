# Scraper Whale Tracker

Real-time EVM whale transaction tracker with risk scoring, Redis publishing, and SQLite history.

## What It Does

- Subscribes to Alchemy mined transaction streams for Ethereum, Arbitrum, and Base.
- Filters transactions by chain-specific USD whale thresholds.
- Prices native assets and ERC-20 transfers through CoinGecko with a cache.
- Classifies DEX, bridge, mixer, and token transfer activity.
- Scores risk with sanctions, mixer, bridge, velocity, and exchange-flow signals.
- Publishes normalized signals into Redis for the rest of your scraper/trading stack.
- Persists whale history in SQLite for repeat-wallet and velocity analysis.

## Setup

```bash
cd /Users/kryptoknight/Desktop/Scraper-Whaletracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your own API key and Redis URL. Do not commit real keys.

## Run

```bash
python -m whaletracker.main
```

Redis must be running before startup. The app validates required environment variables and checks Redis connectivity before opening WebSocket listeners.

## Test

```bash
pip install -r requirements-dev.txt
pytest
```
