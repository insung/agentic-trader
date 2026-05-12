"""
SQLite storage for operational trading logs.

This store mirrors the existing `trading_logs/` JSON and markdown artifacts so
the runtime can keep the file outputs for human inspection while also writing a
queryable SQLite archive.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from backend.features.trading.persistence.connection import PROJECT_ROOT, connect

DEFAULT_TRADING_LOG_DB_PATH = os.path.join(PROJECT_ROOT, "trading_logs", "trading_logs.sqlite")


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS tracked_positions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      trade_id TEXT NOT NULL UNIQUE,
      ticket TEXT,
      mode TEXT NOT NULL,
      symbol TEXT NOT NULL,
      action TEXT NOT NULL,
      entry_time TEXT NOT NULL,
      entry_price REAL NOT NULL,
      sl REAL NOT NULL,
      tp REAL NOT NULL,
      lot_size REAL NOT NULL,
      order_result_json TEXT,
      decision_context_json TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tracked_positions_symbol_mode
    ON tracked_positions (symbol, mode)
    """,
    """
    CREATE TABLE IF NOT EXISTS reviewed_trade_ids (
      trade_id TEXT PRIMARY KEY,
      reviewed_at TEXT NOT NULL,
      source TEXT NOT NULL DEFAULT 'reconcile'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_reviews (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      review_id TEXT NOT NULL UNIQUE,
      trade_id TEXT,
      symbol TEXT,
      reviewed_at TEXT,
      source_path TEXT,
      summary TEXT,
      risk_assessment TEXT,
      process_quality TEXT,
      outcome_quality TEXT,
      trade_quality_label TEXT,
      rule_adherence INTEGER,
      lessons_learned TEXT,
      markdown_body TEXT NOT NULL,
      raw_payload_json TEXT,
      source TEXT NOT NULL DEFAULT 'risk_reviewer',
      created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_journals (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      trade_id TEXT NOT NULL UNIQUE,
      trigger_id TEXT,
      workflow_run_id TEXT,
      rule_id TEXT,
      mode TEXT NOT NULL,
      symbol TEXT NOT NULL,
      action TEXT NOT NULL,
      status TEXT NOT NULL,
      opened_at TEXT NOT NULL,
      closed_at TEXT,
      reviewed_at TEXT,
      entry_price REAL NOT NULL,
      exit_price REAL,
      sl REAL NOT NULL,
      tp REAL NOT NULL,
      lot_size REAL NOT NULL,
      result TEXT,
      exit_reason TEXT,
      strategy TEXT,
      market_regime TEXT,
      review_id TEXT,
      review_markdown_path TEXT,
      decision_context_json TEXT,
      order_result_json TEXT,
      closed_trade_json TEXT,
      review_log_json TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_trade_journals_trigger_id
    ON trade_journals (trigger_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_trade_journals_symbol_mode
    ON trade_journals (symbol, mode)
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


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _ensure_trade_review_quality_columns(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "trade_reviews")
    if not columns:
        return

    required_columns = {
        "process_quality": "TEXT",
        "outcome_quality": "TEXT",
        "trade_quality_label": "TEXT",
        "rule_adherence": "INTEGER",
    }
    for column_name, column_type in required_columns.items():
        if column_name not in columns:
            conn.execute(f"ALTER TABLE trade_reviews ADD COLUMN {column_name} {column_type}")


def init_trading_log_db(db_path: str = DEFAULT_TRADING_LOG_DB_PATH) -> None:
    with _connect(db_path) as conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        _ensure_trade_review_quality_columns(conn)
        conn.commit()


def _json_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def _parse_json(value: Optional[str]) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}


def replace_tracked_positions(db_path: str, positions: Iterable[Dict[str, Any]]) -> None:
    """Replace the tracked position set with the provided list."""
    init_trading_log_db(db_path)
    now = _now_iso()
    rows = []
    for position in positions:
        trade_id = str(position.get("trade_id"))
        if not trade_id:
            continue
        rows.append(
            (
                trade_id,
                str(position.get("ticket")) if position.get("ticket") is not None else None,
                position.get("mode", "paper"),
                position.get("symbol", ""),
                position.get("action", ""),
                position.get("entry_time", now),
                float(position.get("entry_price", 0.0)),
                float(position.get("sl", 0.0)),
                float(position.get("tp", 0.0)),
                float(position.get("lot_size", 0.0)),
                _json_text(position.get("order_result")),
                _json_text(position.get("decision_context")),
                position.get("created_at", now),
                now,
            )
        )

    with _connect(db_path) as conn:
        conn.execute("DELETE FROM tracked_positions")
        conn.executemany(
            """
            INSERT INTO tracked_positions (
                trade_id, ticket, mode, symbol, action, entry_time, entry_price,
                sl, tp, lot_size, order_result_json, decision_context_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def load_tracked_positions(db_path: str = DEFAULT_TRADING_LOG_DB_PATH) -> List[Dict[str, Any]]:
    init_trading_log_db(db_path)
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT trade_id, ticket, mode, symbol, action, entry_time, entry_price,
                   sl, tp, lot_size, order_result_json, decision_context_json,
                   created_at, updated_at
            FROM tracked_positions
            ORDER BY updated_at ASC, created_at ASC, id ASC
            """
        )
        rows = cursor.fetchall()

    positions: List[Dict[str, Any]] = []
    for row in rows:
        positions.append(
            {
                "trade_id": row[0],
                "ticket": row[1],
                "mode": row[2],
                "symbol": row[3],
                "action": row[4],
                "entry_time": row[5],
                "entry_price": row[6],
                "sl": row[7],
                "tp": row[8],
                "lot_size": row[9],
                "order_result": json.loads(row[10]) if row[10] else {},
                "decision_context": json.loads(row[11]) if row[11] else {},
                "created_at": row[12],
                "updated_at": row[13],
            }
        )
    return positions


def replace_reviewed_trade_ids(db_path: str, trade_ids: Iterable[str], *, source: str = "reconcile") -> None:
    init_trading_log_db(db_path)
    now = _now_iso()
    rows = [(str(trade_id), now, source) for trade_id in trade_ids if str(trade_id)]
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM reviewed_trade_ids")
        conn.executemany(
            """
            INSERT INTO reviewed_trade_ids (trade_id, reviewed_at, source)
            VALUES (?, ?, ?)
            ON CONFLICT(trade_id) DO UPDATE SET reviewed_at = excluded.reviewed_at, source = excluded.source
            """,
            rows,
        )
        conn.commit()


def load_reviewed_trade_ids(db_path: str = DEFAULT_TRADING_LOG_DB_PATH) -> List[str]:
    init_trading_log_db(db_path)
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT trade_id
            FROM reviewed_trade_ids
            ORDER BY reviewed_at ASC, trade_id ASC
            """
        )
        return [row[0] for row in cursor.fetchall()]


def mark_trade_reviewed(db_path: str, trade_id: str, *, source: str = "reconcile") -> None:
    init_trading_log_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO reviewed_trade_ids (trade_id, reviewed_at, source)
            VALUES (?, ?, ?)
            ON CONFLICT(trade_id) DO UPDATE SET reviewed_at = excluded.reviewed_at, source = excluded.source
            """,
            (str(trade_id), _now_iso(), source),
        )
        conn.commit()


def store_trade_review(
    db_path: str,
    *,
    review_id: str,
    trade_id: Optional[str],
    symbol: Optional[str],
    reviewed_at: Optional[str],
    source_path: Optional[str],
    summary: Optional[str],
    risk_assessment: Optional[str],
    process_quality: Optional[str] = None,
    outcome_quality: Optional[str] = None,
    trade_quality_label: Optional[str] = None,
    rule_adherence: Optional[bool] = None,
    lessons_learned: Optional[str] = None,
    markdown_body: str = "",
    raw_payload: Optional[Dict[str, Any]] = None,
    source: str = "risk_reviewer",
    ) -> str:
    init_trading_log_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trade_reviews (
                review_id, trade_id, symbol, reviewed_at, source_path,
                summary, risk_assessment, process_quality, outcome_quality,
                trade_quality_label, rule_adherence, lessons_learned, markdown_body,
                raw_payload_json, source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(review_id) DO UPDATE SET
                trade_id = excluded.trade_id,
                symbol = excluded.symbol,
                reviewed_at = excluded.reviewed_at,
                source_path = excluded.source_path,
                summary = excluded.summary,
                risk_assessment = excluded.risk_assessment,
                process_quality = excluded.process_quality,
                outcome_quality = excluded.outcome_quality,
                trade_quality_label = excluded.trade_quality_label,
                rule_adherence = excluded.rule_adherence,
                lessons_learned = excluded.lessons_learned,
                markdown_body = excluded.markdown_body,
                raw_payload_json = excluded.raw_payload_json,
                source = excluded.source
            """,
            (
                review_id,
                trade_id,
                symbol,
                reviewed_at,
                source_path,
                summary,
                risk_assessment,
                process_quality,
                outcome_quality,
                trade_quality_label,
                int(rule_adherence) if rule_adherence is not None else None,
                lessons_learned,
                markdown_body,
                _json_text(raw_payload),
                source,
                _now_iso(),
            ),
        )
        conn.commit()
    return review_id


def upsert_trade_journal(db_path: str, journal: Dict[str, Any]) -> Optional[str]:
    trade_id = str(journal.get("trade_id") or "").strip()
    if not trade_id:
        return None

    init_trading_log_db(db_path)
    now = _now_iso()
    row = {
        "trade_id": trade_id,
        "trigger_id": journal.get("trigger_id"),
        "workflow_run_id": journal.get("workflow_run_id"),
        "rule_id": journal.get("rule_id"),
        "mode": journal.get("mode", "paper"),
        "symbol": journal.get("symbol", ""),
        "action": str(journal.get("action", "")).upper(),
        "status": journal.get("status", "open"),
        "opened_at": journal.get("opened_at", journal.get("entry_time", now)),
        "closed_at": journal.get("closed_at"),
        "reviewed_at": journal.get("reviewed_at"),
        "entry_price": float(journal.get("entry_price", 0.0)),
        "exit_price": journal.get("exit_price"),
        "sl": float(journal.get("sl", 0.0)),
        "tp": float(journal.get("tp", 0.0)),
        "lot_size": float(journal.get("lot_size", 0.0)),
        "result": journal.get("result"),
        "exit_reason": journal.get("exit_reason"),
        "strategy": journal.get("strategy"),
        "market_regime": journal.get("market_regime"),
        "review_id": journal.get("review_id"),
        "review_markdown_path": journal.get("review_markdown_path"),
        "decision_context_json": _json_text(journal.get("decision_context")),
        "order_result_json": _json_text(journal.get("order_result")),
        "closed_trade_json": _json_text(journal.get("closed_trade")),
        "review_log_json": _json_text(journal.get("review_log")),
    }

    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trade_journals (
                trade_id, trigger_id, workflow_run_id, rule_id, mode, symbol,
                action, status, opened_at, closed_at, reviewed_at, entry_price,
                exit_price, sl, tp, lot_size, result, exit_reason, strategy,
                market_regime, review_id, review_markdown_path,
                decision_context_json, order_result_json, closed_trade_json,
                review_log_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_id) DO UPDATE SET
                trigger_id = COALESCE(excluded.trigger_id, trade_journals.trigger_id),
                workflow_run_id = COALESCE(excluded.workflow_run_id, trade_journals.workflow_run_id),
                rule_id = COALESCE(excluded.rule_id, trade_journals.rule_id),
                mode = excluded.mode,
                symbol = excluded.symbol,
                action = excluded.action,
                status = excluded.status,
                opened_at = COALESCE(excluded.opened_at, trade_journals.opened_at),
                closed_at = COALESCE(excluded.closed_at, trade_journals.closed_at),
                reviewed_at = COALESCE(excluded.reviewed_at, trade_journals.reviewed_at),
                entry_price = excluded.entry_price,
                exit_price = COALESCE(excluded.exit_price, trade_journals.exit_price),
                sl = excluded.sl,
                tp = excluded.tp,
                lot_size = excluded.lot_size,
                result = COALESCE(excluded.result, trade_journals.result),
                exit_reason = COALESCE(excluded.exit_reason, trade_journals.exit_reason),
                strategy = excluded.strategy,
                market_regime = excluded.market_regime,
                review_id = COALESCE(excluded.review_id, trade_journals.review_id),
                review_markdown_path = COALESCE(excluded.review_markdown_path, trade_journals.review_markdown_path),
                decision_context_json = COALESCE(excluded.decision_context_json, trade_journals.decision_context_json),
                order_result_json = COALESCE(excluded.order_result_json, trade_journals.order_result_json),
                closed_trade_json = COALESCE(excluded.closed_trade_json, trade_journals.closed_trade_json),
                review_log_json = COALESCE(excluded.review_log_json, trade_journals.review_log_json),
                updated_at = excluded.updated_at
            """,
            (
                row["trade_id"],
                row["trigger_id"],
                row["workflow_run_id"],
                row["rule_id"],
                row["mode"],
                row["symbol"],
                row["action"],
                row["status"],
                row["opened_at"],
                row["closed_at"],
                row["reviewed_at"],
                row["entry_price"],
                row["exit_price"],
                row["sl"],
                row["tp"],
                row["lot_size"],
                row["result"],
                row["exit_reason"],
                row["strategy"],
                row["market_regime"],
                row["review_id"],
                row["review_markdown_path"],
                row["decision_context_json"],
                row["order_result_json"],
                row["closed_trade_json"],
                row["review_log_json"],
                now,
                now,
            ),
        )
        conn.commit()
    return trade_id


def _row_to_trade_journal(row: sqlite3.Row) -> Dict[str, Any]:
    data = dict(row)
    data["decision_context"] = _parse_json(data.get("decision_context_json"))
    data["order_result"] = _parse_json(data.get("order_result_json"))
    data["closed_trade"] = _parse_json(data.get("closed_trade_json"))
    data["review_log"] = _parse_json(data.get("review_log_json"))
    return data


def get_trade_journal_by_trade_id(
    db_path: str = DEFAULT_TRADING_LOG_DB_PATH,
    trade_id: str = "",
) -> Optional[Dict[str, Any]]:
    init_trading_log_db(db_path)
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM trade_journals WHERE trade_id = ?",
            (str(trade_id),),
        ).fetchone()
        return _row_to_trade_journal(row) if row else None


def get_trade_journals_by_trigger(
    db_path: str = DEFAULT_TRADING_LOG_DB_PATH,
    trigger_id: str = "",
) -> List[Dict[str, Any]]:
    init_trading_log_db(db_path)
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM trade_journals WHERE trigger_id = ? ORDER BY opened_at ASC, id ASC",
            (str(trigger_id),),
        ).fetchall()
        return [_row_to_trade_journal(row) for row in rows]
