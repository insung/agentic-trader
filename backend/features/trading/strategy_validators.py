"""
Deterministic strategy gates that run after LLM decision making.

LLMs can summarize and choose a playbook, but these validators enforce that the
selected setup actually satisfies the strategy document with computed data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple


@dataclass(frozen=True)
class StrategyGateConfig:
    min_adx: float = 25.0
    max_cross_age_bars: int = 6
    min_sl_atr: float = 1.0
    ma_band_tolerance: float = 0.003
    bb_lookback_rows: int = 10
    bb_band_tolerance: float = 0.0015


def _strategy_name(strategy_hypothesis: Dict[str, Any]) -> str:
    return str(strategy_hypothesis.get("selected_strategy", "")).lower()


def _base_snapshot(indicator_data: Dict[str, Any]) -> Dict[str, Any]:
    if not indicator_data:
        return {}
    if "M15" in indicator_data:
        return indicator_data.get("M15", {})
    first_key = next(iter(indicator_data.keys()), None)
    if first_key is None:
        return {}
    return indicator_data.get(first_key, {})


def _sl_atr_ok(action: str, entry_price: float, sl_price: float, snapshot: Dict[str, Any], config: StrategyGateConfig) -> Tuple[bool, str]:
    latest = snapshot.get("latest", {})
    atr = latest.get("atr14")
    if not atr or atr <= 0:
        return False, "ATR14 is unavailable; cannot validate stop distance"
    sl_distance = abs(entry_price - sl_price)
    sl_atr = sl_distance / atr
    if sl_atr < config.min_sl_atr:
        return False, f"SL distance is too tight ({sl_atr:.2f} ATR, minimum {config.min_sl_atr:.2f} ATR)"
    return True, f"SL distance OK for {action} ({sl_atr:.2f} ATR)"


def _higher_timeframe_snapshots(indicator_data: Dict[str, Any], base_snapshot: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for snapshot in indicator_data.values():
        if snapshot is base_snapshot:
            continue
        yield snapshot


def _ma_has_higher_timeframe_conflict(action: str, indicator_data: Dict[str, Any], base_snapshot: Dict[str, Any]) -> Tuple[bool, str]:
    for snapshot in _higher_timeframe_snapshots(indicator_data, base_snapshot):
        latest = snapshot.get("latest", {})
        close = latest.get("close")
        ema20 = latest.get("ema20")
        ema50 = latest.get("ema50")
        if not all(value is not None for value in (close, ema20, ema50)):
            continue
        if action == "SELL" and ema20 > ema50 and close >= ema50:
            return True, "higher timeframe bullish conflict"
        if action == "SELL" and not (close < ema20 or ema20 < ema50):
            return True, "higher timeframe is not bearish enough for SELL"
        if action == "BUY" and ema20 < ema50 and close <= ema50:
            return True, "higher timeframe bearish conflict"
        if action == "BUY" and not (close > ema20 or ema20 > ema50):
            return True, "higher timeframe is not bullish enough for BUY"
    return False, ""


def _ma_is_exhausted_band_entry(action: str, latest: Dict[str, Any], config: StrategyGateConfig) -> Tuple[bool, str]:
    close = latest.get("close")
    upper = latest.get("bb_upper20")
    lower = latest.get("bb_lower20")
    rsi = latest.get("rsi14")
    if not all(value is not None for value in (close, upper, lower, rsi)):
        return False, ""

    tolerance = config.ma_band_tolerance
    if action == "SELL" and close <= lower * (1 + tolerance) and rsi <= 35:
        return True, "oversold lower-band exhaustion"
    if action == "BUY" and close >= upper * (1 - tolerance) and rsi >= 65:
        return True, "overbought upper-band exhaustion"
    return False, ""


def _validate_ma_crossover(action: str, snapshot: Dict[str, Any], indicator_data: Dict[str, Any], config: StrategyGateConfig) -> Tuple[bool, str]:
    latest = snapshot.get("latest", {})
    close = latest.get("close")
    ema20 = latest.get("ema20")
    ema50 = latest.get("ema50")
    adx = latest.get("adx14")
    cross_ages = snapshot.get("ema_cross_age_bars", {})

    if not all(value is not None for value in (close, ema20, ema50, adx)):
        return False, "MA Crossover requires close, EMA20, EMA50, and ADX14"
    if adx < config.min_adx:
        return False, f"ADX14 {adx:.2f} is below minimum trend strength {config.min_adx:.2f}"

    if action == "BUY":
        age = cross_ages.get("bullish")
        if not (ema20 > ema50 and close > ema20):
            return False, "BUY requires EMA20 > EMA50 and close > EMA20"
    elif action == "SELL":
        age = cross_ages.get("bearish")
        if not (ema20 < ema50 and close < ema20):
            return False, "SELL requires EMA20 < EMA50 and close < EMA20"
    else:
        return False, "MA Crossover only validates BUY or SELL"

    if age is None or age > config.max_cross_age_bars:
        return False, f"EMA crossover is stale or absent (age={age}, max={config.max_cross_age_bars})"

    has_conflict, conflict_reason = _ma_has_higher_timeframe_conflict(action, indicator_data, snapshot)
    if has_conflict:
        return False, conflict_reason

    is_exhausted, exhaustion_reason = _ma_is_exhausted_band_entry(action, latest, config)
    if is_exhausted:
        return False, exhaustion_reason

    return True, "MA Crossover setup confirmed by EMA position, recent cross, and ADX"


def _validate_bollinger_reversion(action: str, snapshot: Dict[str, Any], config: StrategyGateConfig) -> Tuple[bool, str]:
    rows = snapshot.get("recent_rows", [])[-config.bb_lookback_rows:]
    latest = snapshot.get("latest", {})
    if len(rows) < 3:
        return False, "Bollinger validation requires at least 3 recent rows"

    current = rows[-1]
    previous = rows[-2]
    close = current.get("close")
    open_ = current.get("open")
    high = current.get("high")
    low = current.get("low")
    upper = current.get("bb_upper20")
    lower = current.get("bb_lower20")
    ema20 = latest.get("ema20")
    ema50 = latest.get("ema50")
    rsi = latest.get("rsi14")
    if not all(value is not None for value in (close, open_, high, low, upper, lower, ema20, ema50, rsi)):
        return False, "Bollinger validation requires OHLC, bands, EMA20/50, and RSI14"

    range_size = max(high - low, 0.000001)
    close_position = (close - low) / range_size
    tolerance = config.bb_band_tolerance

    if action == "BUY":
        first_extreme = any(row.get("low") is not None and row.get("bb_lower20") is not None and row["low"] <= row["bb_lower20"] * (1 + tolerance) for row in rows[:-1])
        reversal_candle = close > open_ or close > previous.get("close", close)
        closes_off_low = close_position >= 0.45
        not_strong_downtrend = not (ema20 < ema50 and rsi < 45)
        if first_extreme and reversal_candle and closes_off_low and not_strong_downtrend:
            return True, "Bollinger long setup confirmed by lower-band extreme and reversal candle"
        return False, "BUY requires lower-band extreme, reversal candle, close off low, and no strong downtrend"

    if action == "SELL":
        first_extreme = any(row.get("high") is not None and row.get("bb_upper20") is not None and row["high"] >= row["bb_upper20"] * (1 - tolerance) for row in rows[:-1])
        reversal_candle = close < open_ or close < previous.get("close", close)
        closes_off_high = close_position <= 0.55
        not_strong_uptrend = not (ema20 > ema50 and rsi < 65)
        if first_extreme and reversal_candle and closes_off_high and not_strong_uptrend:
            return True, "Bollinger short setup confirmed by upper-band extreme and reversal candle"
        return False, "SELL requires upper-band extreme, reversal candle, close off high, and no unresolved strong uptrend"

    return False, "Bollinger strategy only validates BUY or SELL"


def validate_strategy_setup(
    action: str,
    entry_price: float,
    sl_price: float,
    strategy_hypothesis: Dict[str, Any],
    indicator_data: Dict[str, Any],
    config: StrategyGateConfig | None = None,
) -> Tuple[bool, str]:
    """Validate the LLM-selected setup against deterministic strategy conditions."""
    config = config or StrategyGateConfig()
    action = action.upper()
    strategy_name = _strategy_name(strategy_hypothesis)
    snapshot = _base_snapshot(indicator_data)
    if not snapshot:
        return False, "No indicator snapshot available for strategy validation"

    sl_ok, sl_reason = _sl_atr_ok(action, entry_price, sl_price, snapshot, config)
    if not sl_ok:
        return False, sl_reason

    if "moving average" in strategy_name or "ma crossover" in strategy_name:
        return _validate_ma_crossover(action, snapshot, indicator_data, config)
    if "bollinger" in strategy_name:
        return _validate_bollinger_reversion(action, snapshot, config)

    return False, f"Unsupported strategy for deterministic validation: {strategy_name or 'N/A'}"
