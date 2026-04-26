import sqlite3

import pandas as pd

from backend.scripts import migrate_legacy_data


def test_migrate_legacy_backtest_and_trading_logs(tmp_path):
    backtest_dir = tmp_path / "backtests"
    data_dir = backtest_dir / "data"
    results_dir = backtest_dir / "results"
    reports_dir = backtest_dir / "reports"
    trading_logs_dir = tmp_path / "trading_logs"
    data_dir.mkdir(parents=True)
    results_dir.mkdir()
    reports_dir.mkdir()
    trading_logs_dir.mkdir()

    pd.DataFrame(
        {
            "time": pd.date_range("2025-01-01", periods=2, freq="15min"),
            "open": [1.0, 1.1],
            "high": [1.2, 1.3],
            "low": [0.9, 1.0],
            "close": [1.1, 1.2],
            "tick_volume": [10, 11],
            "spread": [1, 1],
            "real_volume": [0, 0],
        }
    ).to_csv(data_dir / "BTCUSD_20250101-20250131_M15.csv", index=False)

    (results_dir / "backtest_BTCUSD_20260101_000000.json").write_text(
        """
        {
          "symbol": "BTCUSD",
          "initial_balance": 10000.0,
          "final_balance": 10050.0,
          "timeframes": ["M15"],
          "base_timeframe": "M15",
          "risk_per_trade_pct": 0.005,
          "step_interval": 5,
          "total_trades": 1,
          "trades": [
            {
              "trade_id": "BT-1",
              "action": "BUY",
              "entry_time": "2025-01-01 00:00:00",
              "exit_time": "2025-01-01 00:15:00",
              "entry_price": 1.0,
              "exit_price": 1.2,
              "sl": 0.9,
              "tp": 1.2,
              "lot_size": 250.0,
              "result": "TP_HIT",
              "exit_reason": "Take Profit",
              "pnl": 50.0
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    (reports_dir / "backtest_BTCUSD_20260101_000000.md").write_text(
        "# Backtest Report: BTCUSD\n\n**생성일시**: 2026-01-01 00:00:00  \n",
        encoding="utf-8",
    )
    (trading_logs_dir / "review_20260101_0000.md").write_text(
        "# Trade Review Log\n\n"
        "**Date**: 2026-01-01T00:00:00\n\n"
        "## Summary\nclosed\n\n"
        "## Risk Assessment\nrisk ok\n\n"
        "## Lessons Learned\nlesson\n",
        encoding="utf-8",
    )

    backtest_db = tmp_path / "market_data.sqlite"
    trading_log_db = tmp_path / "trading_logs.sqlite"
    assert migrate_legacy_data.migrate_backtest_csvs(str(backtest_dir), str(backtest_db)) == 1
    assert migrate_legacy_data.migrate_backtest_results(str(backtest_dir), str(backtest_db)) == 1
    assert migrate_legacy_data.migrate_backtest_reports(str(backtest_dir), str(backtest_db)) == 1
    assert migrate_legacy_data.migrate_trading_logs(str(trading_logs_dir), str(trading_log_db)) == 1

    with sqlite3.connect(backtest_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM backtest_trades").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM backtest_reports").fetchone()[0] == 1

    with sqlite3.connect(trading_log_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM trade_reviews").fetchone()[0] == 1
