"""
Summaries for vectorbt quant research runs stored in SQLite.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from typing import Any, Dict, List, Optional

from backend.features.trading.backtest_store import init_backtest_db


def _decode_json(value: Optional[str]) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def summarize_quant_runs(
    db_path: str,
    *,
    run_id: Optional[str] = None,
    symbol: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Return rank-1 quant results joined with run metadata."""
    init_backtest_db(db_path)
    where = ["q.rank = 1"]
    params: List[Any] = []
    if run_id:
        where.append("qr.run_id = ?")
        params.append(run_id)
    if symbol:
        where.append("qr.symbol = ?")
        params.append(symbol)
    if from_date:
        where.append("qr.data_from = ?")
        params.append(from_date)
    if to_date:
        where.append("qr.data_to = ?")
        params.append(to_date)
    if strategy:
        where.append("qr.strategy = ?")
        params.append(strategy)
    params.append(limit)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT
                qr.run_id,
                qr.strategy,
                qr.symbol,
                qr.timeframe,
                qr.data_from,
                qr.data_to,
                qr.fees,
                qr.slippage,
                qr.created_at,
                q.rank,
                q.total_return_pct,
                q.total_trades,
                q.win_rate,
                q.profit_factor,
                q.max_drawdown_pct,
                q.sharpe,
                q.expectancy,
                q.parameter_json
            FROM quant_runs qr
            JOIN quant_results q ON q.run_id = qr.run_id
            WHERE {" AND ".join(where)}
            ORDER BY qr.created_at DESC, qr.id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    summary: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        parameters = _decode_json(item.pop("parameter_json", None))
        filter_timeframe = parameters.get("filter_timeframe")
        item["parameters"] = parameters
        item["timeframe_label"] = (
            f"{item['timeframe']}/{filter_timeframe}" if filter_timeframe else item["timeframe"]
        )
        summary.append(item)
    return summary


def summarize_quant_runs_by_month(
    db_path: str,
    *,
    run_id: Optional[str] = None,
    symbol: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Return the best rank-1 quant result per `data_from` month."""
    init_backtest_db(db_path)
    where = ["q.rank = 1"]
    params: List[Any] = []
    if run_id:
        where.append("qr.run_id = ?")
        params.append(run_id)
    if symbol:
        where.append("qr.symbol = ?")
        params.append(symbol)
    if from_date:
        where.append("substr(qr.data_from, 1, 7) >= substr(?, 1, 7)")
        params.append(from_date)
    if to_date:
        where.append("substr(qr.data_from, 1, 7) <= substr(?, 1, 7)")
        params.append(to_date)
    if strategy:
        where.append("qr.strategy = ?")
        params.append(strategy)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT
                qr.id,
                qr.run_id,
                qr.strategy,
                qr.symbol,
                qr.timeframe,
                qr.data_from,
                qr.data_to,
                qr.fees,
                qr.slippage,
                qr.created_at,
                q.rank,
                q.total_return_pct,
                q.total_trades,
                q.win_rate,
                q.profit_factor,
                q.max_drawdown_pct,
                q.sharpe,
                q.expectancy,
                q.parameter_json
            FROM quant_runs qr
            JOIN quant_results q ON q.run_id = qr.run_id
            WHERE {" AND ".join(where)}
            ORDER BY qr.created_at DESC, qr.id DESC
            """,
            params,
        ).fetchall()

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        item = dict(row)
        month_key = str(item["data_from"])[:7]
        parameters = _decode_json(item.pop("parameter_json", None))
        filter_timeframe = parameters.get("filter_timeframe")
        item["parameters"] = parameters
        item["timeframe_label"] = (
            f"{item['timeframe']}/{filter_timeframe}" if filter_timeframe else item["timeframe"]
        )
        item["month_key"] = month_key
        grouped[month_key].append(item)

    summary: List[Dict[str, Any]] = []
    for month_key in sorted(grouped.keys()):
        candidates = grouped[month_key]
        best = sorted(candidates, key=_monthly_sort_key, reverse=True)[0]
        best["month_key"] = month_key
        best["month_run_count"] = len(candidates)
        summary.append(best)
        if len(summary) >= limit:
            break
    return summary


def format_quant_summary(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "No quant research runs found."

    headers = [
        "run_id",
        "strategy",
        "tf",
        "return%",
        "pf",
        "mdd%",
        "trades",
        "params",
    ]
    rendered_rows = []
    for row in rows:
        params = row.get("parameters", {})
        compact_params = ", ".join(f"{key}={value}" for key, value in params.items())
        rendered_rows.append(
            [
                str(row["run_id"]),
                str(row["strategy"]),
                str(row["timeframe_label"]),
                _fmt_float(row.get("total_return_pct")),
                _fmt_float(row.get("profit_factor")),
                _fmt_float(row.get("max_drawdown_pct")),
                str(row.get("total_trades", 0)),
                compact_params,
            ]
        )

    widths = [
        min(max(len(headers[index]), *(len(row[index]) for row in rendered_rows)), 48)
        for index in range(len(headers))
    ]

    def render_line(values: List[str]) -> str:
        cells = []
        for index, value in enumerate(values):
            truncated = value if len(value) <= widths[index] else value[: widths[index] - 1] + "…"
            cells.append(truncated.ljust(widths[index]))
        return "  ".join(cells)

    lines = [render_line(headers), render_line(["-" * width for width in widths])]
    lines.extend(render_line(row) for row in rendered_rows)
    return "\n".join(lines)


def format_quant_monthly_summary(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "No quant research runs found."

    headers = [
        "month",
        "run_id",
        "strategy",
        "tf",
        "return%",
        "pf",
        "mdd%",
        "trades",
        "runs",
        "params",
    ]
    rendered_rows = []
    for row in rows:
        params = row.get("parameters", {})
        compact_params = ", ".join(f"{key}={value}" for key, value in params.items())
        rendered_rows.append(
            [
                str(row["month_key"]),
                str(row["run_id"]),
                str(row["strategy"]),
                str(row["timeframe_label"]),
                _fmt_float(row.get("total_return_pct")),
                _fmt_float(row.get("profit_factor")),
                _fmt_float(row.get("max_drawdown_pct")),
                str(row.get("total_trades", 0)),
                str(row.get("month_run_count", 1)),
                compact_params,
            ]
        )

    widths = [
        min(max(len(headers[index]), *(len(row[index]) for row in rendered_rows)), 48)
        for index in range(len(headers))
    ]

    def render_line(values: List[str]) -> str:
        cells = []
        for index, value in enumerate(values):
            truncated = value if len(value) <= widths[index] else value[: widths[index] - 1] + "…"
            cells.append(truncated.ljust(widths[index]))
        return "  ".join(cells)

    lines = [render_line(headers), render_line(["-" * width for width in widths])]
    lines.extend(render_line(row) for row in rendered_rows)
    return "\n".join(lines)


def _fmt_float(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.3f}"


def _monthly_sort_key(row: Dict[str, Any]) -> tuple:
    profit_factor = row.get("profit_factor") if row.get("profit_factor") is not None else -1.0
    total_return = row.get("total_return_pct") if row.get("total_return_pct") is not None else -999999.0
    max_drawdown = row.get("max_drawdown_pct") if row.get("max_drawdown_pct") is not None else 999999.0
    created_at = row.get("created_at") or ""
    run_id = row.get("run_id") or ""
    return (profit_factor, total_return, -max_drawdown, created_at, run_id)
