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


def test_incremental_backtest_persistence_records_rows_before_final_summary(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    run = {
        "run_id": "BT-INCREMENTAL",
        "symbol": "BTCUSD",
        "timeframes": ["M15", "M30"],
        "base_timeframe": "M15",
        "data_from": "2025-01-01",
        "data_to": "2025-01-31",
        "initial_balance": 10000.0,
        "risk_per_trade_pct": 0.005,
        "step_interval": 5,
    }

    backtest_store.start_backtest_run(str(db_path), run)
    backtest_store.record_backtest_decision(
        str(db_path),
        run_id="BT-INCREMENTAL",
        decision={
            "decision_time": "2025-01-02 00:00:00",
            "action": "SELL",
            "strategy": "Moving Average Crossover",
            "market_regime": "Bearish",
            "status": "REJECTED",
            "rejection_reason": "SL too tight",
            "indicator_snapshot": {"M15": {"latest": {"atr_14": 50.0}}},
            "final_order": {"action": "SELL"},
        },
    )
    backtest_store.record_backtest_trade(
        str(db_path),
        run_id="BT-INCREMENTAL",
        symbol="BTCUSD",
        trade={
            "trade_id": "BT-1",
            "action": "BUY",
            "entry_time": "2025-01-03 00:00:00",
            "exit_time": "2025-01-03 02:00:00",
            "entry_price": 100.0,
            "exit_price": 110.0,
            "sl": 95.0,
            "tp": 110.0,
            "lot_size": 1.0,
            "result": "TP_HIT",
            "exit_reason": "Take Profit",
            "pnl": 100.0,
        },
    )

    with sqlite3.connect(db_path) as conn:
        run_row = conn.execute(
            "SELECT final_balance, total_trades, status, completed_at, error_message FROM backtest_runs WHERE run_id = ?",
            ("BT-INCREMENTAL",),
        ).fetchone()
        decision_count = conn.execute("SELECT COUNT(*) FROM backtest_decisions").fetchone()[0]
        trade_count = conn.execute("SELECT COUNT(*) FROM backtest_trades").fetchone()[0]

    assert run_row == (None, 0, "running", None, None)
    assert decision_count == 1
    assert trade_count == 1

    backtest_store.finish_backtest_run(
        str(db_path),
        run_id="BT-INCREMENTAL",
        final_balance=10100.0,
        total_trades=1,
        net_pnl=100.0,
        profit_factor=2.0,
        max_drawdown_pct=1.0,
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT final_balance, total_trades, net_pnl, profit_factor, max_drawdown_pct, status, completed_at, error_message
            FROM backtest_runs
            WHERE run_id = ?
            """,
            ("BT-INCREMENTAL",),
        ).fetchone()

    assert row[:6] == (10100.0, 1, 100.0, 2.0, 1.0, "completed")
    assert row[6] is not None
    assert row[7] is None


def test_backtest_run_status_marks_interrupted_and_failed(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    run = {
        "run_id": "BT-STATUS",
        "symbol": "BTCUSD",
        "timeframes": ["M15", "M30"],
        "base_timeframe": "M15",
        "data_from": "2025-01-01",
        "data_to": "2025-01-31",
        "initial_balance": 10000.0,
        "risk_per_trade_pct": 0.005,
        "step_interval": 5,
    }

    backtest_store.start_backtest_run(str(db_path), run)
    backtest_store.mark_backtest_run_status(
        str(db_path),
        run_id="BT-STATUS",
        status="interrupted",
        error_message="KeyboardInterrupt",
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, completed_at, error_message FROM backtest_runs WHERE run_id = ?",
            ("BT-STATUS",),
        ).fetchone()

    assert row[0] == "interrupted"
    assert row[1] is not None
    assert row[2] == "KeyboardInterrupt"

    backtest_store.mark_backtest_run_status(
        str(db_path),
        run_id="BT-STATUS",
        status="failed",
        error_message="boom",
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, error_message FROM backtest_runs WHERE run_id = ?",
            ("BT-STATUS",),
        ).fetchone()

    assert row == ("failed", "boom")


def test_store_backtest_report_keeps_paths_optional(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    backtest_store.start_backtest_run(
        str(db_path),
        {
            "run_id": "RUN-1",
            "symbol": "BTCUSD",
            "timeframes": ["M15"],
            "base_timeframe": "M15",
            "data_from": "2025-01-01",
            "data_to": "2025-01-31",
            "initial_balance": 10000.0,
            "risk_per_trade_pct": 0.005,
            "step_interval": 5,
        },
    )
    backtest_store.store_backtest_report(
        str(db_path),
        report_id="REPORT-1",
        run_id="RUN-1",
        symbol="BTCUSD",
        report_path=None,
        chart_path=None,
        report_created_at="2026-04-27T00:00:00",
        markdown_body="# Backtest Report",
        summary_json={"source": "db_replayable"},
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT report_id, run_id, report_path, chart_path, markdown_body, summary_json
            FROM backtest_reports
            WHERE report_id = ?
            """,
            ("REPORT-1",),
        ).fetchone()

    assert row[0] == "REPORT-1"
    assert row[1] == "RUN-1"
    assert row[2] is None
    assert row[3] is None
    assert row[4] == "# Backtest Report"
    assert "db_replayable" in row[5]


def test_load_backtest_replay_uses_db_source_of_truth(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    backtest_store.upsert_candles(
        str(db_path),
        "BTCUSD",
        "M15",
        _sample_candles("2025-01-01 00:00:00", periods=4, freq="15min"),
    )
    backtest_store.persist_backtest_result(
        str(db_path),
        run={
            "run_id": "BT-REPLAY",
            "symbol": "BTCUSD",
            "timeframes": ["M15", "M30"],
            "base_timeframe": "M15",
            "data_from": "2025-01-01 00:00:00",
            "data_to": "2025-01-01 00:45:00",
            "initial_balance": 10000.0,
            "final_balance": 10025.0,
            "risk_per_trade_pct": 0.005,
            "step_interval": 5,
            "total_trades": 1,
            "net_pnl": 25.0,
            "profit_factor": None,
            "max_drawdown_pct": 0.0,
        },
        trades=[
            {
                "trade_id": "BT-1",
                "action": "BUY",
                "entry_time": "2025-01-01 00:15:00",
                "exit_time": "2025-01-01 00:30:00",
                "entry_price": 101.0,
                "exit_price": 102.0,
                "sl": 99.0,
                "tp": 103.0,
                "lot_size": 1.0,
                "result": "TP_HIT",
                "exit_reason": "Take Profit",
                "pnl": 25.0,
                "strategy": "Moving Average Crossover",
            }
        ],
        decisions=[
            {
                "decision_time": "2025-01-01 00:15:00",
                "action": "BUY",
                "strategy": "Moving Average Crossover",
                "market_regime": "Bullish",
                "status": "OPENED",
                "indicator_snapshot": {"M15": {"latest": {"close": 101.0}}},
                "final_order": {"action": "BUY"},
            }
        ],
    )

    replay = backtest_store.load_backtest_replay(str(db_path), "BT-REPLAY")

    assert replay["run"]["run_id"] == "BT-REPLAY"
    assert replay["run"]["base_timeframe"] == "M15"
    assert len(replay["candles"]) == 4
    assert replay["trades"][0]["trade_id"] == "BT-1"
    assert replay["decisions"][0]["indicator_snapshot"]["M15"]["latest"]["close"] == 101.0


def test_init_backtest_db_migrates_legacy_run_status_columns(tmp_path):
    db_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE backtest_runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id TEXT NOT NULL UNIQUE,
              symbol TEXT NOT NULL,
              timeframes TEXT NOT NULL,
              base_timeframe TEXT NOT NULL,
              data_from TEXT NOT NULL,
              data_to TEXT NOT NULL,
              initial_balance REAL NOT NULL,
              final_balance REAL,
              risk_per_trade_pct REAL NOT NULL,
              step_interval INTEGER NOT NULL,
              total_trades INTEGER DEFAULT 0,
              net_pnl REAL,
              profit_factor REAL,
              max_drawdown_pct REAL,
              created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO backtest_runs (
              run_id, symbol, timeframes, base_timeframe, data_from, data_to,
              initial_balance, final_balance, risk_per_trade_pct, step_interval,
              total_trades, net_pnl, profit_factor, max_drawdown_pct, created_at
            ) VALUES ('DONE', 'BTCUSD', 'M15,M30', 'M15', '2025-01-01', '2025-01-31',
              10000.0, 10100.0, 0.005, 5, 1, 100.0, 2.0, 1.0, '2026-04-27T00:00:00+00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO backtest_runs (
              run_id, symbol, timeframes, base_timeframe, data_from, data_to,
              initial_balance, final_balance, risk_per_trade_pct, step_interval,
              total_trades, net_pnl, profit_factor, max_drawdown_pct, created_at
            ) VALUES ('RUNNING', 'BTCUSD', 'M15,M30', 'M15', '2025-01-01', '2025-01-31',
              10000.0, NULL, 0.005, 5, 0, NULL, NULL, NULL, '2026-04-27T00:00:00+00:00')
            """
        )
        conn.commit()

    backtest_store.init_backtest_db(str(db_path))

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(backtest_runs)")}
        rows = conn.execute(
            "SELECT run_id, status, completed_at, error_message FROM backtest_runs ORDER BY run_id"
        ).fetchall()

    assert {"status", "completed_at", "error_message"}.issubset(columns)
    assert rows[0] == ("DONE", "completed", None, None)
    assert rows[1] == ("RUNNING", "running", None, None)


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
