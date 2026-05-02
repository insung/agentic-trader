from backend.features.trading import backtest_store
from backend.features.trading.research.quant_research import QuantResearchResult
from backend.features.trading.research.quant_summary import (
    format_quant_monthly_summary,
    format_quant_summary,
    summarize_quant_runs,
    summarize_quant_runs_by_month,
)


def test_legacy_quant_research_wrapper_reexports_public_contract():
    from backend.features.trading.quant_research import QuantResearchResult as LegacyQuantResearchResult

    assert LegacyQuantResearchResult is QuantResearchResult


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


def test_backtest_store_load_top_quant_results_returns_rank_one_rows(tmp_path):
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

    rows = backtest_store.load_top_quant_results(
        str(db_path),
        symbol="BTCUSD",
        from_date="2025-01-01",
        to_date="2025-03-31",
    )

    assert len(rows) == 1
    assert rows[0]["run_id"] == "QR-BB"
    assert rows[0]["rank"] == 1
    assert rows[0]["parameter_json"] == '{"bb_window": 20, "rr": 1.3}'


def test_summarize_quant_runs_filters_by_run_id(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    backtest_store.persist_quant_research_result(
        str(db_path),
        QuantResearchResult(
            run={
                "run_id": "QR-ONE",
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
                }
            ],
        ),
    )
    backtest_store.persist_quant_research_result(
        str(db_path),
        QuantResearchResult(
            run={
                "run_id": "QR-TWO",
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

    rows = summarize_quant_runs(str(db_path), run_id="QR-TWO")

    assert len(rows) == 1
    assert rows[0]["run_id"] == "QR-TWO"
    assert rows[0]["strategy"] == "trend_pullback_reclaim"


def test_summarize_quant_runs_by_month_returns_best_run_per_month(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    backtest_store.persist_quant_research_result(
        str(db_path),
        QuantResearchResult(
            run={
                "run_id": "QR-JAN-LOW",
                "strategy": "bollinger",
                "symbol": "BTCUSD",
                "timeframe": "M15",
                "data_from": "2025-01-01",
                "data_to": "2025-01-31",
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
                }
            ],
        ),
    )
    backtest_store.persist_quant_research_result(
        str(db_path),
        QuantResearchResult(
            run={
                "run_id": "QR-JAN-HIGH",
                "strategy": "trend_pullback_reclaim",
                "symbol": "BTCUSD",
                "timeframe": "M15",
                "data_from": "2025-01-15",
                "data_to": "2025-01-31",
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
                    "total_return_pct": 4.2,
                    "total_trades": 77,
                    "win_rate": 55.0,
                    "profit_factor": 1.2,
                    "max_drawdown_pct": 9.5,
                    "sharpe": 0.6,
                    "expectancy": 1.5,
                    "rank": 1,
                }
            ],
        ),
    )
    backtest_store.persist_quant_research_result(
        str(db_path),
        QuantResearchResult(
            run={
                "run_id": "QR-FEB",
                "strategy": "bollinger_mtf",
                "symbol": "BTCUSD",
                "timeframe": "M15",
                "data_from": "2025-02-01",
                "data_to": "2025-02-28",
                "init_cash": 10000.0,
                "fees": 0.0002,
                "slippage": 0.0002,
            },
            results=[
                {
                    "parameter_json": {
                        "filter_timeframe": "M30",
                        "bb_window": 30,
                        "rr": 1.5,
                    },
                    "total_return_pct": 1.6,
                    "total_trades": 25,
                    "win_rate": 49.0,
                    "profit_factor": 1.14,
                    "max_drawdown_pct": 5.7,
                    "sharpe": 0.3,
                    "expectancy": 0.8,
                    "rank": 1,
                }
            ],
        ),
    )

    rows = summarize_quant_runs_by_month(
        str(db_path),
        symbol="BTCUSD",
        from_date="2025-01-01",
        to_date="2025-02-28",
    )

    assert len(rows) == 2
    assert rows[0]["month_key"] == "2025-01"
    assert rows[0]["run_id"] == "QR-JAN-HIGH"
    assert rows[0]["month_run_count"] == 2
    assert rows[0]["profit_factor"] == 1.2
    assert rows[1]["month_key"] == "2025-02"
    assert rows[1]["run_id"] == "QR-FEB"


def test_summarize_quant_runs_by_month_filters_by_run_id(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    backtest_store.persist_quant_research_result(
        str(db_path),
        QuantResearchResult(
            run={
                "run_id": "QR-JAN",
                "strategy": "bollinger",
                "symbol": "BTCUSD",
                "timeframe": "M15",
                "data_from": "2025-01-01",
                "data_to": "2025-01-31",
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
                }
            ],
        ),
    )
    backtest_store.persist_quant_research_result(
        str(db_path),
        QuantResearchResult(
            run={
                "run_id": "QR-FEB",
                "strategy": "breakout",
                "symbol": "BTCUSD",
                "timeframe": "M15",
                "data_from": "2025-02-01",
                "data_to": "2025-02-28",
                "init_cash": 10000.0,
                "fees": 0.0002,
                "slippage": 0.0002,
            },
            results=[
                {
                    "parameter_json": {
                        "filter_timeframe": "M30",
                        "breakout_lookback": 30,
                        "rr": 1.5,
                    },
                    "total_return_pct": 1.6,
                    "total_trades": 25,
                    "win_rate": 49.0,
                    "profit_factor": 1.14,
                    "max_drawdown_pct": 5.7,
                    "sharpe": 0.3,
                    "expectancy": 0.8,
                    "rank": 1,
                }
            ],
        ),
    )

    rows = summarize_quant_runs_by_month(str(db_path), run_id="QR-FEB")

    assert len(rows) == 1
    assert rows[0]["month_key"] == "2025-02"
    assert rows[0]["run_id"] == "QR-FEB"


def test_format_quant_summary_does_not_truncate_parameters():
    text = format_quant_summary(
        [
            {
                "run_id": "QR-LONG",
                "strategy": "breakout",
                "timeframe_label": "M15/M30",
                "total_return_pct": 2.997,
                "profit_factor": 1.082,
                "max_drawdown_pct": 7.813,
                "total_trades": 125,
                "parameters": {
                    "ema_fast": 20,
                    "ema_slow": 50,
                    "filter_timeframe": "M30",
                    "breakout_lookback": 50,
                    "breakout_atr_buffer": 0.25,
                    "cooldown_bars": 20,
                    "atr_stop_multiplier": 1.0,
                    "breakout_rsi_lower": 50.0,
                    "breakout_rsi_upper": 50.0,
                    "rr": 1.3,
                },
            }
        ]
    )

    assert "breakout_lookback=50" in text
    assert "breakout_atr_buffer=0.25" in text
    assert "…" not in text


def test_format_quant_monthly_summary_does_not_truncate_parameters():
    text = format_quant_monthly_summary(
        [
            {
                "month_key": "2025-01",
                "run_id": "QR-LONG",
                "strategy": "breakout",
                "timeframe_label": "M15/M30",
                "total_return_pct": 2.997,
                "profit_factor": 1.082,
                "max_drawdown_pct": 7.813,
                "total_trades": 125,
                "month_run_count": 1,
                "parameters": {
                    "ema_fast": 20,
                    "ema_slow": 50,
                    "filter_timeframe": "M30",
                    "breakout_lookback": 50,
                    "breakout_atr_buffer": 0.25,
                    "cooldown_bars": 20,
                    "atr_stop_multiplier": 1.0,
                    "breakout_rsi_lower": 50.0,
                    "breakout_rsi_upper": 50.0,
                    "rr": 1.3,
                },
            }
        ]
    )

    assert "breakout_lookback=50" in text
    assert "breakout_atr_buffer=0.25" in text
    assert "…" not in text
