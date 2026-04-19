from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
import websockets

from .config import CHAIN_CONFIGS, EXCHANGE_WALLETS, Settings
from .contracts import ContractAnalyzer
from .models import ChainConfig, DataPoint, SignalType
from .publisher import Publisher
from .risk import RiskScorer

log = logging.getLogger(__name__)


class WhaleTracker:
    def __init__(self, publisher: Publisher, settings: Settings):
        self.publisher = publisher
        self.settings = settings
        self.contract_analyzer = ContractAnalyzer()
        self.risk_scorer = RiskScorer(settings.database_path)
        self.price_cache: dict[str, tuple[float, datetime]] = {}
        self.recent_whale_txs: list[dict[str, Any]] = []
        self.coordination_window = timedelta(hours=1)
        self.session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self.settings.validate()
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            self.session = session
            await asyncio.gather(*(self.track_chain(chain) for chain in self.settings.chains))

    async def track_chain(self, chain_id: str) -> None:
        config = CHAIN_CONFIGS[chain_id]
        api_key = self.settings.api_keys[config.required_key]
        ws_url = config.ws_url.format(key=api_key)
        attempts = 0
        log.info("Starting %s listener", config.name)

        while True:
            try:
                async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20, close_timeout=10) as ws:
                    attempts = 0
                    await self._subscribe_evm(ws)
                    async for message in ws:
                        await self._process_message(message, chain_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                attempts += 1
                delay = self._backoff_delay(attempts)
                log.exception("%s listener disconnected; reconnecting in %.1fs", chain_id, delay)
                await asyncio.sleep(delay)

    async def _subscribe_evm(self, ws: Any) -> None:
        subscribe_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_subscribe",
            "params": [
                "alchemy_minedTransactions",
                {"addresses": [], "includeRemoved": False, "hashesOnly": False},
            ],
        }
        await ws.send(json.dumps(subscribe_msg))

    async def _process_message(self, message: str, chain_id: str) -> None:
        data = json.loads(message)
        tx_data = self._extract_transaction(data)
        if tx_data is None:
            return

        config = CHAIN_CONFIGS[chain_id]
        enriched = await self._enrich_transaction(tx_data, config)
        if not enriched or enriched["value_usd"] < config.threshold_usd:
            return

        contract_analysis = self.contract_analyzer.analyze(tx_data)
        exchange_ctx = self._check_exchange_flow(enriched["from"], enriched["to"], chain_id)
        enriched["exchange_context"] = exchange_ctx
        wallet_history = self.risk_scorer.get_wallet_history(enriched["from"], days=7)
        risk_score, risk_level, risk_flags = self.risk_scorer.calculate_risk(
            enriched,
            contract_analysis,
            wallet_history,
        )
        whale_data = {
            **enriched,
            "tx_type": contract_analysis["tx_type"],
            "contract_name": contract_analysis.get("contract_name"),
            "contract_category": contract_analysis.get("contract_category"),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_flags": risk_flags,
            "method_id": contract_analysis.get("method_id"),
        }
        self.risk_scorer.save_transaction(whale_data)
        await self._publish_to_redis(whale_data, chain_id)
        await self._check_coordination(whale_data)
        self._log_alert(whale_data)

    def _extract_transaction(self, data: dict[str, Any]) -> dict[str, Any] | None:
        params = data.get("params")
        if not isinstance(params, dict):
            return None
        result = params.get("result")
        if not isinstance(result, dict):
            return None
        if "transaction" in result and isinstance(result["transaction"], dict):
            return result["transaction"]
        if "hash" in result:
            return result
        return None

    async def _enrich_transaction(self, tx_data: dict[str, Any], config: ChainConfig) -> dict[str, Any] | None:
        tx_hash = tx_data.get("hash")
        from_addr = str(tx_data.get("from") or "").lower()
        to_addr = str(tx_data.get("to") or "0x0").lower()
        if not tx_hash or not from_addr:
            return None

        value_wei = _hex_to_int(tx_data.get("value"), default=0)
        value_native = value_wei / (10**config.native_decimals)
        value_usd = value_native * await self._get_cached_price(config.id)
        token = config.native_token
        token_contract = None

        input_data = str(tx_data.get("input") or "0x")
        if input_data.startswith("0xa9059cbb") and len(input_data) >= 138:
            token_contract = to_addr
            token_amount = int(input_data[74:138], 16) / 1e18
            token_price = await self._get_cached_price(config.id, token_contract)
            if token_price > 0:
                value_usd = token_amount * token_price
                token = token_contract

        return {
            "tx_hash": tx_hash,
            "from": from_addr,
            "to": to_addr,
            "value_native": value_native,
            "value_usd": value_usd,
            "token": token,
            "token_contract": token_contract,
            "gas_price_gwei": _hex_to_int(tx_data.get("gasPrice"), default=0) / 1e9,
            "block_number": _hex_to_int(tx_data.get("blockNumber"), default=0),
            "chain": config.id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _get_cached_price(self, chain: str, token: str | None = None) -> float:
        cache_key = f"{chain}:{token or 'native'}"
        cached = self.price_cache.get(cache_key)
        if cached:
            price, cached_at = cached
            if datetime.now(timezone.utc) - cached_at < timedelta(seconds=self.settings.price_cache_ttl_seconds):
                return price

        price = await self._fetch_price(chain, token)
        if price > 0:
            self.price_cache[cache_key] = (price, datetime.now(timezone.utc))
        return price

    async def _fetch_price(self, chain: str, token: str | None) -> float:
        if self.session is None:
            raise RuntimeError("HTTP session is not initialized")
        config = CHAIN_CONFIGS[chain]
        if token:
            if not config.coingecko_platform:
                return 0
            url = f"https://api.coingecko.com/api/v3/simple/token_price/{config.coingecko_platform}"
            params = {"contract_addresses": token, "vs_currencies": "usd"}
        else:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {"ids": config.coingecko_id, "vs_currencies": "usd"}

        try:
            async with self.session.get(url, params=params) as resp:
                if resp.status == 429:
                    log.warning("CoinGecko rate limit hit")
                    return 0
                resp.raise_for_status()
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            log.exception("Failed to fetch price for chain=%s token=%s", chain, token or "native")
            return 0

        if token:
            return float(data.get(token.lower(), {}).get("usd") or 0)
        return float(data.get(config.coingecko_id, {}).get("usd") or 0)

    def _check_exchange_flow(self, from_addr: str, to_addr: str, chain: str) -> str | None:
        chain_exchanges = EXCHANGE_WALLETS.get(chain, {})
        if from_addr in chain_exchanges:
            return f"outflow_{chain_exchanges[from_addr]}"
        if to_addr in chain_exchanges:
            return f"inflow_{chain_exchanges[to_addr]}"
        return None

    async def _publish_to_redis(self, whale_data: dict[str, Any], chain_id: str) -> None:
        if whale_data["exchange_context"]:
            signal_type = SignalType.EXCHANGE_FLOW.value
        elif whale_data["risk_level"] in {"HIGH", "CRITICAL"}:
            signal_type = SignalType.RISK_ALERT.value
        elif whale_data.get("contract_category") in {"dex", "bridge"}:
            signal_type = SignalType.SMART_MONEY.value
        else:
            signal_type = SignalType.WHALE_TX.value

        await self.publisher.publish(
            DataPoint(
                source=f"whale_tracker_{chain_id}",
                data_type=signal_type,
                symbol=whale_data["token"],
                value={
                    "tx_hash": whale_data["tx_hash"],
                    "from": whale_data["from"],
                    "to": whale_data["to"],
                    "value_usd": whale_data["value_usd"],
                    "value_native": whale_data["value_native"],
                    "exchange_context": whale_data["exchange_context"],
                    "contract_category": whale_data.get("contract_category"),
                    "contract_name": whale_data.get("contract_name"),
                    "tx_type": whale_data["tx_type"],
                    "risk_score": whale_data["risk_score"],
                    "risk_flags": whale_data["risk_flags"],
                },
                chain=chain_id,
                risk_level=whale_data["risk_level"],
                signal_score=self._calculate_signal_score(whale_data),
            )
        )

    def _calculate_signal_score(self, whale_data: dict[str, Any]) -> float:
        score = 0.0
        usd = float(whale_data["value_usd"])
        if usd > 10_000_000:
            score += 0.4
        elif usd > 1_000_000:
            score += 0.3
        elif usd > 500_000:
            score += 0.2

        exchange_context = whale_data.get("exchange_context") or ""
        if "inflow" in exchange_context:
            score += 0.3
        elif "outflow" in exchange_context:
            score += 0.2

        score += {"LOW": 0.2, "MEDIUM": 0.1, "HIGH": 0.0, "CRITICAL": -0.1}.get(
            whale_data["risk_level"],
            0,
        )
        return min(1.0, max(0.0, score))

    async def _check_coordination(self, whale_data: dict[str, Any]) -> None:
        self.recent_whale_txs.append(whale_data)
        cutoff = datetime.now(timezone.utc) - self.coordination_window
        self.recent_whale_txs = [
            tx for tx in self.recent_whale_txs if datetime.fromisoformat(tx["timestamp"]) > cutoff
        ]
        same_token_txs = [tx for tx in self.recent_whale_txs if tx["token"] == whale_data["token"]]
        unique_whales = len({tx["from"] for tx in same_token_txs})
        if unique_whales < 3:
            return

        total_volume = sum(float(tx["value_usd"]) for tx in same_token_txs)
        await self.publisher.publish(
            DataPoint(
                source="whale_tracker_coordination",
                data_type=SignalType.COORDINATED_MOVEMENT.value,
                symbol=whale_data["token"],
                value={
                    "whale_count": unique_whales,
                    "total_volume_usd": total_volume,
                    "transactions": len(same_token_txs),
                    "time_window_minutes": int(self.coordination_window.total_seconds() / 60),
                },
                chain=whale_data["chain"],
                risk_level="HIGH",
                signal_score=0.9,
            )
        )

    def _log_alert(self, whale_data: dict[str, Any]) -> None:
        log.info(
            "whale_tx chain=%s usd=%.0f token=%s risk=%s tx=%s from=%s to=%s type=%s exchange=%s",
            whale_data["chain"],
            whale_data["value_usd"],
            whale_data["token"],
            whale_data["risk_level"],
            whale_data["tx_hash"],
            whale_data["from"],
            whale_data["to"],
            whale_data["tx_type"],
            whale_data["exchange_context"],
        )

    def _backoff_delay(self, attempts: int) -> float:
        base = self.settings.reconnect_base_delay_seconds
        cap = self.settings.reconnect_max_delay_seconds
        return min(cap, base * (2 ** min(attempts, 6))) + random.uniform(0, 1)


def _hex_to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value), 16)
    except (TypeError, ValueError):
        return default
