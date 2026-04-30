from backend.features.trading import backtest_store
from backend.features.trading.quant_research import QuantResearchResult
from backend.features.trading.quant_summary import summarize_quant_runs


def test_summarize_quant_runs_returns_top_rank_per_run(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    backtest_store.persist_quant_research_result(
        str(db_path),
        QuantResearchResult(
            run={
                "run_id": "QR-BB",
                "strategy": "bollinger",
                "symbol": "BTCUSD",
                "timeframe": "M15",
                "data_from": "2025-01-01",
                "data_to": "2025-03-31",
                "init_cash": 10000.0,
                "fees": 0.0002,
                "slippage": 0.0002,
            },
            results=[
                {
                    "parameter_json": {"bb_window": 20, "rr": 1.3},
                    "total_return_pct": 3.5,
                    "total_trades": 132,
                    "win_rate": 52.0,
                    "profit_factor": 1.06,
                    "max_drawdown_pct": 10.9,
                    "sharpe": 0.4,
                    "expectancy": 1.2,
                    "rank": 1,
                },
                {
                    "parameter_json": {"bb_window": 14, "rr": 1.5},
                    "total_return_pct": 1.0,
                    "total_trades": 120,
                    "win_rate": 51.0,
                    "profit_factor": 1.01,
                    "max_drawdown_pct": 11.0,
                    "sharpe": 0.1,
                    "expectancy": 0.3,
                    "rank": 2,
                },
            ],
        ),
    )
    backtest_store.persist_quant_research_result(
        str(db_path),
        QuantResearchResult(
            run={
                "run_id": "QR-RECLAIM",
                "strategy": "trend_pullback_reclaim",
                "symbol": "BTCUSD",
                "timeframe": "M15",
                "data_from": "2025-01-01",
                "data_to": "2025-03-31",
                "init_cash": 10000.0,
                "fees": 0.0002,
                "slippage": 0.0002,
            },
            results=[
                {
                    "parameter_json": {
                        "filter_timeframe": "M30",
                        "reclaim_lookback": 8,
                        "rr": 2.0,
                    },
                    "total_return_pct": 2.2,
                    "total_trades": 122,
                    "win_rate": 49.0,
                    "profit_factor": 1.05,
                    "max_drawdown_pct": 10.4,
                    "sharpe": 0.2,
                    "expectancy": 0.8,
                    "rank": 1,
                }
            ],
        ),
    )

    rows = summarize_quant_runs(
        str(db_path),
        symbol="BTCUSD",
        from_date="2025-01-01",
        to_date="2025-03-31",
    )

    assert len(rows) == 2
    assert rows[0]["run_id"] == "QR-RECLAIM"
    assert rows[0]["timeframe_label"] == "M15/M30"
    assert rows[0]["rank"] == 1
    assert rows[0]["profit_factor"] == 1.05
    assert rows[1]["run_id"] == "QR-BB"
    assert rows[1]["timeframe_label"] == "M15"
