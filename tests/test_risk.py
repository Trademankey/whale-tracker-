from datetime import datetime, timedelta, timezone

from whaletracker.risk import RiskScorer


def test_wallet_history_filters_timestamp_with_or_precedence(tmp_path):
    scorer = RiskScorer(tmp_path / "risk.db")
    old_timestamp = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    new_timestamp = datetime.now(timezone.utc).isoformat()

    scorer.save_transaction(
        {
            "tx_hash": "old",
            "chain": "ethereum",
            "timestamp": old_timestamp,
            "from": "0xabc",
            "to": "0xdef",
            "value_usd": 1_000_000,
            "token": "ETH",
            "tx_type": "transfer",
            "risk_score": 0,
            "risk_level": "LOW",
            "exchange_context": None,
            "block_number": 1,
        }
    )
    scorer.save_transaction(
        {
            "tx_hash": "new",
            "chain": "ethereum",
            "timestamp": new_timestamp,
            "from": "0x123",
            "to": "0xabc",
            "value_usd": 1_000_000,
            "token": "ETH",
            "tx_type": "transfer",
            "risk_score": 0,
            "risk_level": "LOW",
            "exchange_context": None,
            "block_number": 2,
        }
    )

    history = scorer.get_wallet_history("0xabc", days=7)

    assert [row["tx_hash"] for row in history] == ["new"]


def test_sanctioned_address_is_critical(tmp_path):
    scorer = RiskScorer(tmp_path / "risk.db")
    score, level, flags = scorer.calculate_risk(
        {
            "from": "0x722122df12d4e14e13ac3b6895a86e84145b6967",
            "to": "0xabc",
            "value_usd": 500_000,
        },
        {"risk_flags": []},
        [],
    )

    assert score == 100
    assert level == "CRITICAL"
    assert "sanctions_list" in flags
