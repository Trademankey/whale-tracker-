from __future__ import annotations

import json
from typing import Protocol

import redis.asyncio as redis

from .models import DataPoint


class Publisher(Protocol):
    async def publish(self, dp: DataPoint) -> None:
        ...


class RedisPublisher:
    def __init__(self, redis_url: str = "redis://localhost:6379/0", ttl_seconds: int = 300):
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self.r = redis.from_url(redis_url, decode_responses=True)

    async def ping(self) -> None:
        await self.r.ping()

    async def publish(self, dp: DataPoint) -> None:
        key = f"scraper:{dp.data_type}:{dp.symbol}"
        payload = {
            **dp.value,
            "ts": dp.ts,
            "source": dp.source,
        }
        if dp.chain:
            payload["chain"] = dp.chain
        if dp.risk_level:
            payload["risk_level"] = dp.risk_level
        if dp.signal_score is not None:
            payload["signal_score"] = dp.signal_score

        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        await self.r.set(key, encoded, ex=self.ttl_seconds)
        await self.r.publish(f"signal:{dp.data_type}", encoded)
        if dp.risk_level == "CRITICAL":
            await self.r.publish("alerts:critical", encoded)
            await self.r.set(f"alert:critical:{dp.symbol}", encoded, ex=3600)

    async def close(self) -> None:
        await self.r.aclose()
