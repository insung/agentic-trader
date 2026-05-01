"""
SQLite storage for trigger history and scheduling rules.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DEFAULT_TRIGGER_DB_PATH = os.path.join(PROJECT_ROOT, "trading_logs", "trigger_history.sqlite")

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS trigger_schedule_rules (
        rule_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        symbol TEXT NOT NULL,
        timeframes_json TEXT NOT NULL,
        mode TEXT NOT NULL DEFAULT 'paper',
        strategy_override TEXT,
        schedule_type TEXT NOT NULL, -- 'interval' or 'cron'
        cron_expression TEXT,
        interval_seconds INTEGER,
        timezone TEXT NOT NULL DEFAULT 'UTC',
        market_hours_only INTEGER NOT NULL DEFAULT 1,
        last_triggered_at TEXT,
        next_trigger_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trigger_runs (
        trigger_id TEXT PRIMARY KEY,
        rule_id TEXT,
        workflow_run_id TEXT,
        scheduled_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT,
        duration_ms INTEGER,
        symbol TEXT NOT NULL,
        timeframes_json TEXT NOT NULL,
        mode TEXT NOT NULL,
        strategy_override TEXT,
        status TEXT NOT NULL, -- 'scheduled', 'running', 'success', 'failed', 'blocked'
        workflow_status TEXT,
        final_action TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (rule_id) REFERENCES trigger_schedule_rules(rule_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trigger_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        trigger_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        node_name TEXT,
        message TEXT,
        payload_json TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (trigger_id) REFERENCES trigger_runs(trigger_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trigger_execution_snapshots (
        snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
        trigger_id TEXT NOT NULL UNIQUE,
        request_json TEXT,
        initial_state_json TEXT,
        final_state_json TEXT,
        final_order_json TEXT,
        decision_context_json TEXT,
        guardrail_result_json TEXT,
        strategy_snapshot_json TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (trigger_id) REFERENCES trigger_runs(trigger_id)
    )
    """,
    # Indexes
    "CREATE INDEX IF NOT EXISTS idx_trigger_runs_rule_id ON trigger_runs(rule_id)",
    "CREATE INDEX IF NOT EXISTS idx_trigger_runs_status ON trigger_runs(status)",
    "CREATE INDEX IF NOT EXISTS idx_trigger_runs_scheduled_at ON trigger_runs(scheduled_at)",
    "CREATE INDEX IF NOT EXISTS idx_trigger_events_trigger_id ON trigger_events(trigger_id)",
    "CREATE INDEX IF NOT EXISTS idx_trigger_rules_enabled ON trigger_schedule_rules(enabled)",
    "CREATE INDEX IF NOT EXISTS idx_trigger_rules_next_trigger ON trigger_schedule_rules(next_trigger_at)",
]

def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def _ensure_parent_dir(db_path: str) -> None:
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)

def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    target_path = db_path or DEFAULT_TRIGGER_DB_PATH
    _ensure_parent_dir(target_path)
    conn = sqlite3.connect(target_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_trigger_db(db_path: Optional[str] = None) -> None:
    with _connect(db_path) as conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        conn.commit()

def _json_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)

# --- Schedule Rules ---

def get_active_schedule_rules(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    init_trigger_db(db_path)
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM trigger_schedule_rules WHERE enabled = 1")
        return [dict(row) for row in cursor.fetchall()]

def upsert_schedule_rule(db_path: Optional[str] = None, rule: Dict[str, Any] = None) -> str:
    if rule is None:
        return ""
    init_trigger_db(db_path)
    rule_id = rule.get("rule_id") or str(uuid.uuid4())
    now = _now_iso()
    
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trigger_schedule_rules (
                rule_id, name, enabled, symbol, timeframes_json, mode,
                strategy_override, schedule_type, cron_expression, interval_seconds,
                timezone, market_hours_only, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rule_id) DO UPDATE SET
                name = excluded.name,
                enabled = excluded.enabled,
                symbol = excluded.symbol,
                timeframes_json = excluded.timeframes_json,
                mode = excluded.mode,
                strategy_override = excluded.strategy_override,
                schedule_type = excluded.schedule_type,
                cron_expression = excluded.cron_expression,
                interval_seconds = excluded.interval_seconds,
                timezone = excluded.timezone,
                market_hours_only = excluded.market_hours_only,
                updated_at = excluded.updated_at
            """,
            (
                rule_id,
                rule.get("name", "Unnamed Rule"),
                rule.get("enabled", 1),
                rule.get("symbol", "EURUSD"),
                _json_text(rule.get("timeframes", ["M5"])),
                rule.get("mode", "paper"),
                rule.get("strategy_override"),
                rule.get("schedule_type", "interval"),
                rule.get("cron_expression"),
                rule.get("interval_seconds"),
                rule.get("timezone", "UTC"),
                rule.get("market_hours_only", 1),
                rule.get("created_at", now),
                now
            )
        )
        conn.commit()
    return rule_id

def update_rule_last_triggered(db_path: Optional[str] = None, rule_id: str = "", last_triggered_at: str = "", next_trigger_at: Optional[str] = None):
    with _connect(db_path) as conn:
        if next_trigger_at:
            conn.execute(
                "UPDATE trigger_schedule_rules SET last_triggered_at = ?, next_trigger_at = ?, updated_at = ? WHERE rule_id = ?",
                (last_triggered_at, next_trigger_at, _now_iso(), rule_id)
            )
        else:
            conn.execute(
                "UPDATE trigger_schedule_rules SET last_triggered_at = ?, updated_at = ? WHERE rule_id = ?",
                (last_triggered_at, _now_iso(), rule_id)
            )
        conn.commit()

# --- Trigger Runs ---

def create_trigger_run(db_path: Optional[str] = None, run_data: Dict[str, Any] = None) -> str:
    if run_data is None:
        run_data = {}
    init_trigger_db(db_path)
    trigger_id = run_data.get("trigger_id") or f"trig_{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trigger_runs (
                trigger_id, rule_id, workflow_run_id, scheduled_at, started_at,
                symbol, timeframes_json, mode, strategy_override, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trigger_id,
                run_data.get("rule_id"),
                run_data.get("workflow_run_id"),
                run_data.get("scheduled_at", now),
                run_data.get("started_at"),
                run_data.get("symbol"),
                _json_text(run_data.get("timeframes", [])),
                run_data.get("mode", "paper"),
                run_data.get("strategy_override"),
                run_data.get("status", "scheduled"),
                run_data.get("created_at", now),
                run_data.get("updated_at", now)
            )
        )
        conn.commit()
    return trigger_id

def update_trigger_run(db_path: Optional[str] = None, trigger_id: str = "", updates: Dict[str, Any] = None):
    if updates is None:
        return
    init_trigger_db(db_path)
    now = _now_iso()
    
    fields = []
    values = []
    for k, v in updates.items():
        if k in ["workflow_run_id", "started_at", "finished_at", "duration_ms", "status", "workflow_status", "final_action", "error_message"]:
            fields.append(f"{k} = ?")
            values.append(v)
    
    if not fields:
        return
        
    fields.append("updated_at = ?")
    values.append(now)
    values.append(trigger_id)
    
    query = f"UPDATE trigger_runs SET {', '.join(fields)} WHERE trigger_id = ?"
    
    with _connect(db_path) as conn:
        conn.execute(query, tuple(values))
        conn.commit()

# --- Trigger Events ---

def add_trigger_event(db_path: Optional[str] = None, trigger_id: str = "", event_type: str = "", node_name: Optional[str] = None, message: Optional[str] = None, payload: Optional[Dict[str, Any]] = None):
    init_trigger_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trigger_events (
                trigger_id, event_type, node_name, message, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (trigger_id, event_type, node_name, message, _json_text(payload), _now_iso())
        )
        conn.commit()

# --- Snapshots ---

def save_trigger_snapshot(db_path: Optional[str] = None, trigger_id: str = "", snapshots: Dict[str, Any] = None):
    if snapshots is None:
        return
    init_trigger_db(db_path)
    now = _now_iso()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trigger_execution_snapshots (
                trigger_id, request_json, initial_state_json, final_state_json,
                final_order_json, decision_context_json, guardrail_result_json,
                strategy_snapshot_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trigger_id) DO UPDATE SET
                request_json = excluded.request_json,
                initial_state_json = excluded.initial_state_json,
                final_state_json = excluded.final_state_json,
                final_order_json = excluded.final_order_json,
                decision_context_json = excluded.decision_context_json,
                guardrail_result_json = excluded.guardrail_result_json,
                strategy_snapshot_json = excluded.strategy_snapshot_json
            """,
            (
                trigger_id,
                _json_text(snapshots.get("request")),
                _json_text(snapshots.get("initial_state")),
                _json_text(snapshots.get("final_state")),
                _json_text(snapshots.get("final_order")),
                _json_text(snapshots.get("decision_context")),
                _json_text(snapshots.get("guardrail_result")),
                _json_text(snapshots.get("strategy_snapshot")),
                now
            )
        )
        conn.commit()

def get_trigger_history(
    db_path: Optional[str] = None, 
    limit: int = 50, 
    status: Optional[str] = None, 
    symbol: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    init_trigger_db(db_path)
    query = "SELECT * FROM trigger_runs"
    params = []
    conditions = []
    
    if status:
        conditions.append("status = ?")
        params.append(status)
    if symbol:
        conditions.append("symbol = ?")
        params.append(symbol)
    if start_date:
        conditions.append("scheduled_at >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("scheduled_at <= ?")
        params.append(end_date)
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += " ORDER BY scheduled_at DESC LIMIT ?"
    params.append(limit)
    
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]

def get_trigger_run(db_path: Optional[str] = None, trigger_id: str = "") -> Optional[Dict[str, Any]]:
    init_trigger_db(db_path)
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM trigger_runs WHERE trigger_id = ?", (trigger_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_trigger_events(db_path: Optional[str] = None, trigger_id: str = "") -> List[Dict[str, Any]]:
    init_trigger_db(db_path)
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM trigger_events WHERE trigger_id = ? ORDER BY created_at ASC", (trigger_id,))
        return [dict(row) for row in cursor.fetchall()]

def get_trigger_snapshot(db_path: Optional[str] = None, trigger_id: str = "") -> Optional[Dict[str, Any]]:
    init_trigger_db(db_path)
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM trigger_execution_snapshots WHERE trigger_id = ?", (trigger_id,))
        row = cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        # Parse JSON fields for convenience
        for key in ["request_json", "initial_state_json", "final_state_json", "final_order_json", "decision_context_json", "guardrail_result_json", "strategy_snapshot_json"]:
            if data.get(key):
                try:
                    data[key.replace("_json", "")] = json.loads(data[key])
                except:
                    pass
        return data

def cleanup_trigger_history(db_path: Optional[str] = None, days_to_keep: int = 30):
    """
    Deletes trigger runs, events, and snapshots older than specified days.
    """
    init_trigger_db(db_path)
    with _connect(db_path) as conn:
        # Delete old runs (cascading deletes for events/snapshots if we had FKs with CASCADE, 
        # but we don't have all FKs set up that way, so we delete manually)
        
        # 1. Get IDs of runs to delete
        cursor = conn.execute(
            "SELECT trigger_id FROM trigger_runs WHERE created_at < datetime('now', ?)",
            (f"-{days_to_keep} days",)
        )
        ids_to_delete = [row[0] for row in cursor.fetchall()]
        
        if not ids_to_delete:
            return 0
            
        # 2. Delete from related tables
        placeholders = ", ".join(["?"] * len(ids_to_delete))
        conn.execute(f"DELETE FROM trigger_events WHERE trigger_id IN ({placeholders})", ids_to_delete)
        conn.execute(f"DELETE FROM trigger_execution_snapshots WHERE trigger_id IN ({placeholders})", ids_to_delete)
        conn.execute(f"DELETE FROM trigger_runs WHERE trigger_id IN ({placeholders})", ids_to_delete)
        
        conn.commit()
        return len(ids_to_delete)
