from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SignalType(Enum):
    FUNDING = "funding"
    OI = "oi"
    LIQ = "liq"
    NEWS = "news"
    SENTIMENT = "sentiment"
    CVD = "cvd"
    EQUITY = "equity"
    VIX = "vix"
    DXY = "dxy"
    ETF_FLOW = "etf_flow"
    WHALE_TX = "whale_tx"
    WHALE_ACCUMULATION = "whale_accumulation"
    WHALE_DISTRIBUTION = "whale_distribution"
    EXCHANGE_FLOW = "exchange_flow"
    SMART_MONEY = "smart_money"
    COORDINATED_MOVEMENT = "coordinated_movement"
    RISK_ALERT = "risk_alert"


@dataclass(frozen=True)
class DataPoint:
    source: str
    data_type: str
    symbol: str
    value: dict[str, Any]
    ts: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    signal_score: float | None = None
    chain: str | None = None
    risk_level: str | None = None


@dataclass(frozen=True)
class ChainConfig:
    id: str
    name: str
    ws_url: str
    native_token: str
    native_decimals: int
    coingecko_id: str
    coingecko_platform: str | None
    required_key: str
    block_time_seconds: float
    threshold_usd: float
