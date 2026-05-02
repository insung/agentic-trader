"""Quant research result persistence and queries."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from backend.features.trading.persistence.backtest_result_store import _json_text
from backend.features.trading.persistence.schema import _connect, _now_iso, init_backtest_db


def persist_quant_research_result(db_path: str, result: Any) -> str:
    """Persist one vectorbt quant research run and its ranked parameter results."""
    init_backtest_db(db_path)
    run = result.run
    rows = result.results
    run_id = str(run["run_id"])
    created_at = _now_iso()

    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO quant_runs (
                run_id, strategy, symbol, timeframe, data_from, data_to,
                init_cash, fees, slippage, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                strategy = excluded.strategy,
                symbol = excluded.symbol,
                timeframe = excluded.timeframe,
                data_from = excluded.data_from,
                data_to = excluded.data_to,
                init_cash = excluded.init_cash,
                fees = excluded.fees,
                slippage = excluded.slippage
            """,
            (
                run_id,
                run["strategy"],
                run["symbol"],
                run["timeframe"],
                run["data_from"],
                run["data_to"],
                float(run["init_cash"]),
                float(run.get("fees", 0.0) or 0.0),
                float(run.get("slippage", 0.0) or 0.0),
                created_at,
            ),
        )
        conn.execute("DELETE FROM quant_results WHERE run_id = ?", (run_id,))
        conn.executemany(
            """
            INSERT INTO quant_results (
                run_id, parameter_json, total_return_pct, total_trades,
                win_rate, profit_factor, max_drawdown_pct, sharpe,
                expectancy, rank, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    _json_text(row.get("parameter_json", {})),
                    row.get("total_return_pct"),
                    int(row.get("total_trades", 0) or 0),
                    row.get("win_rate"),
                    row.get("profit_factor"),
                    row.get("max_drawdown_pct"),
                    row.get("sharpe"),
                    row.get("expectancy"),
                    int(row["rank"]),
                    created_at,
                )
                for row in rows
            ],
        )
        conn.commit()
    return run_id


def _quant_result_filters(
    *,
    run_id: Optional[str] = None,
    symbol: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    strategy: Optional[str] = None,
    monthly_bounds: bool = False,
) -> Tuple[List[str], List[Any]]:
    where = ["q.rank = 1"]
    params: List[Any] = []
    if run_id:
        where.append("qr.run_id = ?")
        params.append(run_id)
    if symbol:
        where.append("qr.symbol = ?")
        params.append(symbol)
    if from_date:
        if monthly_bounds:
            where.append("substr(qr.data_from, 1, 7) >= substr(?, 1, 7)")
        else:
            where.append("qr.data_from = ?")
        params.append(from_date)
    if to_date:
        if monthly_bounds:
            where.append("substr(qr.data_from, 1, 7) <= substr(?, 1, 7)")
        else:
            where.append("qr.data_to = ?")
        params.append(to_date)
    if strategy:
        where.append("qr.strategy = ?")
        params.append(strategy)
    return where, params


def load_top_quant_results(
    db_path: str,
    *,
    run_id: Optional[str] = None,
    symbol: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Load rank-1 quant results joined with quant run metadata."""
    init_backtest_db(db_path)
    where, params = _quant_result_filters(
        run_id=run_id,
        symbol=symbol,
        from_date=from_date,
        to_date=to_date,
        strategy=strategy,
    )
    params.append(limit)

    with _connect(db_path) as conn:
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
    return [dict(row) for row in rows]


def load_monthly_quant_results(
    db_path: str,
    *,
    run_id: Optional[str] = None,
    symbol: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    strategy: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Load rank-1 quant result candidates for month-level summaries."""
    init_backtest_db(db_path)
    where, params = _quant_result_filters(
        run_id=run_id,
        symbol=symbol,
        from_date=from_date,
        to_date=to_date,
        strategy=strategy,
        monthly_bounds=True,
    )

    with _connect(db_path) as conn:
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
    return [dict(row) for row in rows]
