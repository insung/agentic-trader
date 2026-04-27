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
        "bb_upper20": 110.0,
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


def _ma_mtf_snapshot(action="BUY", m30_conflict=False, **m15_overrides):
    if action == "SELL":
        m15_latest = {
            "close": 96.0,
            "open": 97.0,
            "high": 98.0,
            "low": 95.0,
            "ema20": 98.0,
            "ema50": 99.0,
            "atr14": 10.0,
            "adx14": 30.0,
            "bb_upper20": 110.0,
            "bb_lower20": 90.0,
            "rsi14": 42.0,
        }
        m30_latest = {
            "close": 101.0 if m30_conflict else 96.0,
            "ema20": 100.0 if m30_conflict else 98.0,
            "ema50": 99.0,
            "adx14": 28.0,
        }
        cross_ages = {"bullish": None, "bearish": 0}
    else:
        m15_latest = {
            "close": 104.0,
            "open": 103.0,
            "high": 105.0,
            "low": 102.0,
            "ema20": 102.0,
            "ema50": 101.0,
            "atr14": 10.0,
            "adx14": 30.0,
            "bb_upper20": 110.0,
            "bb_lower20": 90.0,
            "rsi14": 58.0,
        }
        m30_latest = {
            "close": 99.0 if m30_conflict else 104.0,
            "ema20": 100.0 if m30_conflict else 102.0,
            "ema50": 101.0,
            "adx14": 28.0,
        }
        cross_ages = {"bullish": 0, "bearish": None}

    m15_latest.update(m15_overrides)
    return {
        "M15": {
            "latest": m15_latest,
            "ema_cross_age_bars": cross_ages,
            "recent_rows": [],
        },
        "M30": {
            "latest": m30_latest,
            "ema_cross_age_bars": {"bullish": None, "bearish": None},
            "recent_rows": [],
        },
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


def test_ma_crossover_blocks_higher_timeframe_conflict():
    ok, reason = validate_strategy_setup(
        "SELL",
        96.0,
        107.0,
        {"selected_strategy": "Moving Average Crossover"},
        _ma_mtf_snapshot("SELL", m30_conflict=True),
    )
    assert not ok
    assert "higher timeframe bullish conflict" in reason

    ok, reason = validate_strategy_setup(
        "BUY",
        104.0,
        93.0,
        {"selected_strategy": "Moving Average Crossover"},
        _ma_mtf_snapshot("BUY", m30_conflict=True),
    )
    assert not ok
    assert "higher timeframe bearish conflict" in reason


def test_ma_crossover_allows_aligned_multi_timeframe_setup():
    ok, reason = validate_strategy_setup(
        "SELL",
        96.0,
        107.0,
        {"selected_strategy": "Moving Average Crossover"},
        _ma_mtf_snapshot("SELL"),
    )
    assert ok, reason


def test_ma_crossover_blocks_exhausted_band_entries():
    ok, reason = validate_strategy_setup(
        "SELL",
        96.0,
        107.0,
        {"selected_strategy": "Moving Average Crossover"},
        _ma_mtf_snapshot("SELL", close=90.2, rsi14=31.0, bb_lower20=90.0),
    )
    assert not ok
    assert "oversold lower-band exhaustion" in reason

    ok, reason = validate_strategy_setup(
        "BUY",
        104.0,
        93.0,
        {"selected_strategy": "Moving Average Crossover"},
        _ma_mtf_snapshot("BUY", close=109.8, rsi14=70.0, bb_upper20=110.0),
    )
    assert not ok
    assert "overbought upper-band exhaustion" in reason


def test_ma_crossover_blocks_late_chase_near_bollinger_band():
    ok, reason = validate_strategy_setup(
        "SELL",
        99561.75,
        100500.0,
        {"selected_strategy": "Moving Average Crossover"},
        _ma_mtf_snapshot(
            "SELL",
            close=99561.75,
            ema20=100353.29,
            ema50=100471.18,
            atr14=745.35,
            adx14=44.13,
            bb_lower20=99259.01,
            bb_upper20=102186.8,
            rsi14=40.2,
            low=99037.01,
        ),
    )
    assert not ok
    assert "late SELL chase" in reason

    ok, reason = validate_strategy_setup(
        "BUY",
        109.8,
        98.0,
        {"selected_strategy": "Moving Average Crossover"},
        _ma_mtf_snapshot(
            "BUY",
            close=109.8,
            ema20=102.0,
            ema50=101.0,
            atr14=10.0,
            adx14=30.0,
            bb_upper20=110.0,
            bb_lower20=90.0,
            rsi14=56.0,
        ),
    )
    assert not ok
    assert "late BUY chase" in reason


def test_ma_crossover_allows_aligned_setup_with_band_room():
    ok, reason = validate_strategy_setup(
        "SELL",
        96.0,
        107.0,
        {"selected_strategy": "Moving Average Crossover"},
        _ma_mtf_snapshot(
            "SELL",
            close=96.0,
            atr14=10.0,
            bb_lower20=85.0,
            rsi14=46.0,
        ),
    )
    assert ok, reason


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
