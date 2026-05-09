"""Strategy document and registry helpers for workflow nodes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRATEGIES_DIR = PROJECT_ROOT / "docs" / "trading-strategies"
STRATEGIES_CONFIG_PATH = PROJECT_ROOT / "backend" / "config" / "strategies_config.json"


def read_strategies(market_regime: str = "Ranging", current_timeframes: List[str] | None = None, symbol: str | None = None) -> str:
    if current_timeframes is None:
        current_timeframes = ["M5"]

    strategies_text = ""
    try:
        config = json.loads(STRATEGIES_CONFIG_PATH.read_text(encoding="utf-8"))

        for strat in config.get("strategies", []):
            regime_match = market_regime in strat.get("allowed_regimes", [])
            ptf, _ = resolve_strategy_profile(strat, current_timeframes, symbol)
            timeframe_match = ptf is not None

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


def resolve_strategy_profile(strategy_contract: Dict[str, Any], current_timeframes: List[str], symbol: str | None = None) -> Tuple[str | None, List[str]]:
    """
    Finds the best matching profile for the given timeframes and symbol.
    Returns (primary_timeframe, confirmation_timeframes).
    Falls back to required_timeframes if no profiles match or exist.
    """
    if not current_timeframes:
        return None, []

    profiles = strategy_contract.get("profiles", [])
    if profiles:
        valid_profiles = []
        for profile in profiles:
            allowed_symbols = profile.get("allowed_symbols", [])
            if allowed_symbols and symbol and symbol not in allowed_symbols:
                continue

            ptf = profile.get("primary_timeframe")
            ctf = profile.get("confirmation_timeframes", [])
            required = [ptf] + ctf if ptf else ctf
            if set(required).issubset(set(current_timeframes)):
                valid_profiles.append((len(required), ptf, ctf))

        if valid_profiles:
            valid_profiles.sort(key=lambda x: x[0], reverse=True)
            return valid_profiles[0][1], valid_profiles[0][2]
        
        # If profiles are defined but none match (e.g. symbol gate blocked), don't fallback
        return None, []
                
    # Fallback for backward compatibility (only if no profiles are defined)
    required_timeframes = strategy_contract.get("required_timeframes")
    if required_timeframes and set(required_timeframes).issubset(set(current_timeframes)):
        ptf = required_timeframes[0]
        ctf = required_timeframes[1:] if len(required_timeframes) > 1 else []
        return ptf, ctf
        
    return None, []


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
