import sqlite3

import pandas as pd

from backend.features.trading.backtest_store import persist_backtest_result, upsert_candles
from backend.features.trading.no_trade_audit import format_no_trade_audit, summarize_no_trade_audit


def _sample_candles(periods=20):
    times = pd.date_range(start="2025-01-01", periods=periods, freq="15min")
    close = pd.Series([100 + (i * 0.25) for i in range(periods)])
    return pd.DataFrame(
        {
            "time": times,
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "tick_volume": [100] * periods,
            "spread": [1] * periods,
            "real_volume": [0] * periods,
        }
    )


def test_no_trade_audit_summarizes_decisions_and_reasons(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    upsert_candles(str(db_path), "BTCUSD", "M15", _sample_candles())

    persist_backtest_result(
        str(db_path),
        {
            "run_id": "BT-TEST",
            "symbol": "BTCUSD",
            "timeframes": ["M15"],
            "base_timeframe": "M15",
            "data_from": "2025-01-01",
            "data_to": "2025-01-01",
            "initial_balance": 10000.0,
            "final_balance": 10000.0,
            "risk_per_trade_pct": 0.005,
            "step_interval": 5,
            "total_trades": 0,
            "net_pnl": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "status": "completed",
        },
        trades=[],
        decisions=[
            {
                "decision_time": "2025-01-01 00:00:00",
                "action": "BUY",
                "strategy": "ma_crossover",
                "market_regime": "bullish",
                "status": "SKIP",
            },
            {
                "decision_time": "2025-01-01 00:15:00",
                "action": "BUY",
                "strategy": "ma_crossover",
                "market_regime": "bullish",
                "status": "HOLD",
                "final_order": {"reasoning": "wait for trend confirmation"},
            },
            {
                "decision_time": "2025-01-01 00:30:00",
                "action": "SELL",
                "strategy": "macd",
                "market_regime": "bearish",
                "status": "REJECTED",
                "rejection_reason": "invalid SL/TP direction or risk/reward",
            },
            {
                "decision_time": "2025-01-01 00:45:00",
                "action": "BUY",
                "strategy": "breakout",
                "market_regime": "range",
                "status": "REJECTED",
                "rejection_reason": "lot size calculated to <= 0",
            },
        ],
    )

    report = summarize_no_trade_audit(str(db_path), "BT-TEST")

    assert report["run"]["run_id"] == "BT-TEST"
    assert report["counts"]["decisions"] == 4
    assert report["counts"]["trades"] == 0
    assert report["counts"]["opened"] == 0
    assert report["counts"]["rejected"] == 2
    assert report["counts"]["hold"] == 1
    assert report["counts"]["skip"] == 1
    assert report["by_status"]["REJECTED"] == 2
    assert report["by_strategy_status"]["ma_crossover"]["HOLD"] == 1
    assert report["trade_results"] == {}
    assert any("guardrail_invalid_rr" in bucket for bucket, _ in report["reason_buckets"])
    assert any("guardrail_lot_size" in bucket for bucket, _ in report["reason_buckets"])

    rendered = format_no_trade_audit(report)
    assert "No-Trade Audit" in rendered
    assert "BT-TEST" in rendered
    assert "By Status" in rendered
    assert "Top Rejections" in rendered


def test_no_trade_audit_requires_existing_run(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    upsert_candles(str(db_path), "BTCUSD", "M15", _sample_candles())

    try:
        summarize_no_trade_audit(str(db_path), "MISSING")
    except ValueError as exc:
        assert "Backtest run not found" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing run")
