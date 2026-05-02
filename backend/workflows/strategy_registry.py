"""Strategy document and registry helpers for workflow nodes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRATEGIES_DIR = PROJECT_ROOT / "docs" / "trading-strategies"
STRATEGIES_CONFIG_PATH = PROJECT_ROOT / "backend" / "config" / "strategies_config.json"


def read_strategies(market_regime: str = "Ranging", current_timeframes: List[str] | None = None) -> str:
    if current_timeframes is None:
        current_timeframes = ["M5"]

    strategies_text = ""
    try:
        config = json.loads(STRATEGIES_CONFIG_PATH.read_text(encoding="utf-8"))

        for strat in config.get("strategies", []):
            regime_match = market_regime in strat.get("allowed_regimes", [])
            required_timeframes = strat.get("required_timeframes", current_timeframes)
            timeframe_match = set(required_timeframes).issubset(set(current_timeframes))

            if regime_match and timeframe_match:
                filepath = STRATEGIES_DIR / strat.get("file", "")
                if filepath.exists():
                    strategies_text += f"\n--- {strat.get('name')} ---\n"
                    strategies_text += filepath.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"Error reading strategies config: {exc}")
        if STRATEGIES_DIR.exists():
            for filepath in STRATEGIES_DIR.glob("*.md"):
                strategies_text += f"\n--- {filepath.name} ---\n"
                strategies_text += filepath.read_text(encoding="utf-8")

    if not strategies_text.strip():
        strategies_text = "No matching strategies found for current market regime."

    return strategies_text


def normalize_strategy_key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def load_strategy_contract(strategy_name: str) -> Dict[str, Any]:
    """Load registry metadata for a strategy by display name or file slug."""
    if not strategy_name:
        return {}

    target = normalize_strategy_key(strategy_name)
    try:
        config = json.loads(STRATEGIES_CONFIG_PATH.read_text(encoding="utf-8"))
        for strat in config.get("strategies", []):
            candidates = [strat.get("name", ""), strat.get("file", "")]
            for candidate in candidates:
                if not candidate:
                    continue
                normalized = normalize_strategy_key(candidate)
                if normalized == target or normalized.startswith(target) or target.startswith(normalized):
                    return strat
    except Exception as exc:
        print(f"Failed to load strategy contract for {strategy_name}: {exc}")
    return {}
