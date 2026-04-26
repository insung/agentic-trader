import pandas as pd

from backend.features.trading.backtest_store import upsert_candles
from backend.scripts.run_backtest import load_backtest_data_from_sqlite


def _candles(start, periods, freq):
    times = pd.date_range(start=start, periods=periods, freq=freq)
    return pd.DataFrame(
        {
            "time": times,
            "open": [1.0] * periods,
            "high": [2.0] * periods,
            "low": [0.5] * periods,
            "close": [1.5] * periods,
            "tick_volume": [100] * periods,
            "spread": [1] * periods,
            "real_volume": [0] * periods,
        }
    )


def test_load_backtest_data_from_sqlite_returns_timeframe_frames(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    upsert_candles(str(db_path), "BTCUSD", "M15", _candles("2025-01-01", 3, "15min"))
    upsert_candles(str(db_path), "BTCUSD", "M30", _candles("2025-01-01", 2, "30min"))

    dfs, metadata = load_backtest_data_from_sqlite(
        str(db_path),
        symbol="BTCUSD",
        timeframes=["M15", "M30"],
        from_date="2025-01-01",
        to_date="2025-01-01",
    )

    assert list(dfs.keys()) == ["M15", "M30"]
    assert len(dfs["M15"]) == 3
    assert len(dfs["M30"]) == 2
    assert metadata["M15"]["candle_count"] == 3
    assert metadata["M30"]["candle_count"] == 2


def test_load_backtest_data_from_sqlite_fails_for_missing_timeframe(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    upsert_candles(str(db_path), "BTCUSD", "M15", _candles("2025-01-01", 3, "15min"))

    try:
        load_backtest_data_from_sqlite(
            str(db_path),
            symbol="BTCUSD",
            timeframes=["M15", "M30"],
            from_date="2025-01-01",
            to_date="2025-01-01",
        )
    except ValueError as exc:
        assert "No candle data" in str(exc)
        assert "M30" in str(exc)
    else:
        raise AssertionError("Expected missing timeframe to raise ValueError")
