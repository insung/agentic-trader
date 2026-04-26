"""
Deterministic technical indicator calculations used by agents and validators.
"""
from __future__ import annotations

from typing import Any, Dict

import pandas as pd


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of OHLCV data with the indicators used by strategy gates."""
    enriched = df.copy()
    if enriched.empty:
        return enriched

    close = enriched["close"]
    high = enriched["high"]
    low = enriched["low"]

    enriched["ema20"] = close.ewm(span=20, adjust=False).mean()
    enriched["ema50"] = close.ewm(span=50, adjust=False).mean()

    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    enriched["atr14"] = true_range.rolling(14).mean()

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    atr_sum = true_range.rolling(14).sum()
    plus_di = 100 * plus_dm.rolling(14).sum() / atr_sum
    minus_di = 100 * minus_dm.rolling(14).sum() / atr_sum
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).replace([float("inf"), -float("inf")], pd.NA)
    enriched["adx14"] = dx.rolling(14).mean()

    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    enriched["bb_mid20"] = sma20
    enriched["bb_upper20"] = sma20 + (2 * std20)
    enriched["bb_lower20"] = sma20 - (2 * std20)
    enriched["bb_width20"] = (enriched["bb_upper20"] - enriched["bb_lower20"]) / sma20

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    enriched["rsi14"] = 100 - (100 / (1 + rs))

    return enriched


def build_indicator_snapshot(df: pd.DataFrame, lookback: int = 30) -> Dict[str, Any]:
    """Build a compact JSON-safe indicator snapshot for prompts and validators."""
    enriched = add_technical_indicators(df)
    if enriched.empty:
        return {"error": "empty_dataframe"}

    recent = enriched.tail(lookback).copy()
    latest = enriched.iloc[-1]

    def clean(value: Any) -> Any:
        if pd.isna(value):
            return None
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if hasattr(value, "item"):
            value = value.item()
        if isinstance(value, float):
            return round(value, 6)
        return value

    def cross_age(direction: str) -> int | None:
        ema20 = recent["ema20"]
        ema50 = recent["ema50"]
        if len(recent) < 2:
            return None
        if direction == "bullish":
            crosses = (ema20.shift(1) <= ema50.shift(1)) & (ema20 > ema50)
        else:
            crosses = (ema20.shift(1) >= ema50.shift(1)) & (ema20 < ema50)
        indexes = list(recent.index[crosses.fillna(False)])
        if not indexes:
            return None
        return int(enriched.index[-1] - indexes[-1])

    recent_rows = []
    columns = [
        "time",
        "open",
        "high",
        "low",
        "close",
        "ema20",
        "ema50",
        "atr14",
        "adx14",
        "bb_mid20",
        "bb_upper20",
        "bb_lower20",
        "bb_width20",
        "rsi14",
    ]
    for row in enriched.tail(10)[columns].to_dict(orient="records"):
        recent_rows.append({key: clean(value) for key, value in row.items()})

    return {
        "latest": {key: clean(latest.get(key)) for key in columns if key != "time"},
        "latest_time": str(latest.get("time", "")),
        "ema_cross_age_bars": {
            "bullish": cross_age("bullish"),
            "bearish": cross_age("bearish"),
        },
        "recent_rows": recent_rows,
    }
