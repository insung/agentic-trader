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

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
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
      lessons_learned TEXT,
      markdown_body TEXT NOT NULL,
      raw_payload_json TEXT,
      source TEXT NOT NULL DEFAULT 'risk_reviewer',
      created_at TEXT NOT NULL
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


def init_trading_log_db(db_path: str = DEFAULT_TRADING_LOG_DB_PATH) -> None:
    with _connect(db_path) as conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        conn.commit()


def _json_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


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
    lessons_learned: Optional[str],
    markdown_body: str,
    raw_payload: Optional[Dict[str, Any]] = None,
    source: str = "risk_reviewer",
) -> str:
    init_trading_log_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trade_reviews (
                review_id, trade_id, symbol, reviewed_at, source_path,
                summary, risk_assessment, lessons_learned, markdown_body,
                raw_payload_json, source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(review_id) DO UPDATE SET
                trade_id = excluded.trade_id,
                symbol = excluded.symbol,
                reviewed_at = excluded.reviewed_at,
                source_path = excluded.source_path,
                summary = excluded.summary,
                risk_assessment = excluded.risk_assessment,
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
                lessons_learned,
                markdown_body,
                _json_text(raw_payload),
                source,
                _now_iso(),
            ),
        )
        conn.commit()
    return review_id
