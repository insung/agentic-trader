"""
SQLite storage for historical candles and agentic backtest results.

This module keeps the storage layer small and explicit: OHLCV rows are queried
by symbol/timeframe/time, while variable LLM payloads are stored as JSON text.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
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
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_parent_dir(db_path: str) -> None:
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def _connect(db_path: str) -> sqlite3.Connection:
    _ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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


def _normalize_time(value: Any) -> str:
    timestamp = pd.to_datetime(value)
    if getattr(timestamp, "tzinfo", None) is not None:
        timestamp = timestamp.tz_convert(None)
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def _normalize_query_bounds(from_date: str, to_date: str) -> Tuple[str, str]:
    start = pd.to_datetime(from_date)
    end = pd.to_datetime(to_date)
    if len(to_date.strip()) == 10:
        end = end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return _normalize_time(start), _normalize_time(end)


def create_import_batch(
    db_path: str,
    symbol: str,
    timeframes: Iterable[str],
    requested_from: str,
    requested_to: str,
    source: str = "mt5",
    status: str = "running",
) -> int:
    init_backtest_db(db_path)
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO data_import_batches (
                symbol, timeframes, requested_from, requested_to, source, created_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                ",".join(timeframes),
                requested_from,
                requested_to,
                source,
                _now_iso(),
                status,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def update_import_batch_status(
    db_path: str,
    batch_id: int,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    init_backtest_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE data_import_batches
            SET status = ?, error_message = ?
            WHERE id = ?
            """,
            (status, error_message, batch_id),
        )
        conn.commit()


def upsert_candles(
    db_path: str,
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    import_batch_id: Optional[int] = None,
) -> int:
    """Insert or update OHLCV candles keyed by symbol/timeframe/time."""
    init_backtest_db(db_path)
    if df.empty:
        return 0

    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required candle columns: {', '.join(missing)}")

    rows = []
    created_at = _now_iso()
    for item in df.to_dict(orient="records"):
        rows.append(
            (
                symbol,
                timeframe.upper(),
                _normalize_time(item["time"]),
                float(item["open"]),
                float(item["high"]),
                float(item["low"]),
                float(item["close"]),
                int(item.get("tick_volume", 0) or 0),
                int(item.get("spread", 0) or 0),
                int(item.get("real_volume", 0) or 0),
                import_batch_id,
                created_at,
            )
        )

    with _connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO candles (
                symbol, timeframe, time, open, high, low, close,
                tick_volume, spread, real_volume, import_batch_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, timeframe, time) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                tick_volume = excluded.tick_volume,
                spread = excluded.spread,
                real_volume = excluded.real_volume,
                import_batch_id = excluded.import_batch_id
            """,
            rows,
        )
        conn.commit()
    return len(rows)


def load_candles(
    db_path: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
) -> pd.DataFrame:
    """Load candles for a symbol/timeframe/date range as a sorted DataFrame."""
    init_backtest_db(db_path)
    start, end = _normalize_query_bounds(from_date, to_date)
    with _connect(db_path) as conn:
        df = pd.read_sql_query(
            """
            SELECT time, open, high, low, close, tick_volume, spread, real_volume
            FROM candles
            WHERE symbol = ?
              AND timeframe = ?
              AND time >= ?
              AND time <= ?
            ORDER BY time ASC
            """,
            conn,
            params=(symbol, timeframe.upper(), start, end),
            parse_dates=["time"],
        )
    return df


def calculate_candle_quality(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty or "time" not in df.columns:
        return {
            "candle_count": 0,
            "duplicate_count": 0,
            "start_time": None,
            "end_time": None,
            "median_interval": None,
            "max_gap": None,
        }

    times = pd.to_datetime(df["time"]).sort_values()
    diffs = times.diff().dropna()
    return {
        "candle_count": int(len(df)),
        "duplicate_count": int(times.duplicated().sum()),
        "start_time": _normalize_time(times.iloc[0]),
        "end_time": _normalize_time(times.iloc[-1]),
        "median_interval": str(diffs.median()) if not diffs.empty else None,
        "max_gap": str(diffs.max()) if not diffs.empty else None,
    }


def _json_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_value(value: Optional[str]) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _backtest_run_values(run: Dict[str, Any]) -> Tuple[Any, ...]:
    status = run.get("status")
    if not status:
        status = "completed" if run.get("final_balance") is not None else "running"
    completed_at = run.get("completed_at")
    if completed_at is None and status == "completed":
        completed_at = _now_iso()
    return (
        run["run_id"],
        run["symbol"],
        ",".join(run.get("timeframes", [])),
        run["base_timeframe"],
        run["data_from"],
        run["data_to"],
        float(run["initial_balance"]),
        float(run["final_balance"]) if run.get("final_balance") is not None else None,
        float(run["risk_per_trade_pct"]),
        int(run["step_interval"]),
        int(run.get("total_trades", 0)),
        run.get("net_pnl"),
        run.get("profit_factor"),
        run.get("max_drawdown_pct"),
        run.get("created_at", _now_iso()),
        status,
        completed_at,
        run.get("error_message"),
    )


def _trade_values(run_id: str, symbol: str, trade: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        run_id,
        trade.get("trade_id", ""),
        symbol,
        trade.get("strategy"),
        trade.get("market_regime"),
        trade.get("action", ""),
        trade.get("entry_time", trade.get("time", "")),
        trade.get("exit_time"),
        float(trade.get("entry_price", 0.0)),
        trade.get("exit_price"),
        float(trade.get("sl", 0.0)),
        float(trade.get("tp", 0.0)),
        float(trade.get("lot_size", 0.0)),
        trade.get("result"),
        trade.get("exit_reason"),
        trade.get("pnl"),
        trade.get("reasoning"),
    )


def _decision_values(run_id: str, decision: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        run_id,
        decision.get("decision_time", ""),
        decision.get("action", ""),
        decision.get("strategy"),
        decision.get("market_regime"),
        decision.get("status", ""),
        decision.get("rejection_reason"),
        _json_text(decision.get("indicator_snapshot")),
        _json_text(decision.get("final_order")),
    )


def start_backtest_run(db_path: str, run: Dict[str, Any]) -> str:
    """Create the run row before the long-running backtest loop starts."""
    init_backtest_db(db_path)
    run_id = run["run_id"]
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO backtest_runs (
                run_id, symbol, timeframes, base_timeframe, data_from, data_to,
                initial_balance, final_balance, risk_per_trade_pct, step_interval,
                total_trades, net_pnl, profit_factor, max_drawdown_pct, created_at,
                status, completed_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                symbol = excluded.symbol,
                timeframes = excluded.timeframes,
                base_timeframe = excluded.base_timeframe,
                data_from = excluded.data_from,
                data_to = excluded.data_to,
                initial_balance = excluded.initial_balance,
                final_balance = excluded.final_balance,
                risk_per_trade_pct = excluded.risk_per_trade_pct,
                step_interval = excluded.step_interval,
                total_trades = excluded.total_trades,
                net_pnl = excluded.net_pnl,
                profit_factor = excluded.profit_factor,
                max_drawdown_pct = excluded.max_drawdown_pct,
                status = excluded.status,
                completed_at = excluded.completed_at,
                error_message = excluded.error_message
            """,
            _backtest_run_values({**run, "final_balance": run.get("final_balance"), "status": "running"}),
        )
        conn.execute("DELETE FROM backtest_trades WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM backtest_decisions WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM lessons WHERE run_id = ?", (run_id,))
        conn.commit()
    return run_id


def record_backtest_trade(
    db_path: str,
    *,
    run_id: str,
    symbol: str,
    trade: Dict[str, Any],
) -> None:
    """Append one closed backtest trade immediately."""
    init_backtest_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            "DELETE FROM backtest_trades WHERE run_id = ? AND trade_id = ?",
            (run_id, trade.get("trade_id", "")),
        )
        conn.execute(
            """
            INSERT INTO backtest_trades (
                run_id, trade_id, symbol, strategy, market_regime, action,
                entry_time, exit_time, entry_price, exit_price, sl, tp,
                lot_size, result, exit_reason, pnl, reasoning
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _trade_values(run_id, symbol, trade),
        )
        conn.commit()


def record_backtest_decision(
    db_path: str,
    *,
    run_id: str,
    decision: Dict[str, Any],
) -> None:
    """Append one backtest decision immediately."""
    init_backtest_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO backtest_decisions (
                run_id, decision_time, action, strategy, market_regime, status,
                rejection_reason, indicator_snapshot_json, final_order_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _decision_values(run_id, decision),
        )
        conn.commit()


def finish_backtest_run(
    db_path: str,
    *,
    run_id: str,
    final_balance: float,
    total_trades: int,
    net_pnl: Optional[float],
    profit_factor: Optional[float],
    max_drawdown_pct: Optional[float],
) -> None:
    """Update final summary metrics after the loop has completed."""
    init_backtest_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE backtest_runs
            SET final_balance = ?,
                total_trades = ?,
                net_pnl = ?,
                profit_factor = ?,
                max_drawdown_pct = ?,
                status = 'completed',
                completed_at = ?,
                error_message = NULL
            WHERE run_id = ?
            """,
            (
                float(final_balance),
                int(total_trades),
                net_pnl,
                profit_factor,
                max_drawdown_pct,
                _now_iso(),
                run_id,
            ),
        )
        conn.commit()


def mark_backtest_run_status(
    db_path: str,
    *,
    run_id: str,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    """Mark a long-running backtest as interrupted or failed."""
    if status not in {"running", "completed", "interrupted", "failed"}:
        raise ValueError(f"Unsupported backtest run status: {status}")
    init_backtest_db(db_path)
    completed_at = _now_iso() if status in {"completed", "interrupted", "failed"} else None
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE backtest_runs
            SET status = ?,
                completed_at = ?,
                error_message = ?
            WHERE run_id = ?
            """,
            (status, completed_at, error_message, run_id),
        )
        conn.commit()


def persist_backtest_result(
    db_path: str,
    run: Dict[str, Any],
    trades: List[Dict[str, Any]],
    decisions: Optional[List[Dict[str, Any]]] = None,
    lessons: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Persist a backtest run and its structured outputs."""
    init_backtest_db(db_path)
    run_id = run["run_id"]
    decisions = decisions or []
    lessons = lessons or []
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO backtest_runs (
                run_id, symbol, timeframes, base_timeframe, data_from, data_to,
                initial_balance, final_balance, risk_per_trade_pct, step_interval,
                total_trades, net_pnl, profit_factor, max_drawdown_pct, created_at,
                status, completed_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                final_balance = excluded.final_balance,
                total_trades = excluded.total_trades,
                net_pnl = excluded.net_pnl,
                profit_factor = excluded.profit_factor,
                max_drawdown_pct = excluded.max_drawdown_pct,
                status = excluded.status,
                completed_at = excluded.completed_at,
                error_message = excluded.error_message
            """,
            _backtest_run_values({**run, "status": run.get("status", "completed")}),
        )
        conn.execute("DELETE FROM backtest_trades WHERE run_id = ?", (run_id,))
        conn.executemany(
            """
            INSERT INTO backtest_trades (
                run_id, trade_id, symbol, strategy, market_regime, action,
                entry_time, exit_time, entry_price, exit_price, sl, tp,
                lot_size, result, exit_reason, pnl, reasoning
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                _trade_values(run_id, run["symbol"], trade)
                for trade in trades
            ],
        )
        conn.execute("DELETE FROM backtest_decisions WHERE run_id = ?", (run_id,))
        conn.executemany(
            """
            INSERT INTO backtest_decisions (
                run_id, decision_time, action, strategy, market_regime, status,
                rejection_reason, indicator_snapshot_json, final_order_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                _decision_values(run_id, decision)
                for decision in decisions
            ],
        )
        conn.execute("DELETE FROM lessons WHERE run_id = ?", (run_id,))
        conn.executemany(
            """
            INSERT INTO lessons (
                run_id, trade_id, symbol, timeframe, strategy, market_regime,
                lesson_text, evidence_type, confidence, status, created_at, deprecated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    lesson.get("trade_id"),
                    lesson.get("symbol", run["symbol"]),
                    lesson.get("timeframe", run["base_timeframe"]),
                    lesson.get("strategy"),
                    lesson.get("market_regime"),
                    lesson.get("lesson_text", ""),
                    lesson.get("evidence_type", "backtest"),
                    float(lesson.get("confidence", 0.0)),
                    lesson.get("status", "candidate"),
                    lesson.get("created_at", _now_iso()),
                    lesson.get("deprecated_at"),
                )
                for lesson in lessons
            ],
        )
        conn.commit()
    return run_id


def store_backtest_report(
    db_path: str,
    *,
    report_id: str,
    run_id: Optional[str],
    symbol: str,
    report_path: Optional[str],
    markdown_body: str,
    chart_path: Optional[str] = None,
    report_created_at: Optional[str] = None,
    summary_json: Optional[Dict[str, Any]] = None,
) -> str:
    """Persist a markdown report artifact for later lookup."""
    init_backtest_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO backtest_reports (
                report_id, run_id, symbol, report_path, chart_path, report_created_at,
                markdown_body, summary_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_id) DO UPDATE SET
                run_id = excluded.run_id,
                symbol = excluded.symbol,
                report_path = excluded.report_path,
                chart_path = excluded.chart_path,
                report_created_at = excluded.report_created_at,
                markdown_body = excluded.markdown_body,
                summary_json = excluded.summary_json
            """,
            (
                report_id,
                run_id,
                symbol,
                report_path,
                chart_path,
                report_created_at,
                markdown_body,
                _json_text(summary_json) if summary_json is not None else None,
                _now_iso(),
            ),
        )
        conn.commit()
    return report_id


def load_backtest_replay(db_path: str, run_id: str) -> Dict[str, Any]:
    """Load the DB source-of-truth needed to reconstruct a backtest chart."""
    init_backtest_db(db_path)
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        run_row = conn.execute(
            """
            SELECT run_id, symbol, timeframes, base_timeframe, data_from, data_to,
                   initial_balance, final_balance, risk_per_trade_pct, step_interval,
                   total_trades, net_pnl, profit_factor, max_drawdown_pct,
                   created_at, status, completed_at, error_message
            FROM backtest_runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if run_row is None:
            raise ValueError(f"Backtest run not found: {run_id}")
        run = dict(run_row)

        trades = [
            dict(row)
            for row in conn.execute(
                """
                SELECT trade_id, symbol, strategy, market_regime, action,
                       entry_time, exit_time, entry_price, exit_price, sl, tp,
                       lot_size, result, exit_reason, pnl, reasoning
                FROM backtest_trades
                WHERE run_id = ?
                ORDER BY entry_time ASC, id ASC
                """,
                (run_id,),
            ).fetchall()
        ]

        decisions = []
        for row in conn.execute(
            """
            SELECT decision_time, action, strategy, market_regime, status,
                   rejection_reason, indicator_snapshot_json, final_order_json
            FROM backtest_decisions
            WHERE run_id = ?
            ORDER BY decision_time ASC, id ASC
            """,
            (run_id,),
        ).fetchall():
            decision = dict(row)
            decision["indicator_snapshot"] = _json_value(decision.pop("indicator_snapshot_json"))
            decision["final_order"] = _json_value(decision.pop("final_order_json"))
            decisions.append(decision)

    candles = load_candles(
        db_path,
        run["symbol"],
        run["base_timeframe"],
        run["data_from"],
        run["data_to"],
    )
    return {
        "run": run,
        "candles": candles.to_dict(orient="records"),
        "trades": trades,
        "decisions": decisions,
    }
