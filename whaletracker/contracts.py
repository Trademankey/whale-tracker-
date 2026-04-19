from __future__ import annotations

from typing import Any


class ContractAnalyzer:
    METHOD_SIGNATURES = {
        "0x38ed1739": ("swapExactTokensForTokens", "swap"),
        "0x8803dbee": ("swapTokensForExactTokens", "swap"),
        "0x7ff36ab5": ("swapExactETHForTokens", "swap"),
        "0x18cbafe5": ("swapExactTokensForETH", "swap"),
        "0xe8e33700": ("addLiquidity", "liquidity_add"),
        "0xf305d719": ("addLiquidityETH", "liquidity_add"),
        "0xbaa2abde": ("removeLiquidity", "liquidity_remove"),
        "0x02751cec": ("removeLiquidityETH", "liquidity_remove"),
        "0xa694fc3a": ("stake", "stake"),
        "0x2e1a7d4d": ("withdraw", "unstake"),
        "0x8e9b1aef": ("bridge", "bridge"),
        "0xb214faa5": ("deposit", "mixer"),
        "0x21a0adb6": ("withdraw", "mixer"),
    }

    KNOWN_CONTRACTS = {
        "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": ("Uniswap V2", "dex"),
        "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": ("Uniswap V3", "dex"),
        "0x10ed43c718714eb63d5aa57b78b54704e256024e": ("PancakeSwap", "dex"),
        "0x13f4ea83d0bd40e75ce625ae38b47cef98bfa3d6": ("SushiSwap", "dex"),
        "0x99c9fc46f92e8a1c0dec1b1747d010903e884be1": ("Optimism Bridge", "bridge"),
        "0x4dbd4fc535ac27206064b68ffcf827b0a60bab3f": ("Arbitrum Bridge", "bridge"),
        "0x8e57ec5be3a31d36fd0e3f8ecb301b0b60546c6c": ("Polygon Bridge", "bridge"),
        "0x722122df12d4e14e13ac3b6895a86e84145b6967": ("Tornado Cash", "mixer"),
        "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf": ("Tornado Cash", "mixer"),
    }

    def analyze(self, tx: dict[str, Any]) -> dict[str, Any]:
        to_addr = str(tx.get("to") or "").lower()
        input_data = str(tx.get("input") or "0x")
        method_id = input_data[:10] if len(input_data) >= 10 else None
        gas = _hex_to_int(tx.get("gas"), default=0)

        result: dict[str, Any] = {
            "tx_type": "transfer",
            "is_contract": False,
            "contract_name": None,
            "contract_category": None,
            "method_name": None,
            "method_id": method_id,
            "risk_flags": [],
        }

        if to_addr and gas > 21_000:
            result["is_contract"] = True
            if to_addr in self.KNOWN_CONTRACTS:
                name, category = self.KNOWN_CONTRACTS[to_addr]
                result["contract_name"] = name
                result["contract_category"] = category
                if category == "mixer":
                    result["risk_flags"].append("sanctions_list")

            if method_id in self.METHOD_SIGNATURES:
                method_name, tx_type = self.METHOD_SIGNATURES[method_id]
                result["method_name"] = method_name
                result["tx_type"] = tx_type
                if tx_type == "mixer":
                    result["risk_flags"].append("mixer_usage")

        if input_data.startswith("0xa9059cbb") and len(input_data) >= 138:
            result["tx_type"] = "token_transfer"
            result["token_to"] = "0x" + input_data[34:74]
            result["token_amount_raw"] = int(input_data[74:138], 16)

        return result


def _hex_to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value), 16)
    except (TypeError, ValueError):
        return default
