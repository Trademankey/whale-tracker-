from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .models import ChainConfig


CHAIN_CONFIGS: dict[str, ChainConfig] = {
    "ethereum": ChainConfig(
        id="ethereum",
        name="Ethereum",
        ws_url="wss://eth-mainnet.g.alchemy.com/v2/{key}",
        native_token="ETH",
        native_decimals=18,
        coingecko_id="ethereum",
        coingecko_platform="ethereum",
        required_key="ALCHEMY_API_KEY",
        block_time_seconds=12.0,
        threshold_usd=500_000,
    ),
    "arbitrum": ChainConfig(
        id="arbitrum",
        name="Arbitrum",
        ws_url="wss://arb-mainnet.g.alchemy.com/v2/{key}",
        native_token="ETH",
        native_decimals=18,
        coingecko_id="ethereum",
        coingecko_platform="arbitrum-one",
        required_key="ALCHEMY_API_KEY",
        block_time_seconds=0.5,
        threshold_usd=250_000,
    ),
    "base": ChainConfig(
        id="base",
        name="Base",
        ws_url="wss://base-mainnet.g.alchemy.com/v2/{key}",
        native_token="ETH",
        native_decimals=18,
        coingecko_id="ethereum",
        coingecko_platform="base",
        required_key="ALCHEMY_API_KEY",
        block_time_seconds=2.0,
        threshold_usd=100_000,
    ),
}


EXCHANGE_WALLETS: dict[str, dict[str, str]] = {
    "ethereum": {
        "0x28c6c06298d514db089934071355e5743bf21d60": "Binance",
        "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance",
        "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance",
        "0x0716a17fbaee714f1e902b10871db2b7e4a9b10a": "Coinbase",
        "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase",
        "0x8d37d2c5b23c68c1d27e9935d70d842e21c62b78": "Kraken",
        "0x1151314c646ce4e0efd76d1af4760ae66a9fe30f": "Bybit",
    },
    "arbitrum": {
        "0xf89d7b9c864f589bbf53a82105127622b35eacfd": "Binance",
    },
    "base": {
        "0x0b09c86260c12294e3b967d0b0c3c8c6c4ab5e49": "Coinbase",
    },
}


@dataclass(frozen=True)
class Settings:
    redis_url: str
    database_path: Path
    chains: tuple[str, ...]
    api_keys: dict[str, str]
    price_cache_ttl_seconds: int
    reconnect_base_delay_seconds: float
    reconnect_max_delay_seconds: float
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        chains = tuple(
            chain.strip()
            for chain in os.getenv("WHALE_CHAINS", "ethereum,arbitrum,base").split(",")
            if chain.strip()
        )
        api_keys = {
            name: value
            for name, value in {
                "ALCHEMY_API_KEY": os.getenv("ALCHEMY_API_KEY", ""),
            }.items()
            if value
        }
        return cls(
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            database_path=Path(os.getenv("WHALE_DB_PATH", "whale_data.db")),
            chains=chains,
            api_keys=api_keys,
            price_cache_ttl_seconds=int(os.getenv("PRICE_CACHE_TTL_SECONDS", "300")),
            reconnect_base_delay_seconds=float(os.getenv("RECONNECT_BASE_DELAY_SECONDS", "2")),
            reconnect_max_delay_seconds=float(os.getenv("RECONNECT_MAX_DELAY_SECONDS", "60")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )

    def validate(self) -> None:
        unknown_chains = [chain for chain in self.chains if chain not in CHAIN_CONFIGS]
        if unknown_chains:
            supported = ", ".join(sorted(CHAIN_CONFIGS))
            raise ValueError(f"Unsupported chains: {', '.join(unknown_chains)}. Supported: {supported}")

        missing = sorted(
            {
                CHAIN_CONFIGS[chain].required_key
                for chain in self.chains
                if CHAIN_CONFIGS[chain].required_key not in self.api_keys
            }
        )
        if missing:
            raise ValueError(f"Missing required environment variable(s): {', '.join(missing)}")


def load_env_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
