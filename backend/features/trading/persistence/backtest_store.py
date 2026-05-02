"""Backward-compatible facade for backtest persistence stores.

The implementation is split by responsibility, but this module intentionally
keeps the historical import surface stable for existing backend code, scripts,
and tests.
"""
from __future__ import annotations

from backend.features.trading.persistence.schema import (
    DEFAULT_BACKTEST_DB_PATH,
    SCHEMA_STATEMENTS,
    _connect,
    _ensure_backtest_run_columns,
    _ensure_parent_dir,
    _now_iso,
    init_backtest_db,
)
from backend.features.trading.persistence.market_data_store import (
    _normalize_query_bounds,
    _normalize_time,
    calculate_candle_quality,
    create_import_batch,
    load_candles,
    update_import_batch_status,
    upsert_candles,
)
from backend.features.trading.persistence.backtest_result_store import (
    _backtest_run_values,
    _decision_values,
    _json_text,
    _json_value,
    _trade_values,
    finish_backtest_run,
    load_backtest_replay,
    mark_backtest_run_status,
    persist_backtest_result,
    record_backtest_decision,
    record_backtest_trade,
    start_backtest_run,
    store_backtest_report,
)
from backend.features.trading.persistence.quant_result_store import (
    _quant_result_filters,
    load_monthly_quant_results,
    load_top_quant_results,
    persist_quant_research_result,
)

__all__ = [
    "DEFAULT_BACKTEST_DB_PATH",
    "SCHEMA_STATEMENTS",
    "init_backtest_db",
    "create_import_batch",
    "update_import_batch_status",
    "upsert_candles",
    "load_candles",
    "calculate_candle_quality",
    "start_backtest_run",
    "record_backtest_trade",
    "record_backtest_decision",
    "finish_backtest_run",
    "mark_backtest_run_status",
    "persist_backtest_result",
    "store_backtest_report",
    "load_backtest_replay",
    "persist_quant_research_result",
    "load_top_quant_results",
    "load_monthly_quant_results",
]
