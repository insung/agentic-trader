"""
Print a compact summary of stored vectorbt quant research runs.
"""
from __future__ import annotations

import argparse

from backend.features.trading.backtest_store import DEFAULT_BACKTEST_DB_PATH
from backend.features.trading.quant_summary import format_quant_summary, summarize_quant_runs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize stored quant research runs")
    parser.add_argument("--data-db", default=DEFAULT_BACKTEST_DB_PATH)
    parser.add_argument("--symbol")
    parser.add_argument("--from", dest="from_date")
    parser.add_argument("--to", dest="to_date")
    parser.add_argument("--strategy")
    parser.add_argument("--limit", type=int, default=50)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = summarize_quant_runs(
        args.data_db,
        symbol=args.symbol,
        from_date=args.from_date,
        to_date=args.to_date,
        strategy=args.strategy,
        limit=args.limit,
    )
    print(format_quant_summary(rows))


if __name__ == "__main__":
    main()
