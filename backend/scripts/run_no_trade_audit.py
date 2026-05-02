"""
Summarize backtest decision/trade behavior for a given run_id.
"""
from __future__ import annotations

import argparse

from backend.features.trading.persistence.backtest_store import DEFAULT_BACKTEST_DB_PATH
from backend.features.trading.research.no_trade_audit import format_no_trade_audit, summarize_no_trade_audit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a no-trade audit for a stored backtest run")
    parser.add_argument("--data-db", default=DEFAULT_BACKTEST_DB_PATH)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sample-decisions-limit", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = summarize_no_trade_audit(args.data_db, args.run_id)
    print(format_no_trade_audit(report, sample_decisions_limit=args.sample_decisions_limit))


if __name__ == "__main__":
    main()
