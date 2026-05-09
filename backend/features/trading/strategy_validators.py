"""
Deterministic strategy gates that run after LLM decision making.

LLMs can summarize and choose a playbook, but these validators enforce that the
selected setup actually satisfies the strategy document with computed data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Tuple, Optional, List


@dataclass(frozen=True)
class StrategyGateConfig:
    min_adx: float = 25.0
    max_cross_age_bars: int = 6
    min_sl_atr: float = 1.0
    ma_band_tolerance: float = 0.003
    ma_late_chase_band_atr: float = 0.5
    ma_late_chase_sell_rsi: float = 45.0
    ma_late_chase_buy_rsi: float = 55.0
    bb_lookback_rows: int = 10
    bb_band_tolerance: float = 0.0015
    rsi_pullback_buy: float = 50.0
    rsi_pullback_sell: float = 50.0
    rsi_lookback_candles: int = 3
    min_body_ratio: float = 0.3


ValidatorReturnType = Tuple[bool, str, Optional[float], Optional[float]]
ValidatorFunction = Callable[[str, float, float, Dict[str, Any], Dict[str, Any], StrategyGateConfig, Optional[List[str]]], ValidatorReturnType]


def _strategy_name(strategy_hypothesis: Dict[str, Any]) -> str:
    return str(strategy_hypothesis.get("selected_strategy", "")).lower()


def _base_snapshot(indicator_data: Dict[str, Any], primary_timeframe: str | None = None) -> Dict[str, Any]:
    if not indicator_data:
        return {}
    if primary_timeframe and primary_timeframe in indicator_data:
        return indicator_data[primary_timeframe]
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


def _higher_timeframe_snapshots(indicator_data: Dict[str, Any], base_snapshot: Dict[str, Any], confirmation_timeframes: List[str] | None = None) -> Iterable[Dict[str, Any]]:
    if confirmation_timeframes:
        for tf in confirmation_timeframes:
            if tf in indicator_data:
                yield indicator_data[tf]
    else:
        for snapshot in indicator_data.values():
            if snapshot is base_snapshot:
                continue
            yield snapshot


def _ma_has_higher_timeframe_conflict(action: str, indicator_data: Dict[str, Any], base_snapshot: Dict[str, Any], confirmation_timeframes: List[str] | None = None) -> Tuple[bool, str]:
    for snapshot in _higher_timeframe_snapshots(indicator_data, base_snapshot, confirmation_timeframes):
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


def _ma_is_late_band_chase(action: str, latest: Dict[str, Any], config: StrategyGateConfig) -> Tuple[bool, str]:
    close = latest.get("close")
    atr = latest.get("atr14")
    upper = latest.get("bb_upper20")
    lower = latest.get("bb_lower20")
    rsi = latest.get("rsi14")
    if not all(value is not None for value in (close, atr, upper, lower, rsi)):
        return False, ""
    if atr <= 0:
        return False, ""

    band_room = config.ma_late_chase_band_atr * atr
    if action == "SELL" and close <= lower + band_room and rsi <= config.ma_late_chase_sell_rsi:
        return True, "late SELL chase near lower Bollinger band"
    if action == "BUY" and close >= upper - band_room and rsi >= config.ma_late_chase_buy_rsi:
        return True, "late BUY chase near upper Bollinger band"
    return False, ""


def _validate_ma_crossover(action: str, entry_price: float, sl_price: float, snapshot: Dict[str, Any], indicator_data: Dict[str, Any], config: StrategyGateConfig, confirmation_timeframes: List[str] | None = None) -> ValidatorReturnType:
    latest = snapshot.get("latest", {})
    close = latest.get("close")
    ema20 = latest.get("ema20")
    ema50 = latest.get("ema50")
    adx = latest.get("adx14")
    cross_ages = snapshot.get("ema_cross_age_bars", {})

    if not all(value is not None for value in (close, ema20, ema50, adx)):
        return False, "MA Crossover requires close, EMA20, EMA50, and ADX14", None, None
    if adx < config.min_adx:
        return False, f"ADX14 {adx:.2f} is below minimum trend strength {config.min_adx:.2f}", None, None

    if action == "BUY":
        age = cross_ages.get("bullish")
        if not (ema20 > ema50 and close > ema20):
            return False, "BUY requires EMA20 > EMA50 and close > EMA20", None, None
    elif action == "SELL":
        age = cross_ages.get("bearish")
        if not (ema20 < ema50 and close < ema20):
            return False, "SELL requires EMA20 < EMA50 and close < EMA20", None, None
    else:
        return False, "MA Crossover only validates BUY or SELL", None, None

    if age is None or age > config.max_cross_age_bars:
        return False, f"EMA crossover is stale or absent (age={age}, max={config.max_cross_age_bars})", None, None

    has_conflict, conflict_reason = _ma_has_higher_timeframe_conflict(action, indicator_data, snapshot, confirmation_timeframes)
    if has_conflict:
        return False, conflict_reason, None, None

    is_exhausted, exhaustion_reason = _ma_is_exhausted_band_entry(action, latest, config)
    if is_exhausted:
        return False, exhaustion_reason, None, None

    is_late_chase, late_chase_reason = _ma_is_late_band_chase(action, latest, config)
    if is_late_chase:
        return False, late_chase_reason, None, None

    return True, "MA Crossover setup confirmed by EMA position, recent cross, and ADX", None, None


def _validate_bollinger_reversion(action: str, entry_price: float, sl_price: float, snapshot: Dict[str, Any], indicator_data: Dict[str, Any], config: StrategyGateConfig, confirmation_timeframes: List[str] | None = None) -> ValidatorReturnType:
    rows = snapshot.get("recent_rows", [])[-config.bb_lookback_rows:]
    latest = snapshot.get("latest", {})
    if len(rows) < 3:
        return False, "Bollinger validation requires at least 3 recent rows", None, None

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
        return False, "Bollinger validation requires OHLC, bands, EMA20/50, and RSI14", None, None

    range_size = max(high - low, 0.000001)
    close_position = (close - low) / range_size
    tolerance = config.bb_band_tolerance

    if action == "BUY":
        first_extreme = any(row.get("low") is not None and row.get("bb_lower20") is not None and row["low"] <= row["bb_lower20"] * (1 + tolerance) for row in rows[:-1])
        reversal_candle = close > open_ or close > previous.get("close", close)
        closes_off_low = close_position >= 0.45
        not_strong_downtrend = not (ema20 < ema50 and rsi < 45)
        if first_extreme and reversal_candle and closes_off_low and not_strong_downtrend:
            return True, "Bollinger long setup confirmed by lower-band extreme and reversal candle", None, None
        return False, "BUY requires lower-band extreme, reversal candle, close off low, and no strong downtrend", None, None

    if action == "SELL":
        first_extreme = any(row.get("high") is not None and row.get("bb_upper20") is not None and row["high"] >= row["bb_upper20"] * (1 - tolerance) for row in rows[:-1])
        reversal_candle = close < open_ or close < previous.get("close", close)
        closes_off_high = close_position <= 0.55
        not_strong_uptrend = not (ema20 > ema50 and rsi < 65)
        if first_extreme and reversal_candle and closes_off_high and not_strong_uptrend:
            return True, "Bollinger short setup confirmed by upper-band extreme and reversal candle", None, None
        return False, "SELL requires upper-band extreme, reversal candle, close off high, and no unresolved strong uptrend", None, None

    return False, "Bollinger strategy only validates BUY or SELL", None, None


def _validate_rsi_trend_pullback(action: str, entry_price: float, sl_price: float, snapshot: Dict[str, Any], indicator_data: Dict[str, Any], config: StrategyGateConfig, confirmation_timeframes: List[str] | None = None) -> ValidatorReturnType:
    latest = snapshot.get("latest", {})
    close = latest.get("close")
    open_ = latest.get("open")
    high = latest.get("high")
    low = latest.get("low")
    ema20 = latest.get("ema20")
    ema50 = latest.get("ema50")
    adx = latest.get("adx14")
    atr = latest.get("atr14")

    if not all(value is not None for value in (close, open_, high, low, ema20, ema50, adx, atr)):
        return False, "RSI Pullback requires OHLC, EMA20/50, ADX14, and ATR14", None, None

    if adx < config.min_adx:
        return False, f"ADX14 {adx:.2f} is below minimum trend strength {config.min_adx:.2f}", None, None

    candle_length = high - low
    body_size = abs(close - open_)
    if candle_length == 0 or (body_size / candle_length) < config.min_body_ratio:
        return False, "Candle body ratio is too small (fake rebound)", None, None

    recent_rows = snapshot.get("recent_rows", [])[-config.rsi_lookback_candles:]
    if not recent_rows:
        return False, "Not enough recent rows for RSI pullback validation", None, None

    # H1 Trend Filter (Conflict Check)
    has_conflict, conflict_reason = _ma_has_higher_timeframe_conflict(action, indicator_data, snapshot, confirmation_timeframes)
    if has_conflict:
        return False, conflict_reason, None, None

    overridden_sl: float | None = None
    overridden_tp: float | None = None

    if action == "BUY":
        if not (ema20 > ema50 and close > ema20 and close > open_):
            return False, "BUY requires EMA20 > EMA50, close > EMA20, and bullish candle", None, None
        
        pulled_back = any(row.get("rsi14") is not None and row["rsi14"] < config.rsi_pullback_buy for row in recent_rows)
        if not pulled_back:
            return False, f"No RSI pullback below {config.rsi_pullback_buy} in the last {config.rsi_lookback_candles} candles", None, None

        # SL Override Calculation
        min_low = min((row.get("low", float("inf")) for row in recent_rows), default=low)
        swing_low_sl = min_low - (0.2 * atr)
        min_atr_sl = entry_price - (1.0 * atr)
        conservative_sl = min(swing_low_sl, min_atr_sl)

        if sl_price > conservative_sl:
            overridden_sl = round(conservative_sl, 5)
            # Maintain RR 2.0
            expected_loss = entry_price - overridden_sl
            overridden_tp = round(entry_price + (expected_loss * 2.0), 5)
            sl_reason_suffix = f" (SL overridden from {sl_price} to {overridden_sl})"
        else:
            sl_reason_suffix = ""

        return True, "RSI Trend Pullback BUY setup confirmed" + sl_reason_suffix, overridden_sl, overridden_tp

    elif action == "SELL":
        if not (ema20 < ema50 and close < ema20 and close < open_):
            return False, "SELL requires EMA20 < EMA50, close < EMA20, and bearish candle", None, None
        
        pulled_back = any(row.get("rsi14") is not None and row["rsi14"] > config.rsi_pullback_sell for row in recent_rows)
        if not pulled_back:
            return False, f"No RSI pullback above {config.rsi_pullback_sell} in the last {config.rsi_lookback_candles} candles", None, None

        # SL Override Calculation
        max_high = max((row.get("high", -float("inf")) for row in recent_rows), default=high)
        swing_high_sl = max_high + (0.2 * atr)
        min_atr_sl = entry_price + (1.0 * atr)
        conservative_sl = max(swing_high_sl, min_atr_sl)

        if sl_price < conservative_sl:
            overridden_sl = round(conservative_sl, 5)
            # Maintain RR 2.0
            expected_loss = overridden_sl - entry_price
            overridden_tp = round(entry_price - (expected_loss * 2.0), 5)
            sl_reason_suffix = f" (SL overridden from {sl_price} to {overridden_sl})"
        else:
            sl_reason_suffix = ""

        return True, "RSI Trend Pullback SELL setup confirmed" + sl_reason_suffix, overridden_sl, overridden_tp

    return False, "RSI Trend Pullback only validates BUY or SELL", None, None


VALIDATOR_REGISTRY: Dict[str, ValidatorFunction] = {
    "moving average": _validate_ma_crossover,
    "ma crossover": _validate_ma_crossover,
    "bollinger": _validate_bollinger_reversion,
    "rsi trend pullback": _validate_rsi_trend_pullback,
}


def validate_strategy_setup(
    action: str,
    entry_price: float,
    sl_price: float,
    strategy_hypothesis: Dict[str, Any],
    indicator_data: Dict[str, Any],
    config: StrategyGateConfig | None = None,
    primary_timeframe: str | None = None,
    confirmation_timeframes: List[str] | None = None,
) -> ValidatorReturnType:
    """Validate the LLM-selected setup against deterministic strategy conditions.
    
    Returns:
        (is_valid, reason, overridden_sl, overridden_tp)
    """
    config = config or StrategyGateConfig()
    action = action.upper()
    strategy_name = _strategy_name(strategy_hypothesis)
    snapshot = _base_snapshot(indicator_data, primary_timeframe)
    
    if not snapshot:
        return False, "No indicator snapshot available for strategy validation", None, None

    # Check basic SL distance first, unless the validator handles override
    sl_ok, sl_reason = _sl_atr_ok(action, entry_price, sl_price, snapshot, config)
    if not sl_ok:
        # If sl is too tight, we still let the specific validator run because it might override it
        pass

    for key, validator in VALIDATOR_REGISTRY.items():
        if key in strategy_name:
            is_valid, reason, overridden_sl, overridden_tp = validator(
                action, entry_price, sl_price, snapshot, indicator_data, config, confirmation_timeframes
            )
            
            # If the validator doesn't override SL, and the original SL was bad, fail it
            if is_valid and overridden_sl is None and not sl_ok:
                return False, sl_reason, None, None
                
            return is_valid, reason, overridden_sl, overridden_tp

    return False, f"Unsupported strategy for deterministic validation: {strategy_name or 'N/A'}", None, None
