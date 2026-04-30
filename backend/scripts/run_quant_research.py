"""
Run fast vectorbt-backed quant research from the local candle SQLite store.

Example:
    python -m backend.scripts.run_quant_research --symbol BTCUSD --timeframe M15 --from 2025-01-01 --to 2025-01-31
"""
from __future__ import annotations

import argparse
from typing import List

from backend.features.trading.backtest_store import (
    DEFAULT_BACKTEST_DB_PATH,
    load_candles,
    persist_quant_research_result,
)
from backend.features.trading.quant_research import (
    QuantResearchConfig,
    run_bollinger_mtf_research,
    run_bollinger_research,
    run_trend_pullback_reclaim_research,
    run_trend_pullback_research,
)


def _parse_ints(value: str) -> List[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _parse_floats(value: str) -> List[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run vectorbt quant research from SQLite candles")
    parser.add_argument("--data-db", default=DEFAULT_BACKTEST_DB_PATH)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--filter-timeframe")
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", required=True)
    parser.add_argument(
        "--strategy",
        default="bollinger",
        choices=["bollinger", "bollinger_mtf", "trend_pullback", "trend_pullback_reclaim"],
    )
    parser.add_argument("--init-cash", type=float, default=10000.0)
    parser.add_argument("--fees", type=float, default=0.0)
    parser.add_argument("--slippage", type=float, default=0.0)
    parser.add_argument("--bb-windows", default="14,20,30")
    parser.add_argument("--bb-stds", default="1.8,2.0,2.2")
    parser.add_argument("--rsi-lowers", default="25,30,35")
    parser.add_argument("--rsi-uppers", default="65,70,75")
    parser.add_argument("--filter-rsi-lows", default="45")
    parser.add_argument("--filter-rsi-highs", default="55")
    parser.add_argument("--rrs", default="1.3,1.5,2.0")
    parser.add_argument("--stop-pcts", default="0.01")
    parser.add_argument("--ema-fast-windows", default="20")
    parser.add_argument("--ema-slow-windows", default="50")
    parser.add_argument("--pullback-atrs", default="0.25,0.5,0.75")
    parser.add_argument("--atr-stop-multipliers", default="1.0,1.5")
    parser.add_argument("--trend-rsi-lowers", default="45")
    parser.add_argument("--trend-rsi-uppers", default="55")
    parser.add_argument("--reclaim-lookbacks", default="3,5,8")
    parser.add_argument("--cooldown-bars", default="8,12,20")
    parser.add_argument("--top", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candles = load_candles(args.data_db, args.symbol, args.timeframe, args.from_date, args.to_date)
    if candles.empty:
        raise SystemExit(
            f"No candles found for {args.symbol} {args.timeframe} from {args.from_date} to {args.to_date}. "
            "Run `make backtest-fetch` first."
        )

    config = QuantResearchConfig(
        symbol=args.symbol,
        timeframe=args.timeframe,
        filter_timeframe=args.filter_timeframe,
        from_date=args.from_date,
        to_date=args.to_date,
        strategy=args.strategy,
        init_cash=args.init_cash,
        fees=args.fees,
        slippage=args.slippage,
        bb_windows=_parse_ints(args.bb_windows),
        bb_stds=_parse_floats(args.bb_stds),
        rsi_lowers=_parse_floats(args.rsi_lowers),
        rsi_uppers=_parse_floats(args.rsi_uppers),
        filter_rsi_lows=_parse_floats(args.filter_rsi_lows),
        filter_rsi_highs=_parse_floats(args.filter_rsi_highs),
        rrs=_parse_floats(args.rrs),
        stop_pcts=_parse_floats(args.stop_pcts),
        ema_fast_windows=_parse_ints(args.ema_fast_windows),
        ema_slow_windows=_parse_ints(args.ema_slow_windows),
        pullback_atrs=_parse_floats(args.pullback_atrs),
        atr_stop_multipliers=_parse_floats(args.atr_stop_multipliers),
        trend_rsi_lowers=_parse_floats(args.trend_rsi_lowers),
        trend_rsi_uppers=_parse_floats(args.trend_rsi_uppers),
        reclaim_lookbacks=_parse_ints(args.reclaim_lookbacks),
        cooldown_bars=_parse_ints(args.cooldown_bars),
    )
    if args.strategy in {"bollinger_mtf", "trend_pullback", "trend_pullback_reclaim"}:
        if not args.filter_timeframe:
            raise SystemExit(f"--filter-timeframe is required for {args.strategy}")
        filter_candles = load_candles(
            args.data_db,
            args.symbol,
            args.filter_timeframe,
            args.from_date,
            args.to_date,
        )
        if filter_candles.empty:
            raise SystemExit(
                f"No filter candles found for {args.symbol} {args.filter_timeframe} "
                f"from {args.from_date} to {args.to_date}. Run `make backtest-fetch` first."
            )
        if args.strategy == "bollinger_mtf":
            result = run_bollinger_mtf_research(candles, filter_candles, config)
        elif args.strategy == "trend_pullback":
            result = run_trend_pullback_research(candles, filter_candles, config)
        else:
            result = run_trend_pullback_reclaim_research(candles, filter_candles, config)
    else:
        result = run_bollinger_research(candles, config)
    run_id = persist_quant_research_result(args.data_db, result)

    print(f"✅ Quant research complete: {run_id}")
    if args.strategy in {"bollinger_mtf", "trend_pullback", "trend_pullback_reclaim"}:
        print(f"   Symbol/timeframes: {args.symbol} {args.timeframe}+{args.filter_timeframe}")
    else:
        print(f"   Symbol/timeframe: {args.symbol} {args.timeframe}")
    print(f"   Candles: {len(candles)}")
    print(f"   Parameter sets: {len(result.results)}")
    print("")
    print("Top results:")
    for row in result.results[: args.top]:
        params = row["parameter_json"]
        print(
            "  "
            f"#{row['rank']} trades={row['total_trades']} "
            f"return={row['total_return_pct']}% "
            f"pf={row['profit_factor']} "
            f"mdd={row['max_drawdown_pct']}% "
            f"params={params}"
        )


if __name__ == "__main__":
    main()
