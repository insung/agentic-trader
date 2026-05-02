"""Backtest run, trade, decision, report, and replay persistence."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from backend.features.trading.persistence.market_data_store import load_candles
from backend.features.trading.persistence.schema import _connect, _now_iso, init_backtest_db


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
