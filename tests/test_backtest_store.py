import sqlite3

import pandas as pd

from backend.features.trading import backtest_store
from backend.features.trading.reporting import _summarize_decisions


def _sample_candles(start="2025-01-01 00:00:00", periods=3, freq="15min"):
    times = pd.date_range(start=start, periods=periods, freq=freq)
    return pd.DataFrame(
        {
            "time": times,
            "open": [100.0 + i for i in range(periods)],
            "high": [101.0 + i for i in range(periods)],
            "low": [99.0 + i for i in range(periods)],
            "close": [100.5 + i for i in range(periods)],
            "tick_volume": [10 + i for i in range(periods)],
            "spread": [2 for _ in range(periods)],
            "real_volume": [0 for _ in range(periods)],
        }
    )


def test_upsert_and_load_candles_without_duplicates(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    df = _sample_candles()

    backtest_store.init_backtest_db(str(db_path))
    first_count = backtest_store.upsert_candles(str(db_path), "BTCUSD", "M15", df)
    second_count = backtest_store.upsert_candles(str(db_path), "BTCUSD", "M15", df)

    loaded = backtest_store.load_candles(
        str(db_path),
        "BTCUSD",
        "M15",
        "2025-01-01",
        "2025-01-01",
    )

    assert first_count == 3
    assert second_count == 3
    assert len(loaded) == 3
    assert list(loaded["close"]) == [100.5, 101.5, 102.5]

    with sqlite3.connect(db_path) as conn:
        row_count = conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
    assert row_count == 3


def test_import_batch_status_is_recorded(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    backtest_store.init_backtest_db(str(db_path))

    batch_id = backtest_store.create_import_batch(
        str(db_path),
        symbol="BTCUSD",
        timeframes=["M15", "M30"],
        requested_from="2025-01-01",
        requested_to="2025-01-31",
    )
    backtest_store.update_import_batch_status(str(db_path), batch_id, "success")

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT symbol, timeframes, status FROM data_import_batches WHERE id = ?",
            (batch_id,),
        ).fetchone()

    assert row == ("BTCUSD", "M15,M30", "success")


def test_data_quality_metadata_reports_gaps(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    january = _sample_candles("2025-01-01 00:00:00", periods=2, freq="15min")
    february = _sample_candles("2025-02-01 00:00:00", periods=2, freq="15min")
    df = pd.concat([january, february], ignore_index=True)

    backtest_store.upsert_candles(str(db_path), "BTCUSD", "M15", df)
    loaded = backtest_store.load_candles(
        str(db_path),
        "BTCUSD",
        "M15",
        "2025-01-01",
        "2025-02-28",
    )
    quality = backtest_store.calculate_candle_quality(loaded)

    assert quality["candle_count"] == 4
    assert quality["duplicate_count"] == 0
    assert quality["median_interval"] == "0 days 00:15:00"
    assert quality["max_gap"] > "0 days 00:15:00"


def test_persist_backtest_result_records_run_trade_and_decision(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    backtest_store.init_backtest_db(str(db_path))

    run_id = backtest_store.persist_backtest_result(
        str(db_path),
        run={
            "run_id": "BT-TEST",
            "symbol": "BTCUSD",
            "timeframes": ["M15", "M30"],
            "base_timeframe": "M15",
            "data_from": "2025-01-01",
            "data_to": "2025-01-31",
            "initial_balance": 10000.0,
            "final_balance": 10100.0,
            "risk_per_trade_pct": 0.005,
            "step_interval": 5,
            "total_trades": 1,
            "net_pnl": 100.0,
            "profit_factor": 2.0,
            "max_drawdown_pct": 1.0,
        },
        trades=[
            {
                "trade_id": "BT-1",
                "action": "BUY",
                "entry_time": "2025-01-02 00:00:00",
                "exit_time": "2025-01-02 01:00:00",
                "entry_price": 100.0,
                "exit_price": 110.0,
                "sl": 95.0,
                "tp": 110.0,
                "lot_size": 1.0,
                "result": "TP_HIT",
                "exit_reason": "Take Profit",
                "pnl": 100.0,
                "strategy": "Moving Average Crossover",
                "market_regime": "Bullish",
                "reasoning": "test",
            }
        ],
        decisions=[
            {
                "decision_time": "2025-01-02 00:00:00",
                "action": "BUY",
                "strategy": "Moving Average Crossover",
                "market_regime": "Bullish",
                "status": "OPENED",
                "rejection_reason": "higher timeframe bullish conflict",
                "indicator_snapshot": {"M15": {"latest": {"close": 100.0}}},
                "final_order": {"action": "BUY"},
            }
        ],
    )

    assert run_id == "BT-TEST"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM backtest_trades").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM backtest_decisions").fetchone()[0] == 1
        row = conn.execute(
            """
            SELECT strategy, market_regime, rejection_reason, indicator_snapshot_json
            FROM backtest_decisions
            """
        ).fetchone()
    assert row[0] == "Moving Average Crossover"
    assert row[1] == "Bullish"
    assert row[2] == "higher timeframe bullish conflict"
    assert '"M15"' in row[3]


def test_summarize_decisions_groups_status_strategy_and_rejections():
    summary = _summarize_decisions(
        [
            {
                "status": "OPENED",
                "action": "SELL",
                "strategy": "Moving Average Crossover",
                "market_regime": "Bearish",
            },
            {
                "status": "REJECTED",
                "action": "SELL",
                "strategy": "Moving Average Crossover",
                "market_regime": "Bearish",
                "rejection_reason": "higher timeframe bullish conflict",
            },
            {
                "status": "REJECTED",
                "action": "SELL",
                "strategy": "Moving Average Crossover",
                "market_regime": "Bearish",
                "rejection_reason": "higher timeframe bullish conflict",
            },
            {"status": "HOLD", "action": "HOLD"},
        ]
    )

    assert summary["total"] == 4
    assert summary["by_status"]["REJECTED"] == 2
    assert summary["by_strategy"]["Moving Average Crossover"]["OPENED"] == 1
    assert summary["top_rejections"][0] == ("higher timeframe bullish conflict", 2)
