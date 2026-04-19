from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class RiskScorer:
    SANCTIONED_ADDRESSES = {
        "0x722122df12d4e14e13ac3b6895a86e84145b6967",
        "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",
        "0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936",
        "0x23773e65ed146a459791799d01336db287f25334",
    }

    def __init__(self, db_path: str | Path = "whale_data.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS whale_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tx_hash TEXT UNIQUE NOT NULL,
                    chain TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    from_addr TEXT NOT NULL,
                    to_addr TEXT NOT NULL,
                    value_usd REAL NOT NULL,
                    token_symbol TEXT NOT NULL,
                    tx_type TEXT NOT NULL,
                    risk_score REAL NOT NULL,
                    risk_level TEXT NOT NULL,
                    exchange_context TEXT,
                    block_number INTEGER NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_from_addr ON whale_transactions(from_addr)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_to_addr ON whale_transactions(to_addr)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON whale_transactions(timestamp)")

    def calculate_risk(
        self,
        tx: dict[str, Any],
        contract_analysis: dict[str, Any],
        wallet_history: list[dict[str, Any]],
    ) -> tuple[float, str, list[str]]:
        score = 0.0
        flags: list[str] = []
        from_addr = str(tx.get("from") or "").lower()
        to_addr = str(tx.get("to") or "").lower()
        value_usd = float(tx.get("value_usd") or 0)

        if from_addr in self.SANCTIONED_ADDRESSES or to_addr in self.SANCTIONED_ADDRESSES:
            score += 100
            flags.append("sanctions_list")

        if "mixer_usage" in contract_analysis.get("risk_flags", []):
            score += 90
            flags.append("mixer_usage")

        if contract_analysis.get("contract_category") == "bridge" and value_usd > 100_000:
            score += 30
            flags.append("large_bridge")

        recent = [row for row in wallet_history if _parse_timestamp(row["timestamp"]) > _utcnow() - timedelta(hours=24)]
        if len(recent) > 10:
            score += 20
            flags.append("high_velocity")

        blocks = [row["block_number"] for row in recent if row.get("block_number") is not None]
        if len(blocks) >= 4 and len(set(blocks)) <= len(blocks) * 0.5:
            score += 35
            flags.append("same_block_cluster")

        if value_usd in {100_000, 500_000, 1_000_000, 5_000_000}:
            score += 10
            flags.append("round_number")

        if tx.get("exchange_context"):
            score -= 15

        score = max(0, min(100, score))
        if score >= 80:
            level = "CRITICAL"
        elif score >= 60:
            level = "HIGH"
        elif score >= 30:
            level = "MEDIUM"
        else:
            level = "LOW"
        return score, level, flags

    def save_transaction(self, tx_data: dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO whale_transactions
                (tx_hash, chain, timestamp, from_addr, to_addr, value_usd,
                 token_symbol, tx_type, risk_score, risk_level, exchange_context, block_number)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tx_data["tx_hash"],
                    tx_data["chain"],
                    tx_data["timestamp"],
                    tx_data["from"],
                    tx_data["to"],
                    tx_data["value_usd"],
                    tx_data["token"],
                    tx_data["tx_type"],
                    tx_data["risk_score"],
                    tx_data["risk_level"],
                    tx_data.get("exchange_context"),
                    tx_data["block_number"],
                ),
            )

    def get_wallet_history(self, address: str, days: int = 7) -> list[dict[str, Any]]:
        since = (_utcnow() - timedelta(days=days)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM whale_transactions
                WHERE (from_addr = ? OR to_addr = ?)
                  AND timestamp > ?
                ORDER BY timestamp DESC
                """,
                (address.lower(), address.lower(), since),
            ).fetchall()
        return [dict(row) for row in rows]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
