from whaletracker.contracts import ContractAnalyzer


def test_detects_erc20_transfer():
    tx = {
        "to": "0x0000000000000000000000000000000000000001",
        "gas": "0x5209",
        "input": (
            "0xa9059cbb"
            "0000000000000000000000001111111111111111111111111111111111111111"
            "0000000000000000000000000000000000000000000000000de0b6b3a7640000"
        ),
    }

    result = ContractAnalyzer().analyze(tx)

    assert result["tx_type"] == "token_transfer"
    assert result["token_to"] == "0x1111111111111111111111111111111111111111"
    assert result["token_amount_raw"] == 1_000_000_000_000_000_000


def test_detects_known_mixer_contract():
    tx = {
        "to": "0x722122df12d4e14e13ac3b6895a86e84145b6967",
        "gas": "0x100000",
        "input": "0xb214faa5",
    }

    result = ContractAnalyzer().analyze(tx)

    assert result["contract_category"] == "mixer"
    assert "sanctions_list" in result["risk_flags"]
    assert "mixer_usage" in result["risk_flags"]
