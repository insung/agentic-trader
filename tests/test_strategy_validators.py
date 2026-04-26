from backend.features.trading.strategy_validators import validate_strategy_setup


def _snapshot(**latest_overrides):
    latest = {
        "close": 100.0,
        "open": 99.0,
        "high": 101.0,
        "low": 98.0,
        "ema20": 95.0,
        "ema50": 90.0,
        "atr14": 10.0,
        "adx14": 30.0,
        "bb_upper20": 101.0,
        "bb_lower20": 90.0,
        "rsi14": 70.0,
    }
    latest.update(latest_overrides)
    return {
        "M15": {
            "latest": latest,
            "ema_cross_age_bars": {"bullish": 2, "bearish": None},
            "recent_rows": [
                {"open": 96.0, "high": 102.0, "low": 95.0, "close": 101.0, "bb_upper20": 101.0, "bb_lower20": 90.0},
                {"open": 101.0, "high": 103.0, "low": 99.0, "close": 100.0, "bb_upper20": 102.0, "bb_lower20": 91.0},
                {"open": 101.0, "high": 101.5, "low": 98.0, "close": 99.0, "bb_upper20": 102.0, "bb_lower20": 91.0},
            ],
        }
    }


def test_ma_crossover_requires_recent_cross_and_atr_sized_stop():
    ok, reason = validate_strategy_setup(
        "BUY",
        100.0,
        89.0,
        {"selected_strategy": "Moving Average Crossover"},
        _snapshot(),
    )
    assert ok, reason

    ok, reason = validate_strategy_setup(
        "BUY",
        100.0,
        95.0,
        {"selected_strategy": "Moving Average Crossover"},
        _snapshot(),
    )
    assert not ok
    assert "ATR" in reason


def test_ma_crossover_blocks_stale_or_absent_cross():
    data = _snapshot()
    data["M15"]["ema_cross_age_bars"]["bullish"] = 12
    ok, reason = validate_strategy_setup(
        "BUY",
        100.0,
        89.0,
        {"selected_strategy": "Moving Average Crossover"},
        data,
    )
    assert not ok
    assert "stale" in reason


def test_bollinger_short_blocks_unresolved_uptrend_without_overbought_rsi():
    ok, reason = validate_strategy_setup(
        "SELL",
        100.0,
        111.0,
        {"selected_strategy": "Bollinger Bands Double Top"},
        _snapshot(rsi14=54.0, ema20=99.0, ema50=95.0),
    )
    assert not ok
    assert "strong uptrend" in reason


def test_unknown_strategy_is_rejected():
    ok, reason = validate_strategy_setup(
        "BUY",
        100.0,
        89.0,
        {"selected_strategy": "RSI Guess"},
        _snapshot(),
    )
    assert not ok
    assert "Unsupported strategy" in reason
