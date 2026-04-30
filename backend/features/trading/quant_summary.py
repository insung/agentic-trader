"""
Summaries for vectorbt quant research runs stored in SQLite.
"""
from __future__ import annotations

import json
import sqlite3
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


def _fmt_float(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.3f}"
