"""SQLite schema and initialization for backtest persistence."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from backend.features.trading.persistence.connection import PROJECT_ROOT, connect

DEFAULT_BACKTEST_DB_PATH = os.path.join(PROJECT_ROOT, "backtests", "data", "market_data.sqlite")


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS data_import_batches (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      symbol TEXT NOT NULL,
      timeframes TEXT NOT NULL,
      requested_from TEXT NOT NULL,
      requested_to TEXT NOT NULL,
      source TEXT NOT NULL DEFAULT 'mt5',
      created_at TEXT NOT NULL,
      status TEXT NOT NULL,
      error_message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS candles (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      symbol TEXT NOT NULL,
      timeframe TEXT NOT NULL,
      time TEXT NOT NULL,
      open REAL NOT NULL,
      high REAL NOT NULL,
      low REAL NOT NULL,
      close REAL NOT NULL,
      tick_volume INTEGER NOT NULL DEFAULT 0,
      spread INTEGER NOT NULL DEFAULT 0,
      real_volume INTEGER NOT NULL DEFAULT 0,
      import_batch_id INTEGER,
      created_at TEXT NOT NULL,
      FOREIGN KEY (import_batch_id) REFERENCES data_import_batches(id),
      UNIQUE (symbol, timeframe, time)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_candles_lookup
    ON candles (symbol, timeframe, time)
    """,
    """
    CREATE TABLE IF NOT EXISTS backtest_runs (
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
      created_at TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'running',
      completed_at TEXT,
      error_message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backtest_trades (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id TEXT NOT NULL,
      trade_id TEXT NOT NULL,
      symbol TEXT NOT NULL,
      strategy TEXT,
      market_regime TEXT,
      action TEXT NOT NULL,
      entry_time TEXT NOT NULL,
      exit_time TEXT,
      entry_price REAL NOT NULL,
      exit_price REAL,
      sl REAL NOT NULL,
      tp REAL NOT NULL,
      lot_size REAL NOT NULL,
      result TEXT,
      exit_reason TEXT,
      pnl REAL,
      reasoning TEXT,
      FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backtest_decisions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id TEXT NOT NULL,
      decision_time TEXT NOT NULL,
      action TEXT NOT NULL,
      strategy TEXT,
      market_regime TEXT,
      status TEXT NOT NULL,
      rejection_reason TEXT,
      indicator_snapshot_json TEXT,
      final_order_json TEXT,
      FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lessons (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id TEXT,
      trade_id TEXT,
      symbol TEXT NOT NULL,
      timeframe TEXT NOT NULL,
      strategy TEXT,
      market_regime TEXT,
      lesson_text TEXT NOT NULL,
      evidence_type TEXT NOT NULL,
      confidence REAL NOT NULL DEFAULT 0.0,
      status TEXT NOT NULL DEFAULT 'candidate',
      created_at TEXT NOT NULL,
      deprecated_at TEXT,
      FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backtest_reports (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      report_id TEXT NOT NULL UNIQUE,
      run_id TEXT,
      symbol TEXT NOT NULL,
      report_path TEXT,
      chart_path TEXT,
      report_created_at TEXT,
      markdown_body TEXT NOT NULL,
      summary_json TEXT,
      created_at TEXT NOT NULL,
      FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quant_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id TEXT NOT NULL UNIQUE,
      strategy TEXT NOT NULL,
      symbol TEXT NOT NULL,
      timeframe TEXT NOT NULL,
      data_from TEXT NOT NULL,
      data_to TEXT NOT NULL,
      init_cash REAL NOT NULL,
      fees REAL NOT NULL DEFAULT 0.0,
      slippage REAL NOT NULL DEFAULT 0.0,
      created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quant_results (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id TEXT NOT NULL,
      parameter_json TEXT NOT NULL,
      total_return_pct REAL,
      total_trades INTEGER NOT NULL DEFAULT 0,
      win_rate REAL,
      profit_factor REAL,
      max_drawdown_pct REAL,
      sharpe REAL,
      expectancy REAL,
      rank INTEGER NOT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY (run_id) REFERENCES quant_runs(run_id)
    )
    """,
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_parent_dir(db_path: str) -> None:
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def _connect(db_path: str) -> sqlite3.Connection:
    return connect(db_path)


def _ensure_backtest_run_columns(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(backtest_runs)").fetchall()}
    if "status" not in columns:
        conn.execute("ALTER TABLE backtest_runs ADD COLUMN status TEXT NOT NULL DEFAULT 'running'")
        conn.execute(
            """
            UPDATE backtest_runs
            SET status = CASE
                WHEN final_balance IS NULL THEN 'running'
                ELSE 'completed'
            END
            """
        )
    if "completed_at" not in columns:
        conn.execute("ALTER TABLE backtest_runs ADD COLUMN completed_at TEXT")
    if "error_message" not in columns:
        conn.execute("ALTER TABLE backtest_runs ADD COLUMN error_message TEXT")


def init_backtest_db(db_path: str = DEFAULT_BACKTEST_DB_PATH) -> None:
    """Create the SQLite schema if it does not exist."""
    with _connect(db_path) as conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        _ensure_backtest_run_columns(conn)
        conn.commit()
