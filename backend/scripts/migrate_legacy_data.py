"""
Migrate legacy CSV/JSON/Markdown artifacts into SQLite stores.

The migration is idempotent: candle rows, backtest reports, trade reviews, and
run records use stable natural IDs so the script can be rerun safely.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from backend.features.trading.backtest_store import (
    DEFAULT_BACKTEST_DB_PATH,
    create_import_batch,
    persist_backtest_result,
    store_backtest_report,
    update_import_batch_status,
    upsert_candles,
)
from backend.features.trading.trading_log_store import (
    DEFAULT_TRADING_LOG_DB_PATH,
    replace_reviewed_trade_ids,
    replace_tracked_positions,
    store_trade_review,
)


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_BACKTEST_DIR = os.path.join(PROJECT_ROOT, "backtests")
DEFAULT_TRADING_LOGS_DIR = os.path.join(PROJECT_ROOT, "trading_logs")

CSV_PATTERN = re.compile(
    r"^(?P<symbol>.+)_(?P<start>\d{8})-(?P<end>\d{8})_(?P<timeframe>[A-Z0-9]+)(?:_legacy)?\.csv$"
)


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_csv_filename(path: str) -> Optional[Dict[str, str]]:
    match = CSV_PATTERN.match(os.path.basename(path))
    if not match:
        return None
    data = match.groupdict()
    data["timeframe"] = data["timeframe"].upper()
    return data


def _parse_date_yyyymmdd(value: str) -> str:
    return datetime.strptime(value, "%Y%m%d").strftime("%Y-%m-%d")


def migrate_backtest_csvs(backtest_dir: str, db_path: str) -> int:
    data_dir = os.path.join(backtest_dir, "data")
    migrated = 0
    for path in sorted(glob.glob(os.path.join(data_dir, "*.csv"))):
        parsed = _parse_csv_filename(path)
        if not parsed:
            continue
        df = pd.read_csv(path, parse_dates=["time"])
        batch_id = create_import_batch(
            db_path,
            symbol=parsed["symbol"],
            timeframes=[parsed["timeframe"]],
            requested_from=_parse_date_yyyymmdd(parsed["start"]),
            requested_to=_parse_date_yyyymmdd(parsed["end"]),
            source="legacy_csv",
        )
        try:
            upsert_candles(db_path, parsed["symbol"], parsed["timeframe"], df, import_batch_id=batch_id)
            update_import_batch_status(db_path, batch_id, "success")
            migrated += 1
        except BaseException as exc:
            update_import_batch_status(db_path, batch_id, "failed", str(exc))
            raise
    return migrated


def _stats_from_trades(trades: List[Dict[str, Any]], initial_balance: float, final_balance: float) -> Dict[str, Any]:
    pnls = [float(trade.get("pnl", 0.0) or 0.0) for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    gross_loss = abs(sum(losses))
    profit_factor = (sum(wins) / gross_loss) if gross_loss > 0 else None
    cumulative = initial_balance
    peak = initial_balance
    max_dd = 0.0
    for pnl in pnls:
        cumulative += pnl
        peak = max(peak, cumulative)
        if peak:
            max_dd = max(max_dd, (peak - cumulative) / peak * 100)
    return {
        "net_pnl": round(final_balance - initial_balance, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "max_drawdown_pct": round(max_dd, 2),
    }


def _run_dates_from_payload(payload: Dict[str, Any]) -> Tuple[str, str]:
    data_quality = payload.get("data_quality", {}) or {}
    if data_quality:
        starts = [item.get("start_time") for item in data_quality.values() if item.get("start_time")]
        ends = [item.get("end_time") for item in data_quality.values() if item.get("end_time")]
        if starts and ends:
            return min(starts), max(ends)

    trades = payload.get("trades", []) or []
    times = [trade.get("time") or trade.get("entry_time") for trade in trades if trade.get("time") or trade.get("entry_time")]
    exit_times = [trade.get("exit_time") for trade in trades if trade.get("exit_time")]
    if times:
        return min(times), max(exit_times or times)

    data_paths = payload.get("data_paths", []) or []
    parsed = [_parse_csv_filename(path) for path in data_paths]
    parsed = [item for item in parsed if item]
    if parsed:
        return _parse_date_yyyymmdd(min(item["start"] for item in parsed)), _parse_date_yyyymmdd(max(item["end"] for item in parsed))

    return "N/A", "N/A"


def _decisions_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if payload.get("decisions"):
        return payload["decisions"]
    decisions = []
    for item in payload.get("equity_curve", []) or []:
        action = str(item.get("action", "UNKNOWN"))
        decisions.append(
            {
                "decision_time": item.get("time", ""),
                "action": action,
                "status": action,
            }
        )
    return decisions


def migrate_backtest_results(backtest_dir: str, db_path: str) -> int:
    results_dir = os.path.join(backtest_dir, "results")
    migrated = 0
    for path in sorted(glob.glob(os.path.join(results_dir, "backtest_*.json"))):
        payload = _read_json(path, {})
        if not payload:
            continue
        symbol = payload.get("symbol", "UNKNOWN")
        run_id = payload.get("run_id") or os.path.splitext(os.path.basename(path))[0]
        timeframes = payload.get("timeframes", []) or [payload.get("base_timeframe", "N/A")]
        data_from, data_to = _run_dates_from_payload(payload)
        initial_balance = float(payload.get("initial_balance", 0.0))
        final_balance = float(payload.get("final_balance", initial_balance))
        trades = payload.get("trades", []) or []
        stats = _stats_from_trades(trades, initial_balance, final_balance)
        persist_backtest_result(
            db_path,
            run={
                "run_id": run_id,
                "symbol": symbol,
                "timeframes": timeframes,
                "base_timeframe": payload.get("base_timeframe") or timeframes[0],
                "data_from": data_from,
                "data_to": data_to,
                "initial_balance": initial_balance,
                "final_balance": final_balance,
                "risk_per_trade_pct": float(payload.get("risk_per_trade_pct", 0.0)),
                "step_interval": int(payload.get("step_interval", 0)),
                "total_trades": int(payload.get("total_trades", len(trades))),
                **stats,
            },
            trades=trades,
            decisions=_decisions_from_payload(payload),
        )
        migrated += 1
    return migrated


def _extract_markdown_section(body: str, heading: str) -> str:
    pattern = re.compile(rf"^## {re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(body)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^## ", body[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(body)
    return body[start:end].strip()


def _extract_date(body: str) -> Optional[str]:
    match = re.search(r"\*\*Date\*\*:\s*(.+)", body)
    if match:
        return match.group(1).strip()
    match = re.search(r"\*\*생성일시\*\*:\s*(.+?)(?:\s{2,}|$)", body)
    if match:
        return match.group(1).strip()
    return None


def _extract_report_symbol(body: str, path: str) -> str:
    match = re.search(r"^# .*Backtest Report:\s*(\S+)", body, re.MULTILINE)
    if match:
        return match.group(1).strip()
    match = re.match(r"backtest_(?P<symbol>.+?)_\d{8}_\d{6}\.md$", os.path.basename(path))
    return match.group("symbol") if match else "UNKNOWN"


def _extract_chart_path(body: str, report_path: str) -> Optional[str]:
    match = re.search(r"!\[Backtest Chart\]\(\./([^)]+)\)", body)
    if not match:
        return None
    return os.path.join(os.path.dirname(report_path), match.group(1))


def migrate_backtest_reports(backtest_dir: str, db_path: str) -> int:
    reports_dir = os.path.join(backtest_dir, "reports")
    migrated = 0
    for path in sorted(glob.glob(os.path.join(reports_dir, "backtest_*.md"))):
        body = _read_text(path)
        report_id = os.path.splitext(os.path.basename(path))[0]
        store_backtest_report(
            db_path,
            report_id=report_id,
            run_id=None,
            symbol=_extract_report_symbol(body, path),
            report_path=path,
            chart_path=_extract_chart_path(body, path),
            report_created_at=_extract_date(body),
            markdown_body=body,
            summary_json={"source": "legacy_markdown"},
        )
        migrated += 1
    return migrated


def migrate_trading_logs(trading_logs_dir: str, db_path: str) -> int:
    migrated = 0
    tracked = _read_json(os.path.join(trading_logs_dir, "tracked_positions.json"), [])
    reviewed = _read_json(os.path.join(trading_logs_dir, "reviewed_trades.json"), [])
    replace_tracked_positions(db_path, tracked if isinstance(tracked, list) else [])
    replace_reviewed_trade_ids(db_path, reviewed if isinstance(reviewed, list) else [], source="legacy_json")

    for path in sorted(glob.glob(os.path.join(trading_logs_dir, "review_*.md"))):
        body = _read_text(path)
        review_id = os.path.splitext(os.path.basename(path))[0]
        store_trade_review(
            db_path,
            review_id=review_id,
            trade_id=None,
            symbol=None,
            reviewed_at=_extract_date(body),
            source_path=path,
            summary=_extract_markdown_section(body, "Summary"),
            risk_assessment=_extract_markdown_section(body, "Risk Assessment"),
            lessons_learned=_extract_markdown_section(body, "Lessons Learned"),
            markdown_body=body,
            raw_payload={"source": "legacy_markdown"},
            source="legacy_markdown",
        )
        migrated += 1
    return migrated


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy backtest/trading logs into SQLite")
    parser.add_argument("--backtest-dir", default=DEFAULT_BACKTEST_DIR)
    parser.add_argument("--trading-logs-dir", default=DEFAULT_TRADING_LOGS_DIR)
    parser.add_argument("--backtest-db", default=DEFAULT_BACKTEST_DB_PATH)
    parser.add_argument("--trading-log-db", default=DEFAULT_TRADING_LOG_DB_PATH)
    parser.add_argument("--skip-backtests", action="store_true")
    parser.add_argument("--skip-trading-logs", action="store_true")
    args = parser.parse_args()

    if not args.skip_backtests:
        csv_count = migrate_backtest_csvs(args.backtest_dir, args.backtest_db)
        result_count = migrate_backtest_results(args.backtest_dir, args.backtest_db)
        report_count = migrate_backtest_reports(args.backtest_dir, args.backtest_db)
        print(f"Backtests migrated: csv_files={csv_count}, result_json={result_count}, reports={report_count}")

    if not args.skip_trading_logs:
        review_count = migrate_trading_logs(args.trading_logs_dir, args.trading_log_db)
        print(f"Trading logs migrated: reviews={review_count}")


if __name__ == "__main__":
    main()
