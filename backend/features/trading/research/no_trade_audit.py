"""
No-trade and blocked-trade audit helpers for agentic backtests.

This module reads stored backtest decisions/trades and summarizes why a run
produced little or no trade activity. It is intentionally read-only and can be
reused by CLI, API, or future UI surfaces.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from backend.features.trading.persistence.backtest_store import init_backtest_db, load_backtest_replay


def _extract_reason_text(decision: Dict[str, Any]) -> str:
    candidates: List[str] = []
    rejection_reason = decision.get("rejection_reason")
    if rejection_reason:
        candidates.append(str(rejection_reason))

    final_order = decision.get("final_order") or {}
    if isinstance(final_order, dict):
        for key in ("reasoning", "final_reasoning", "reason", "decision_reason"):
            value = final_order.get(key)
            if value:
                candidates.append(str(value))

    indicator_snapshot = decision.get("indicator_snapshot") or {}
    if isinstance(indicator_snapshot, dict):
        for key in ("reason", "reasoning", "regime_reason", "signal_reason"):
            value = indicator_snapshot.get(key)
            if value:
                candidates.append(str(value))

    return " | ".join(dict.fromkeys(candidate.strip() for candidate in candidates if candidate and candidate.strip()))


def _bucket_reason(text: str, status: str) -> str:
    normalized = f"{status}:{text}".lower()
    if not text:
        return f"{status.lower()}:unexplained"
    if "invalid sl/tp" in normalized or "risk/reward" in normalized:
        return f"{status.lower()}:guardrail_invalid_rr"
    if "lot size" in normalized:
        return f"{status.lower()}:guardrail_lot_size"
    if "validator" in normalized or "setup" in normalized:
        return f"{status.lower()}:validator_reject"
    if "tech analyst" in normalized or "no signal" in normalized or "market" in normalized and "not" in normalized:
        return f"{status.lower()}:no_candidate"
    if "hold" in normalized or "wait" in normalized:
        return f"{status.lower()}:hold"
    if "skip" in normalized:
        return f"{status.lower()}:skip"
    return f"{status.lower()}:other"


def summarize_no_trade_audit(db_path: str, run_id: str) -> Dict[str, Any]:
    """Summarize decision and trade outcomes for a given backtest run."""
    init_backtest_db(db_path)
    replay = load_backtest_replay(db_path, run_id)
    run = replay["run"]
    trades = replay["trades"]
    decisions = replay["decisions"]

    status_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    strategy_counts: Counter[str] = Counter()
    regime_counts: Counter[str] = Counter()
    rejection_reasons: Counter[str] = Counter()
    reason_buckets: Counter[str] = Counter()
    by_strategy_status: Dict[str, Counter[str]] = defaultdict(Counter)

    for decision in decisions:
        status = str(decision.get("status") or "UNKNOWN")
        action = str(decision.get("action") or "UNKNOWN")
        strategy = str(decision.get("strategy") or "N/A")
        regime = str(decision.get("market_regime") or "N/A")

        status_counts[status] += 1
        action_counts[action] += 1
        strategy_counts[strategy] += 1
        regime_counts[regime] += 1
        by_strategy_status[strategy][status] += 1

        reason_text = _extract_reason_text(decision)
        if status == "REJECTED" and reason_text:
            rejection_reasons[reason_text] += 1
        if status != "OPENED":
            reason_buckets[_bucket_reason(reason_text, status)] += 1

    opened = status_counts.get("OPENED", 0)
    rejected = status_counts.get("REJECTED", 0)
    held = status_counts.get("HOLD", 0)
    skipped = status_counts.get("SKIP", 0)
    errored = status_counts.get("ERROR", 0)
    total_decisions = len(decisions)
    total_trades = len(trades)

    trade_actions: Counter[str] = Counter()
    trade_results: Counter[str] = Counter()
    for trade in trades:
        trade_actions[str(trade.get("action") or "UNKNOWN")] += 1
        trade_results[str(trade.get("result") or "UNKNOWN")] += 1

    return {
        "run": run,
        "counts": {
            "decisions": total_decisions,
            "trades": total_trades,
            "opened": opened,
            "rejected": rejected,
            "hold": held,
            "skip": skipped,
            "error": errored,
            "opened_ratio": round((opened / total_decisions) * 100, 2) if total_decisions else 0.0,
            "trade_ratio": round((total_trades / total_decisions) * 100, 2) if total_decisions else 0.0,
        },
        "by_status": dict(status_counts),
        "by_action": dict(action_counts),
        "by_strategy": dict(strategy_counts),
        "by_market_regime": dict(regime_counts),
        "by_strategy_status": {strategy: dict(counts) for strategy, counts in by_strategy_status.items()},
        "trade_actions": dict(trade_actions),
        "trade_results": dict(trade_results),
        "rejection_reasons": rejection_reasons.most_common(10),
        "reason_buckets": reason_buckets.most_common(10),
        "sample_decisions": decisions[:10],
    }


def format_no_trade_audit(report: Dict[str, Any], *, sample_decisions_limit: int = 5) -> str:
    run = report.get("run", {})
    counts = report.get("counts", {})
    lines: List[str] = []
    lines.append("No-Trade Audit")
    lines.append(f"run_id: {run.get('run_id', 'N/A')}")
    lines.append(
        f"strategy: {run.get('symbol', 'N/A')} {run.get('base_timeframe', 'N/A')} "
        f"| status={run.get('status', 'N/A')} | trades={counts.get('trades', 0)} | decisions={counts.get('decisions', 0)}"
    )
    lines.append(
        f"opened={counts.get('opened', 0)} ({counts.get('opened_ratio', 0.0)}%) "
        f"rejected={counts.get('rejected', 0)} hold={counts.get('hold', 0)} "
        f"skip={counts.get('skip', 0)} error={counts.get('error', 0)}"
    )
    lines.append("")

    def _table(title: str, headers: List[str], rows: List[List[str]]) -> None:
        lines.append(title)
        if not rows:
            lines.append("  N/A")
            lines.append("")
            return
        widths = [len(header) for header in headers]
        for row in rows:
            for idx, value in enumerate(row):
                widths[idx] = max(widths[idx], len(value))

        def render(values: List[str]) -> str:
            return "  ".join(value.ljust(widths[idx]) for idx, value in enumerate(values))

        lines.append(render(headers))
        lines.append(render(["-" * width for width in widths]))
        for row in rows:
            lines.append(render(row))
        lines.append("")

    _table(
        "By Status",
        ["status", "count"],
        [[status, str(count)] for status, count in sorted(report.get("by_status", {}).items())],
    )
    _table(
        "By Strategy",
        ["strategy", "count"],
        [[strategy, str(count)] for strategy, count in sorted(report.get("by_strategy", {}).items())],
    )
    _table(
        "By Regime",
        ["regime", "count"],
        [[regime, str(count)] for regime, count in sorted(report.get("by_market_regime", {}).items())],
    )
    _table(
        "Trade Results",
        ["result", "count"],
        [[result, str(count)] for result, count in sorted(report.get("trade_results", {}).items())],
    )
    _table(
        "Reason Buckets",
        ["bucket", "count"],
        [[bucket, str(count)] for bucket, count in report.get("reason_buckets", [])],
    )
    _table(
        "Top Rejections",
        ["reason", "count"],
        [[reason, str(count)] for reason, count in report.get("rejection_reasons", [])],
    )

    sample_decisions = report.get("sample_decisions", [])[:sample_decisions_limit]
    lines.append("Sample Decisions")
    if not sample_decisions:
        lines.append("  N/A")
    else:
        for decision in sample_decisions:
            reason_text = _extract_reason_text(decision) or "N/A"
            lines.append(
                f"  {decision.get('decision_time', 'N/A')} | {decision.get('status', 'N/A')} | "
                f"{decision.get('action', 'N/A')} | {decision.get('strategy', 'N/A')} | "
                f"{decision.get('market_regime', 'N/A')} | {reason_text}"
            )
    return "\n".join(lines)
