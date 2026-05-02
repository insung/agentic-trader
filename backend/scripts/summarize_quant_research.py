"""
Print a compact summary of stored vectorbt quant research runs.
"""
from __future__ import annotations

import argparse

from backend.features.trading.persistence.backtest_store import DEFAULT_BACKTEST_DB_PATH
from backend.features.trading.research.quant_summary import (
    format_quant_monthly_summary,
    format_quant_summary,
    summarize_quant_runs,
    summarize_quant_runs_by_month,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize stored quant research runs")
    parser.add_argument("--data-db", default=DEFAULT_BACKTEST_DB_PATH)
    parser.add_argument("--run-id")
    parser.add_argument("--symbol")
    parser.add_argument("--from", dest="from_date")
    parser.add_argument("--to", dest="to_date")
    parser.add_argument("--strategy")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--monthly", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.monthly:
        rows = summarize_quant_runs_by_month(
            args.data_db,
            run_id=args.run_id,
            symbol=args.symbol,
            from_date=args.from_date,
            to_date=args.to_date,
            strategy=args.strategy,
            limit=args.limit,
        )
        print(format_quant_monthly_summary(rows))
    else:
        rows = summarize_quant_runs(
            args.data_db,
            run_id=args.run_id,
            symbol=args.symbol,
            from_date=args.from_date,
            to_date=args.to_date,
            strategy=args.strategy,
            limit=args.limit,
        )
        print(format_quant_summary(rows))


if __name__ == "__main__":
    main()
