import pytest

from backend.features.trading.strategy_validators import (
    build_volatility_expansion_breakout_metadata,
    validate_strategy_setup,
)


def _m5_row(
    *,
    high: float,
    low: float,
    close: float,
    open_: float | None = None,
    atr14: float = 1.0,
    bb_lower20: float = 90.0,
    bb_upper20: float = 110.0,
) -> dict:
    return {
        "high": high,
        "low": low,
        "close": close,
        "open": close if open_ is None else open_,
        "atr14": atr14,
        "bb_lower20": bb_lower20,
        "bb_upper20": bb_upper20,
    }


def _build_buy_rows(
    *,
    current_high: float = 108.0,
    current_low: float = 104.0,
    current_close: float = 107.0,
    current_atr: float = 1.0,
    bottom2_low: float = 91.0,
    current_bb_lower20: float = 80.0,
    current_bb_upper20: float = 120.0,
) -> list[dict]:
    rows = [_m5_row(high=100.0, low=95.0, close=97.0, open_=96.0) for _ in range(23)]
    rows.extend(
        [
            _m5_row(high=100.0, low=89.0, close=92.0, open_=91.0, bb_lower20=90.0),
            _m5_row(high=105.0, low=94.0, close=104.0, open_=103.0, bb_lower20=90.0),
            _m5_row(high=102.0, low=bottom2_low, close=95.0, open_=96.0, bb_lower20=90.0),
            _m5_row(high=103.0, low=96.0, close=100.0, open_=99.0),
            _m5_row(high=104.0, low=97.0, close=101.0, open_=100.0),
            _m5_row(high=105.0, low=98.0, close=102.0, open_=101.0),
            _m5_row(
                high=current_high,
                low=current_low,
                close=current_close,
                open_=104.0,
                atr14=current_atr,
                bb_lower20=current_bb_lower20,
                bb_upper20=current_bb_upper20,
            ),
        ]
    )
    return rows


def _build_sell_rows(
    *,
    current_high: float = 96.0,
    current_low: float = 92.0,
    current_close: float = 93.0,
    current_atr: float = 1.0,
    top2_high: float = 108.0,
    current_bb_lower20: float = 80.0,
    current_bb_upper20: float = 120.0,
) -> list[dict]:
    rows = [_m5_row(high=100.0, low=95.0, close=97.0, open_=96.0) for _ in range(23)]
    rows.extend(
        [
            _m5_row(high=111.0, low=100.0, close=108.0, open_=107.0, bb_upper20=110.0),
            _m5_row(high=106.0, low=95.0, close=96.0, open_=97.0),
            _m5_row(high=top2_high, low=96.0, close=104.0, open_=105.0, bb_upper20=110.0),
            _m5_row(high=107.0, low=97.0, close=103.0, open_=104.0),
            _m5_row(high=106.0, low=98.0, close=102.0, open_=103.0),
            _m5_row(high=105.0, low=99.0, close=101.0, open_=102.0),
            _m5_row(
                high=current_high,
                low=current_low,
                close=current_close,
                open_=94.0,
                atr14=current_atr,
                bb_lower20=current_bb_lower20,
                bb_upper20=current_bb_upper20,
            ),
        ]
    )
    return rows


def _indicator_data(m5_rows: list[dict], m15_latest: dict | None, previous_adx: float = 24.0) -> dict:
    data = {
        "M5": {
            "latest": m5_rows[-1],
            "recent_rows": m5_rows,
        }
    }
    if m15_latest is not None:
        data["M15"] = {
            "latest": m15_latest,
            "recent_rows": [{"adx14": previous_adx}, m15_latest],
        }
    return data


def test_volatility_expansion_breakout_long_success():
    m15_latest = {
        "adx14": 25.0,
        "close": 107.0,
        "ema20": 100.0,
        "ema50": 90.0,
        "atr14": 2.0,
    }
    indicator_data = _indicator_data(_build_buy_rows(), m15_latest)

    ok, reason, sl, tp = validate_strategy_setup(
        "BUY",
        107.0,
        90.0,
        {"selected_strategy": "Volatility Expansion Breakout"},
        indicator_data,
        primary_timeframe="M5",
        confirmation_timeframes=["M15"],
    )

    assert ok, reason
    assert sl == pytest.approx(90.5)
    assert tp == pytest.approx(140.0)


def test_volatility_expansion_breakout_short_success_uses_m15_fallback():
    m15_latest = {
        "adx14": 25.0,
        "close": 93.0,
        "ema20": 100.0,
        "ema50": 110.0,
        "atr14": 2.0,
    }
    indicator_data = _indicator_data(_build_sell_rows(), m15_latest)

    ok, reason, sl, tp = validate_strategy_setup(
        "SELL",
        93.0,
        110.0,
        {"selected_strategy": "Volatility Expansion Breakout"},
        indicator_data,
        primary_timeframe="M5",
    )

    assert ok, reason
    assert sl == pytest.approx(108.5)
    assert tp == pytest.approx(62.0)


def test_volatility_expansion_breakout_fails_on_weak_momentum():
    m15_latest = {
        "adx14": 25.0,
        "close": 105.5,
        "ema20": 100.0,
        "ema50": 90.0,
        "atr14": 2.0,
    }
    indicator_data = _indicator_data(
        _build_buy_rows(current_high=106.0, current_low=105.3, current_close=105.5),
        m15_latest,
    )

    ok, reason, _, _ = validate_strategy_setup(
        "BUY",
        105.5,
        90.0,
        {"selected_strategy": "Volatility Expansion Breakout"},
        indicator_data,
        primary_timeframe="M5",
        confirmation_timeframes=["M15"],
    )
    assert not ok
    assert "range" in reason.lower() or "atr" in reason.lower()


def test_volatility_expansion_breakout_fails_on_adx_slope():
    m15_latest = {
        "adx14": 25.0,
        "close": 107.0,
        "ema20": 100.0,
        "ema50": 90.0,
        "atr14": 2.0,
    }
    indicator_data = _indicator_data(_build_buy_rows(), m15_latest, previous_adx=26.0)

    ok, reason, _, _ = validate_strategy_setup(
        "BUY",
        107.0,
        90.0,
        {"selected_strategy": "Volatility Expansion Breakout"},
        indicator_data,
        primary_timeframe="M5",
        confirmation_timeframes=["M15"],
    )
    assert not ok
    assert "adx slope" in reason.lower()


def test_volatility_expansion_breakout_rejects_without_bandwidth_expansion():
    m15_latest = {
        "adx14": 25.0,
        "close": 107.0,
        "ema20": 100.0,
        "ema50": 90.0,
        "atr14": 2.0,
    }
    indicator_data = _indicator_data(
        _build_buy_rows(current_bb_lower20=90.0, current_bb_upper20=110.0),
        m15_latest,
    )

    ok, reason, _, _ = validate_strategy_setup(
        "BUY",
        107.0,
        90.0,
        {"selected_strategy": "Volatility Expansion Breakout"},
        indicator_data,
        primary_timeframe="M5",
        confirmation_timeframes=["M15"],
    )

    assert not ok
    assert "bandwidth" in reason.lower()


def test_volatility_expansion_breakout_metadata_helper_extracts_neckline():
    m15_latest = {
        "adx14": 25.0,
        "close": 107.0,
        "ema20": 100.0,
        "ema50": 90.0,
        "atr14": 2.0,
    }
    indicator_data = _indicator_data(_build_buy_rows(), m15_latest)

    metadata = build_volatility_expansion_breakout_metadata(
        "BUY",
        indicator_data,
        primary_timeframe="M5",
        confirmation_timeframes=["M15"],
    )

    assert metadata["strategy"] == "Volatility Expansion Breakout"
    assert metadata["neckline"] == 105.0
    assert metadata["invalidation_rule"] == "two_consecutive_neckline_breaks"
    assert metadata["direction"] == "BUY"


def test_volatility_expansion_breakout_rejects_missing_current_m5_fields():
    rows = _build_buy_rows()
    rows[-1].pop("atr14")
    m15_latest = {
        "adx14": 25.0,
        "close": 107.0,
        "ema20": 100.0,
        "ema50": 90.0,
        "atr14": 2.0,
    }
    indicator_data = _indicator_data(rows, m15_latest)

    ok, reason, _, _ = validate_strategy_setup(
        "BUY",
        107.0,
        90.0,
        {"selected_strategy": "Volatility Expansion Breakout"},
        indicator_data,
        primary_timeframe="M5",
        confirmation_timeframes=["M15"],
    )
    assert not ok
    assert "current m5 fields" in reason.lower()
    assert "atr14" in reason.lower()


def test_volatility_expansion_breakout_rejects_missing_m15_snapshot():
    indicator_data = {"M5": {"latest": _build_buy_rows()[-1], "recent_rows": _build_buy_rows()}}

    ok, reason, _, _ = validate_strategy_setup(
        "BUY",
        107.0,
        90.0,
        {"selected_strategy": "Volatility Expansion Breakout"},
        indicator_data,
        primary_timeframe="M5",
    )
    assert not ok
    assert "confirmation" in reason.lower()


def test_volatility_expansion_breakout_rejects_unsupported_action():
    m15_latest = {
        "adx14": 25.0,
        "close": 107.0,
        "ema20": 100.0,
        "ema50": 90.0,
        "atr14": 2.0,
    }
    indicator_data = _indicator_data(_build_buy_rows(), m15_latest)

    ok, reason, _, _ = validate_strategy_setup(
        "HOLD",
        107.0,
        90.0,
        {"selected_strategy": "Volatility Expansion Breakout"},
        indicator_data,
        primary_timeframe="M5",
        confirmation_timeframes=["M15"],
    )
    assert not ok
    assert "only validates buy or sell" in reason.lower()
