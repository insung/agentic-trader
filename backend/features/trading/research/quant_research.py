"""
Fast deterministic strategy research helpers backed by vectorbt.

This module is intentionally separate from the agentic backtest runner. It reads
already-stored candles, generates mechanical signals, and lets vectorbt simulate
portfolio results for parameter sweeps.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class QuantResearchConfig:
    symbol: str
    timeframe: str
    from_date: str
    to_date: str
    strategy: str = "bollinger"
    init_cash: float = 10000.0
    fees: float = 0.0
    slippage: float = 0.0
    bb_windows: List[int] | None = None
    bb_stds: List[float] | None = None
    rsi_lowers: List[float] | None = None
    rsi_uppers: List[float] | None = None
    rrs: List[float] | None = None
    stop_pcts: List[float] | None = None
    filter_timeframe: str | None = None
    filter_rsi_lows: List[float] | None = None
    filter_rsi_highs: List[float] | None = None
    ema_fast_windows: List[int] | None = None
    ema_slow_windows: List[int] | None = None
    pullback_atrs: List[float] | None = None
    atr_stop_multipliers: List[float] | None = None
    trend_rsi_lowers: List[float] | None = None
    trend_rsi_uppers: List[float] | None = None
    reclaim_lookbacks: List[int] | None = None
    cooldown_bars: List[int] | None = None
    breakout_lookbacks: List[int] | None = None
    breakout_atr_buffers: List[float] | None = None
    breakout_rsi_lowers: List[float] | None = None
    breakout_rsi_uppers: List[float] | None = None
    ma_adx_mins: List[float] | None = None
    ma_max_cross_age_bars: List[int] | None = None
    macd_fast_windows: List[int] | None = None
    macd_slow_windows: List[int] | None = None
    macd_signal_windows: List[int] | None = None
    random_seed: int | None = 42
    random_entry_prob: float | None = 0.01
    random_long_bias: float | None = 0.5
    random_min_hold_bars: int | None = 3
    random_max_hold_bars: int | None = 12
    min_trades_for_rank: int = 20


@dataclass(frozen=True)
class QuantResearchResult:
    run: Dict[str, Any]
    results: List[Dict[str, Any]]


def _now_run_id(symbol: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"QR_{symbol}_{stamp}"


def _load_vectorbt():
    try:
        import vectorbt as vbt  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "vectorbt is not installed. Run `make install-quant` before `make quant-run`."
        ) from exc
    return vbt


def _timeframe_to_freq(timeframe: str) -> str:
    value = timeframe.upper()
    if value.startswith("M") and value[1:].isdigit():
        return f"{int(value[1:])}min"
    if value.startswith("H") and value[1:].isdigit():
        return f"{int(value[1:])}h"
    if value.startswith("D") and value[1:].isdigit():
        return f"{int(value[1:])}d"
    return timeframe


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window).mean()


def _adx(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    true_range = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(window).mean()
    plus_di = 100 * plus_dm.rolling(window).mean() / atr
    minus_di = 100 * minus_dm.rolling(window).mean() / atr
    di_sum = plus_di + minus_di
    dx = ((plus_di - minus_di).abs() / di_sum.replace(0, pd.NA)) * 100
    return dx.rolling(window).mean()


def _bollinger_parts(close: pd.Series, window: int, std_multiplier: float) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = close.rolling(window).mean()
    std = close.rolling(window).std()
    upper = mid + (std * std_multiplier)
    lower = mid - (std * std_multiplier)
    return mid, upper, lower


def _float_metric(stats: pd.Series, key: str) -> float | None:
    value = stats.get(key)
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return float(value)


def _int_metric(stats: pd.Series, key: str) -> int:
    value = stats.get(key, 0)
    if value is None or pd.isna(value):
        return 0
    if hasattr(value, "item"):
        value = value.item()
    return int(value)


def _rank_key(result: Dict[str, Any]) -> tuple:
    has_min_trades = result["total_trades"] >= result.get("min_trades_for_rank", 20)
    profit_factor = result["profit_factor"] if result["profit_factor"] is not None else -1.0
    max_drawdown = result["max_drawdown_pct"] if result["max_drawdown_pct"] is not None else 999999.0
    total_return = result["total_return_pct"] if result["total_return_pct"] is not None else -999999.0
    return (has_min_trades, profit_factor, -max_drawdown, total_return)


def _apply_cooldown(signals: pd.Series, bars: int) -> pd.Series:
    if bars <= 0:
        return signals.fillna(False).astype(bool)

    cooled = []
    last_signal_index = -bars - 1
    for index, value in enumerate(signals.fillna(False).astype(bool)):
        allow = bool(value) and (index - last_signal_index > bars)
        cooled.append(allow)
        if allow:
            last_signal_index = index
    return pd.Series(cooled, index=signals.index, dtype=bool)


def _bars_since_last_true(signals: pd.Series) -> pd.Series:
    active = signals.fillna(False).astype(bool)
    positions = pd.Series(range(len(active)), index=signals.index, dtype=float)
    last_true_positions = positions.where(active).ffill()
    age = positions - last_true_positions
    return age.fillna(len(active) + 1).astype(int)


def _build_random_trade_signals(
    length: int,
    seed: int,
    entry_prob: float,
    long_bias: float,
    min_hold_bars: int,
    max_hold_bars: int,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    rng = np.random.default_rng(seed)
    entries = pd.Series(False, index=range(length), dtype=bool)
    exits = pd.Series(False, index=range(length), dtype=bool)
    short_entries = pd.Series(False, index=range(length), dtype=bool)
    short_exits = pd.Series(False, index=range(length), dtype=bool)

    hold_min = max(1, int(min_hold_bars))
    hold_max = max(hold_min, int(max_hold_bars))
    flat_until = -1
    current_position: str | None = None
    exit_index = -1

    for index in range(length):
        if current_position is not None and index >= exit_index:
            if current_position == "long":
                exits.iloc[index] = True
            else:
                short_exits.iloc[index] = True
            current_position = None
            flat_until = index

        if current_position is not None:
            continue
        if index <= flat_until:
            continue
        if rng.random() >= entry_prob:
            continue

        if rng.random() < long_bias:
            entries.iloc[index] = True
            current_position = "long"
        else:
            short_entries.iloc[index] = True
            current_position = "short"

        hold_bars = int(rng.integers(hold_min, hold_max + 1))
        exit_index = min(index + hold_bars, length - 1)

    if current_position is not None and exit_index >= 0:
        if current_position == "long":
            exits.iloc[exit_index] = True
        else:
            short_exits.iloc[exit_index] = True

    return entries, exits, short_entries, short_exits


def run_bollinger_research(candles: pd.DataFrame, config: QuantResearchConfig) -> QuantResearchResult:
    """Run a Bollinger mean-reversion parameter sweep with vectorbt portfolios."""
    if candles.empty:
        raise ValueError("No candle data available for quant research")
    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(candles.columns))
    if missing:
        raise ValueError(f"Missing required candle columns: {', '.join(missing)}")

    vbt = _load_vectorbt()
    df = candles.sort_values("time").reset_index(drop=True).copy()
    close = df["close"].astype(float)

    bb_windows = config.bb_windows or [14, 20, 30]
    bb_stds = config.bb_stds or [1.8, 2.0, 2.2]
    rsi_lowers = config.rsi_lowers or [25.0, 30.0, 35.0]
    rsi_uppers = config.rsi_uppers or [65.0, 70.0, 75.0]
    rrs = config.rrs or [1.3, 1.5, 2.0]
    stop_pcts = config.stop_pcts or [0.01]
    rsi14 = _rsi(close, 14)
    freq = _timeframe_to_freq(config.timeframe)

    results: List[Dict[str, Any]] = []
    for bb_window in bb_windows:
        mid = close.rolling(bb_window).mean()
        std = close.rolling(bb_window).std()
        for bb_std in bb_stds:
            upper = mid + (std * bb_std)
            lower = mid - (std * bb_std)
            for rsi_lower in rsi_lowers:
                for rsi_upper in rsi_uppers:
                    long_entries = ((close <= lower) & (rsi14 <= rsi_lower)).fillna(False)
                    short_entries = ((close >= upper) & (rsi14 >= rsi_upper)).fillna(False)
                    long_exits = (close >= mid).fillna(False)
                    short_exits = (close <= mid).fillna(False)

                    for stop_pct in stop_pcts:
                        for rr in rrs:
                            portfolio = vbt.Portfolio.from_signals(
                                close,
                                entries=long_entries,
                                exits=long_exits,
                                short_entries=short_entries,
                                short_exits=short_exits,
                                init_cash=config.init_cash,
                                fees=config.fees,
                                slippage=config.slippage,
                                sl_stop=stop_pct,
                                tp_stop=stop_pct * rr,
                                freq=freq,
                            )
                            stats = portfolio.stats()
                            results.append(
                                {
                                    "parameter_json": {
                                        "bb_window": int(bb_window),
                                        "bb_std": float(bb_std),
                                        "rsi_lower": float(rsi_lower),
                                        "rsi_upper": float(rsi_upper),
                                        "stop_pct": float(stop_pct),
                                        "rr": float(rr),
                                    },
                                    "total_return_pct": _float_metric(stats, "Total Return [%]"),
                                    "total_trades": _int_metric(stats, "Total Trades"),
                                    "win_rate": _float_metric(stats, "Win Rate [%]"),
                                    "profit_factor": _float_metric(stats, "Profit Factor"),
                                    "max_drawdown_pct": _float_metric(stats, "Max Drawdown [%]"),
                                    "sharpe": _float_metric(stats, "Sharpe Ratio"),
                                    "expectancy": _float_metric(stats, "Expectancy"),
                                    "min_trades_for_rank": config.min_trades_for_rank,
                                }
                            )

    ranked = sorted(results, key=_rank_key, reverse=True)
    for index, item in enumerate(ranked, start=1):
        item.pop("min_trades_for_rank", None)
        item["rank"] = index

    return QuantResearchResult(
        run={
            "run_id": _now_run_id(config.symbol),
            "strategy": config.strategy,
            "symbol": config.symbol,
            "timeframe": config.timeframe.upper(),
            "data_from": config.from_date,
            "data_to": config.to_date,
            "init_cash": config.init_cash,
            "fees": config.fees,
            "slippage": config.slippage,
        },
        results=ranked,
    )


def run_buy_hold_research(candles: pd.DataFrame, config: QuantResearchConfig) -> QuantResearchResult:
    """Run a simple buy-and-hold benchmark."""
    if candles.empty:
        raise ValueError("No candle data available for buy and hold benchmark")
    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(candles.columns))
    if missing:
        raise ValueError(f"Missing required candle columns: {', '.join(missing)}")

    vbt = _load_vectorbt()
    df = candles.sort_values("time").reset_index(drop=True).copy()
    close = df["close"].astype(float)
    freq = _timeframe_to_freq(config.timeframe)
    entries = pd.Series(False, index=close.index, dtype=bool)
    exits = pd.Series(False, index=close.index, dtype=bool)
    if not close.empty:
        entries.iloc[0] = True
        exits.iloc[-1] = True

    portfolio = vbt.Portfolio.from_signals(
        close,
        entries=entries,
        exits=exits,
        init_cash=config.init_cash,
        fees=config.fees,
        slippage=config.slippage,
        freq=freq,
    )
    stats = portfolio.stats()
    result = {
        "parameter_json": {
            "benchmark": "buy_hold",
        },
        "total_return_pct": _float_metric(stats, "Total Return [%]"),
        "total_trades": _int_metric(stats, "Total Trades"),
        "win_rate": _float_metric(stats, "Win Rate [%]"),
        "profit_factor": _float_metric(stats, "Profit Factor"),
        "max_drawdown_pct": _float_metric(stats, "Max Drawdown [%]"),
        "sharpe": _float_metric(stats, "Sharpe Ratio"),
        "expectancy": _float_metric(stats, "Expectancy"),
        "min_trades_for_rank": 0,
    }
    result["rank"] = 1

    return QuantResearchResult(
        run={
            "run_id": _now_run_id(config.symbol),
            "strategy": "buy_hold",
            "symbol": config.symbol,
            "timeframe": config.timeframe.upper(),
            "data_from": config.from_date,
            "data_to": config.to_date,
            "init_cash": config.init_cash,
            "fees": config.fees,
            "slippage": config.slippage,
        },
        results=[result],
    )


def run_no_trade_research(candles: pd.DataFrame, config: QuantResearchConfig) -> QuantResearchResult:
    """Run a no-trade benchmark."""
    if candles.empty:
        raise ValueError("No candle data available for no-trade benchmark")
    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(candles.columns))
    if missing:
        raise ValueError(f"Missing required candle columns: {', '.join(missing)}")

    vbt = _load_vectorbt()
    df = candles.sort_values("time").reset_index(drop=True).copy()
    close = df["close"].astype(float)
    freq = _timeframe_to_freq(config.timeframe)
    empty_signals = pd.Series(False, index=close.index, dtype=bool)

    portfolio = vbt.Portfolio.from_signals(
        close,
        entries=empty_signals,
        exits=empty_signals,
        short_entries=empty_signals,
        short_exits=empty_signals,
        init_cash=config.init_cash,
        fees=config.fees,
        slippage=config.slippage,
        freq=freq,
    )
    stats = portfolio.stats()
    result = {
        "parameter_json": {
            "benchmark": "no_trade",
        },
        "total_return_pct": _float_metric(stats, "Total Return [%]"),
        "total_trades": _int_metric(stats, "Total Trades"),
        "win_rate": _float_metric(stats, "Win Rate [%]"),
        "profit_factor": _float_metric(stats, "Profit Factor"),
        "max_drawdown_pct": _float_metric(stats, "Max Drawdown [%]"),
        "sharpe": _float_metric(stats, "Sharpe Ratio"),
        "expectancy": _float_metric(stats, "Expectancy"),
        "min_trades_for_rank": 0,
    }
    result["rank"] = 1

    return QuantResearchResult(
        run={
            "run_id": _now_run_id(config.symbol),
            "strategy": "no_trade",
            "symbol": config.symbol,
            "timeframe": config.timeframe.upper(),
            "data_from": config.from_date,
            "data_to": config.to_date,
            "init_cash": config.init_cash,
            "fees": config.fees,
            "slippage": config.slippage,
        },
        results=[result],
    )


def run_random_research(candles: pd.DataFrame, config: QuantResearchConfig) -> QuantResearchResult:
    """Run a deterministic random trading benchmark."""
    if candles.empty:
        raise ValueError("No candle data available for random benchmark")
    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(candles.columns))
    if missing:
        raise ValueError(f"Missing required candle columns: {', '.join(missing)}")

    vbt = _load_vectorbt()
    df = candles.sort_values("time").reset_index(drop=True).copy()
    close = df["close"].astype(float)
    freq = _timeframe_to_freq(config.timeframe)

    seed = config.random_seed if config.random_seed is not None else 42
    entry_prob = config.random_entry_prob if config.random_entry_prob is not None else 0.01
    long_bias = config.random_long_bias if config.random_long_bias is not None else 0.5
    min_hold_bars = config.random_min_hold_bars if config.random_min_hold_bars is not None else 3
    max_hold_bars = config.random_max_hold_bars if config.random_max_hold_bars is not None else 12

    entries, exits, short_entries, short_exits = _build_random_trade_signals(
        len(close),
        int(seed),
        float(entry_prob),
        float(long_bias),
        int(min_hold_bars),
        int(max_hold_bars),
    )

    portfolio = vbt.Portfolio.from_signals(
        close,
        entries=entries,
        exits=exits,
        short_entries=short_entries,
        short_exits=short_exits,
        init_cash=config.init_cash,
        fees=config.fees,
        slippage=config.slippage,
        freq=freq,
    )
    stats = portfolio.stats()
    result = {
        "parameter_json": {
            "benchmark": "random",
            "seed": int(seed),
            "entry_prob": float(entry_prob),
            "long_bias": float(long_bias),
            "min_hold_bars": int(min_hold_bars),
            "max_hold_bars": int(max_hold_bars),
        },
        "total_return_pct": _float_metric(stats, "Total Return [%]"),
        "total_trades": _int_metric(stats, "Total Trades"),
        "win_rate": _float_metric(stats, "Win Rate [%]"),
        "profit_factor": _float_metric(stats, "Profit Factor"),
        "max_drawdown_pct": _float_metric(stats, "Max Drawdown [%]"),
        "sharpe": _float_metric(stats, "Sharpe Ratio"),
        "expectancy": _float_metric(stats, "Expectancy"),
        "min_trades_for_rank": 0,
    }
    result["rank"] = 1

    return QuantResearchResult(
        run={
            "run_id": _now_run_id(config.symbol),
            "strategy": "random",
            "symbol": config.symbol,
            "timeframe": config.timeframe.upper(),
            "data_from": config.from_date,
            "data_to": config.to_date,
            "init_cash": config.init_cash,
            "fees": config.fees,
            "slippage": config.slippage,
        },
        results=[result],
    )


def run_trend_pullback_research(
    candles: pd.DataFrame,
    filter_candles: pd.DataFrame,
    config: QuantResearchConfig,
) -> QuantResearchResult:
    """Run an EMA trend-pullback baseline with higher-timeframe confirmation."""
    if candles.empty:
        raise ValueError("No candle data available for trend pullback quant research")
    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(candles.columns))
    if missing:
        raise ValueError(f"Missing required candle columns: {', '.join(missing)}")
    if not config.filter_timeframe:
        raise ValueError("filter_timeframe is required for trend_pullback")

    vbt = _load_vectorbt()
    df = candles.sort_values("time").reset_index(drop=True).copy()
    df["time"] = pd.to_datetime(df["time"])
    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    low = df["low"].astype(float)
    high = df["high"].astype(float)
    rsi14 = _rsi(close, 14)
    atr14 = _atr(df, 14)
    merged_filter = _prepare_filter_frame(filter_candles, df["time"])

    ema_fast_windows = config.ema_fast_windows or [20]
    ema_slow_windows = config.ema_slow_windows or [50]
    pullback_atrs = config.pullback_atrs or [0.25, 0.5, 0.75]
    atr_stop_multipliers = config.atr_stop_multipliers or [1.0, 1.5]
    trend_rsi_lowers = config.trend_rsi_lowers or [45.0]
    trend_rsi_uppers = config.trend_rsi_uppers or [55.0]
    rrs = config.rrs or [1.3, 1.5, 2.0]
    freq = _timeframe_to_freq(config.timeframe)

    results: List[Dict[str, Any]] = []
    for ema_fast_window in ema_fast_windows:
        ema_fast = close.ewm(span=ema_fast_window, adjust=False).mean()
        for ema_slow_window in ema_slow_windows:
            ema_slow = close.ewm(span=ema_slow_window, adjust=False).mean()
            trend_up = ema_fast > ema_slow
            trend_down = ema_fast < ema_slow
            filter_up = merged_filter["filter_ema20"] > merged_filter["filter_ema50"]
            filter_down = merged_filter["filter_ema20"] < merged_filter["filter_ema50"]

            for pullback_atr in pullback_atrs:
                pullback_long = low <= (ema_fast + (atr14 * pullback_atr))
                pullback_short = high >= (ema_fast - (atr14 * pullback_atr))
                resume_long = (close > open_) & (close > ema_fast)
                resume_short = (close < open_) & (close < ema_fast)

                for trend_rsi_lower in trend_rsi_lowers:
                    for trend_rsi_upper in trend_rsi_uppers:
                        long_entries = (
                            trend_up
                            & filter_up
                            & pullback_long
                            & resume_long
                            & (rsi14 >= trend_rsi_lower)
                            & (rsi14 <= 70)
                        ).fillna(False)
                        short_entries = (
                            trend_down
                            & filter_down
                            & pullback_short
                            & resume_short
                            & (rsi14 <= trend_rsi_upper)
                            & (rsi14 >= 30)
                        ).fillna(False)
                        long_exits = ((close < ema_fast) | (ema_fast < ema_slow)).fillna(False)
                        short_exits = ((close > ema_fast) | (ema_fast > ema_slow)).fillna(False)

                        for atr_stop_multiplier in atr_stop_multipliers:
                            sl_stop = ((atr14 * atr_stop_multiplier) / close).clip(lower=0.0001)
                            for rr in rrs:
                                tp_stop = sl_stop * rr
                                portfolio = vbt.Portfolio.from_signals(
                                    close,
                                    entries=long_entries.astype(bool),
                                    exits=long_exits.astype(bool),
                                    short_entries=short_entries.astype(bool),
                                    short_exits=short_exits.astype(bool),
                                    init_cash=config.init_cash,
                                    fees=config.fees,
                                    slippage=config.slippage,
                                    sl_stop=sl_stop,
                                    tp_stop=tp_stop,
                                    freq=freq,
                                )
                                stats = portfolio.stats()
                                results.append(
                                    {
                                        "parameter_json": {
                                            "ema_fast": int(ema_fast_window),
                                            "ema_slow": int(ema_slow_window),
                                            "filter_timeframe": config.filter_timeframe.upper(),
                                            "pullback_atr": float(pullback_atr),
                                            "atr_stop_multiplier": float(atr_stop_multiplier),
                                            "trend_rsi_lower": float(trend_rsi_lower),
                                            "trend_rsi_upper": float(trend_rsi_upper),
                                            "rr": float(rr),
                                        },
                                        "total_return_pct": _float_metric(stats, "Total Return [%]"),
                                        "total_trades": _int_metric(stats, "Total Trades"),
                                        "win_rate": _float_metric(stats, "Win Rate [%]"),
                                        "profit_factor": _float_metric(stats, "Profit Factor"),
                                        "max_drawdown_pct": _float_metric(stats, "Max Drawdown [%]"),
                                        "sharpe": _float_metric(stats, "Sharpe Ratio"),
                                        "expectancy": _float_metric(stats, "Expectancy"),
                                        "min_trades_for_rank": config.min_trades_for_rank,
                                    }
                                )

    ranked = sorted(results, key=_rank_key, reverse=True)
    for index, item in enumerate(ranked, start=1):
        item.pop("min_trades_for_rank", None)
        item["rank"] = index

    return QuantResearchResult(
        run={
            "run_id": _now_run_id(config.symbol),
            "strategy": config.strategy,
            "symbol": config.symbol,
            "timeframe": config.timeframe.upper(),
            "filter_timeframe": config.filter_timeframe.upper(),
            "data_from": config.from_date,
            "data_to": config.to_date,
            "init_cash": config.init_cash,
            "fees": config.fees,
            "slippage": config.slippage,
        },
        results=ranked,
    )


def run_trend_pullback_reclaim_research(
    candles: pd.DataFrame,
    filter_candles: pd.DataFrame,
    config: QuantResearchConfig,
) -> QuantResearchResult:
    """Run a stricter EMA reclaim trend-pullback baseline with cooldown."""
    if candles.empty:
        raise ValueError("No candle data available for trend pullback reclaim quant research")
    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(candles.columns))
    if missing:
        raise ValueError(f"Missing required candle columns: {', '.join(missing)}")
    if not config.filter_timeframe:
        raise ValueError("filter_timeframe is required for trend_pullback_reclaim")

    vbt = _load_vectorbt()
    df = candles.sort_values("time").reset_index(drop=True).copy()
    df["time"] = pd.to_datetime(df["time"])
    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    rsi14 = _rsi(close, 14)
    atr14 = _atr(df, 14)
    merged_filter = _prepare_filter_frame(filter_candles, df["time"])

    ema_fast_windows = config.ema_fast_windows or [20]
    ema_slow_windows = config.ema_slow_windows or [50]
    reclaim_lookbacks = config.reclaim_lookbacks or [3, 5, 8]
    cooldown_bars = config.cooldown_bars or [8, 12, 20]
    atr_stop_multipliers = config.atr_stop_multipliers or [2.0, 3.0]
    trend_rsi_lowers = config.trend_rsi_lowers or [50.0]
    trend_rsi_uppers = config.trend_rsi_uppers or [50.0]
    rrs = config.rrs or [2.0, 3.0]
    freq = _timeframe_to_freq(config.timeframe)

    results: List[Dict[str, Any]] = []
    for ema_fast_window in ema_fast_windows:
        ema_fast = close.ewm(span=ema_fast_window, adjust=False).mean()
        for ema_slow_window in ema_slow_windows:
            ema_slow = close.ewm(span=ema_slow_window, adjust=False).mean()
            trend_up = ema_fast > ema_slow
            trend_down = ema_fast < ema_slow
            filter_up = (
                (merged_filter["filter_close"] > merged_filter["filter_ema20"])
                & (merged_filter["filter_ema20"] > merged_filter["filter_ema50"])
            )
            filter_down = (
                (merged_filter["filter_close"] < merged_filter["filter_ema20"])
                & (merged_filter["filter_ema20"] < merged_filter["filter_ema50"])
            )

            for reclaim_lookback in reclaim_lookbacks:
                recent_below_fast = close.shift(1).lt(ema_fast.shift(1)).rolling(reclaim_lookback).max().fillna(0).astype(bool)
                recent_above_fast = close.shift(1).gt(ema_fast.shift(1)).rolling(reclaim_lookback).max().fillna(0).astype(bool)
                recent_rsi_low = rsi14.shift(1).le(45).rolling(reclaim_lookback).max().fillna(0).astype(bool)
                recent_rsi_high = rsi14.shift(1).ge(55).rolling(reclaim_lookback).max().fillna(0).astype(bool)
                reclaim_long = (close > ema_fast) & (close.shift(1) <= ema_fast.shift(1))
                reclaim_short = (close < ema_fast) & (close.shift(1) >= ema_fast.shift(1))
                bullish_resume = close > open_
                bearish_resume = close < open_

                for trend_rsi_lower in trend_rsi_lowers:
                    for trend_rsi_upper in trend_rsi_uppers:
                        base_long_entries = (
                            trend_up
                            & filter_up
                            & recent_below_fast
                            & reclaim_long
                            & bullish_resume
                            & recent_rsi_low
                            & (rsi14 >= trend_rsi_lower)
                        ).fillna(False)
                        base_short_entries = (
                            trend_down
                            & filter_down
                            & recent_above_fast
                            & reclaim_short
                            & bearish_resume
                            & recent_rsi_high
                            & (rsi14 <= trend_rsi_upper)
                        ).fillna(False)
                        long_exits = ((close < ema_slow) | (ema_fast < ema_slow)).fillna(False)
                        short_exits = ((close > ema_slow) | (ema_fast > ema_slow)).fillna(False)

                        for cooldown in cooldown_bars:
                            long_entries = _apply_cooldown(base_long_entries, cooldown)
                            short_entries = _apply_cooldown(base_short_entries, cooldown)
                            for atr_stop_multiplier in atr_stop_multipliers:
                                sl_stop = ((atr14 * atr_stop_multiplier) / close).clip(lower=0.0001)
                                for rr in rrs:
                                    tp_stop = sl_stop * rr
                                    portfolio = vbt.Portfolio.from_signals(
                                        close,
                                        entries=long_entries.astype(bool),
                                        exits=long_exits.astype(bool),
                                        short_entries=short_entries.astype(bool),
                                        short_exits=short_exits.astype(bool),
                                        init_cash=config.init_cash,
                                        fees=config.fees,
                                        slippage=config.slippage,
                                        sl_stop=sl_stop,
                                        tp_stop=tp_stop,
                                        freq=freq,
                                    )
                                    stats = portfolio.stats()
                                    results.append(
                                        {
                                            "parameter_json": {
                                                "ema_fast": int(ema_fast_window),
                                                "ema_slow": int(ema_slow_window),
                                                "filter_timeframe": config.filter_timeframe.upper(),
                                                "reclaim_lookback": int(reclaim_lookback),
                                                "cooldown_bars": int(cooldown),
                                                "atr_stop_multiplier": float(atr_stop_multiplier),
                                                "trend_rsi_lower": float(trend_rsi_lower),
                                                "trend_rsi_upper": float(trend_rsi_upper),
                                                "rr": float(rr),
                                            },
                                            "total_return_pct": _float_metric(stats, "Total Return [%]"),
                                            "total_trades": _int_metric(stats, "Total Trades"),
                                            "win_rate": _float_metric(stats, "Win Rate [%]"),
                                            "profit_factor": _float_metric(stats, "Profit Factor"),
                                            "max_drawdown_pct": _float_metric(stats, "Max Drawdown [%]"),
                                            "sharpe": _float_metric(stats, "Sharpe Ratio"),
                                            "expectancy": _float_metric(stats, "Expectancy"),
                                            "min_trades_for_rank": config.min_trades_for_rank,
                                        }
                                    )

    ranked = sorted(results, key=_rank_key, reverse=True)
    for index, item in enumerate(ranked, start=1):
        item.pop("min_trades_for_rank", None)
        item["rank"] = index

    return QuantResearchResult(
        run={
            "run_id": _now_run_id(config.symbol),
            "strategy": config.strategy,
            "symbol": config.symbol,
            "timeframe": config.timeframe.upper(),
            "filter_timeframe": config.filter_timeframe.upper(),
            "data_from": config.from_date,
            "data_to": config.to_date,
            "init_cash": config.init_cash,
            "fees": config.fees,
            "slippage": config.slippage,
        },
        results=ranked,
    )


def run_ma_crossover_research(
    candles: pd.DataFrame,
    filter_candles: pd.DataFrame,
    config: QuantResearchConfig,
) -> QuantResearchResult:
    """Run an MA crossover baseline with higher-timeframe confirmation."""
    if candles.empty:
        raise ValueError("No candle data available for MA crossover quant research")
    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(candles.columns))
    if missing:
        raise ValueError(f"Missing required candle columns: {', '.join(missing)}")
    if not config.filter_timeframe:
        raise ValueError("filter_timeframe is required for ma_crossover")

    vbt = _load_vectorbt()
    df = candles.sort_values("time").reset_index(drop=True).copy()
    df["time"] = pd.to_datetime(df["time"])
    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    atr14 = _atr(df, 14)
    adx14 = _adx(df, 14)
    merged_filter = _prepare_filter_frame(filter_candles, df["time"])

    ema_fast_windows = config.ema_fast_windows or [20]
    ema_slow_windows = config.ema_slow_windows or [50]
    ma_adx_mins = config.ma_adx_mins or [25.0, 30.0]
    ma_max_cross_age_bars = config.ma_max_cross_age_bars or [3, 6]
    cooldown_bars = config.cooldown_bars or [8, 12, 20]
    atr_stop_multipliers = config.atr_stop_multipliers or [1.0, 1.5]
    rrs = config.rrs or [2.0, 3.0]
    max_cross_age_cap = max(ma_max_cross_age_bars)
    freq = _timeframe_to_freq(config.timeframe)

    results: List[Dict[str, Any]] = []
    for ema_fast_window in ema_fast_windows:
        ema_fast = close.ewm(span=ema_fast_window, adjust=False).mean()
        for ema_slow_window in ema_slow_windows:
            ema_slow = close.ewm(span=ema_slow_window, adjust=False).mean()
            bullish_cross = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
            bearish_cross = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))
            bullish_cross_age = _bars_since_last_true(bullish_cross)
            bearish_cross_age = _bars_since_last_true(bearish_cross)
            trend_up = ema_fast > ema_slow
            trend_down = ema_fast < ema_slow

            filter_bullish = (
                (merged_filter["filter_close"] > merged_filter["filter_ema20"])
                & (merged_filter["filter_ema20"] > merged_filter["filter_ema50"])
                & (merged_filter["filter_adx14"] >= 25)
            )
            filter_bearish = (
                (merged_filter["filter_close"] < merged_filter["filter_ema20"])
                & (merged_filter["filter_ema20"] < merged_filter["filter_ema50"])
                & (merged_filter["filter_adx14"] >= 25)
            )

            for ma_adx_min in ma_adx_mins:
                base_long_entries = (
                    trend_up
                    & filter_bullish
                    & (bullish_cross_age <= max_cross_age_cap)
                    & (close > ema_fast)
                    & (adx14 >= ma_adx_min)
                    & (close > open_)
                ).fillna(False)
                base_short_entries = (
                    trend_down
                    & filter_bearish
                    & (bearish_cross_age <= max_cross_age_cap)
                    & (close < ema_fast)
                    & (adx14 >= ma_adx_min)
                    & (close < open_)
                ).fillna(False)

                for max_cross_age_bars in ma_max_cross_age_bars:
                    long_entries = base_long_entries & (bullish_cross_age <= max_cross_age_bars)
                    short_entries = base_short_entries & (bearish_cross_age <= max_cross_age_bars)
                    long_exits = ((close < ema_slow) | (ema_fast < ema_slow)).fillna(False)
                    short_exits = ((close > ema_slow) | (ema_fast > ema_slow)).fillna(False)

                    for cooldown in cooldown_bars:
                        cooled_long_entries = _apply_cooldown(long_entries, cooldown)
                        cooled_short_entries = _apply_cooldown(short_entries, cooldown)
                        for atr_stop_multiplier in atr_stop_multipliers:
                            sl_stop = ((atr14 * atr_stop_multiplier) / close).clip(lower=0.0001)
                            for rr in rrs:
                                tp_stop = sl_stop * rr
                                portfolio = vbt.Portfolio.from_signals(
                                    close,
                                    entries=cooled_long_entries.astype(bool),
                                    exits=long_exits.astype(bool),
                                    short_entries=cooled_short_entries.astype(bool),
                                    short_exits=short_exits.astype(bool),
                                    init_cash=config.init_cash,
                                    fees=config.fees,
                                    slippage=config.slippage,
                                    sl_stop=sl_stop,
                                    tp_stop=tp_stop,
                                    freq=freq,
                                )
                                stats = portfolio.stats()
                                results.append(
                                    {
                                        "parameter_json": {
                                            "ema_fast": int(ema_fast_window),
                                            "ema_slow": int(ema_slow_window),
                                            "filter_timeframe": config.filter_timeframe.upper(),
                                            "ma_adx_min": float(ma_adx_min),
                                            "max_cross_age_bars": int(max_cross_age_bars),
                                            "cooldown_bars": int(cooldown),
                                            "atr_stop_multiplier": float(atr_stop_multiplier),
                                            "rr": float(rr),
                                        },
                                        "total_return_pct": _float_metric(stats, "Total Return [%]"),
                                        "total_trades": _int_metric(stats, "Total Trades"),
                                        "win_rate": _float_metric(stats, "Win Rate [%]"),
                                        "profit_factor": _float_metric(stats, "Profit Factor"),
                                        "max_drawdown_pct": _float_metric(stats, "Max Drawdown [%]"),
                                        "sharpe": _float_metric(stats, "Sharpe Ratio"),
                                        "expectancy": _float_metric(stats, "Expectancy"),
                                        "min_trades_for_rank": config.min_trades_for_rank,
                                    }
                                )

    ranked = sorted(results, key=_rank_key, reverse=True)
    for index, item in enumerate(ranked, start=1):
        item.pop("min_trades_for_rank", None)
        item["rank"] = index

    return QuantResearchResult(
        run={
            "run_id": _now_run_id(config.symbol),
            "strategy": config.strategy,
            "symbol": config.symbol,
            "timeframe": config.timeframe.upper(),
            "filter_timeframe": config.filter_timeframe.upper(),
            "data_from": config.from_date,
            "data_to": config.to_date,
            "init_cash": config.init_cash,
            "fees": config.fees,
            "slippage": config.slippage,
        },
        results=ranked,
    )


def run_breakout_research(
    candles: pd.DataFrame,
    filter_candles: pd.DataFrame | None,
    config: QuantResearchConfig,
) -> QuantResearchResult:
    """Run a Donchian-style breakout baseline with optional higher-timeframe confirmation."""
    if candles.empty:
        raise ValueError("No candle data available for breakout quant research")
    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(candles.columns))
    if missing:
        raise ValueError(f"Missing required candle columns: {', '.join(missing)}")

    vbt = _load_vectorbt()
    df = candles.sort_values("time").reset_index(drop=True).copy()
    df["time"] = pd.to_datetime(df["time"])
    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    rsi14 = _rsi(close, 14)
    atr14 = _atr(df, 14)
    merged_filter = _prepare_filter_frame(filter_candles, df["time"]) if filter_candles is not None else None

    ema_fast_windows = config.ema_fast_windows or [20]
    ema_slow_windows = config.ema_slow_windows or [50]
    breakout_lookbacks = config.breakout_lookbacks or [20, 30, 50]
    breakout_atr_buffers = config.breakout_atr_buffers or [0.0, 0.25, 0.5]
    breakout_rsi_lowers = config.breakout_rsi_lowers or [50.0, 55.0]
    breakout_rsi_uppers = config.breakout_rsi_uppers or [45.0, 50.0]
    atr_stop_multipliers = config.atr_stop_multipliers or [1.5, 2.0]
    rrs = config.rrs or [1.3, 1.5, 2.0]
    cooldown_bars = config.cooldown_bars or [8, 12, 20]
    freq = _timeframe_to_freq(config.timeframe)

    results: List[Dict[str, Any]] = []
    for ema_fast_window in ema_fast_windows:
        ema_fast = close.ewm(span=ema_fast_window, adjust=False).mean()
        for ema_slow_window in ema_slow_windows:
            ema_slow = close.ewm(span=ema_slow_window, adjust=False).mean()
            trend_up = ema_fast > ema_slow
            trend_down = ema_fast < ema_slow

            if merged_filter is not None:
                filter_up = (
                    (merged_filter["filter_close"] > merged_filter["filter_ema20"])
                    & (merged_filter["filter_ema20"] > merged_filter["filter_ema50"])
                )
                filter_down = (
                    (merged_filter["filter_close"] < merged_filter["filter_ema20"])
                    & (merged_filter["filter_ema20"] < merged_filter["filter_ema50"])
                )
            else:
                filter_up = pd.Series(True, index=df.index)
                filter_down = pd.Series(True, index=df.index)

            for breakout_lookback in breakout_lookbacks:
                prev_high = high.shift(1).rolling(breakout_lookback).max()
                prev_low = low.shift(1).rolling(breakout_lookback).min()
                for breakout_atr_buffer in breakout_atr_buffers:
                    breakout_long = close > (prev_high + (atr14 * breakout_atr_buffer))
                    breakout_short = close < (prev_low - (atr14 * breakout_atr_buffer))
                    long_reclaim = close > open_
                    short_reclaim = close < open_
                    long_exits = ((close < ema_slow) | (ema_fast < ema_slow)).fillna(False)
                    short_exits = ((close > ema_slow) | (ema_fast > ema_slow)).fillna(False)

                    for breakout_rsi_lower in breakout_rsi_lowers:
                        for breakout_rsi_upper in breakout_rsi_uppers:
                            base_long_entries = (
                                trend_up
                                & filter_up
                                & breakout_long
                                & long_reclaim
                                & (rsi14 >= breakout_rsi_lower)
                            ).fillna(False)
                            base_short_entries = (
                                trend_down
                                & filter_down
                                & breakout_short
                                & short_reclaim
                                & (rsi14 <= breakout_rsi_upper)
                            ).fillna(False)

                            for cooldown in cooldown_bars:
                                long_entries = _apply_cooldown(base_long_entries, cooldown)
                                short_entries = _apply_cooldown(base_short_entries, cooldown)
                                for atr_stop_multiplier in atr_stop_multipliers:
                                    sl_stop = ((atr14 * atr_stop_multiplier) / close).clip(lower=0.0001)
                                    for rr in rrs:
                                        tp_stop = sl_stop * rr
                                        portfolio = vbt.Portfolio.from_signals(
                                            close,
                                            entries=long_entries.astype(bool),
                                            exits=long_exits.astype(bool),
                                            short_entries=short_entries.astype(bool),
                                            short_exits=short_exits.astype(bool),
                                            init_cash=config.init_cash,
                                            fees=config.fees,
                                            slippage=config.slippage,
                                            sl_stop=sl_stop,
                                            tp_stop=tp_stop,
                                            freq=freq,
                                        )
                                        stats = portfolio.stats()
                                        results.append(
                                            {
                                                "parameter_json": {
                                                    "ema_fast": int(ema_fast_window),
                                                    "ema_slow": int(ema_slow_window),
                                                    "filter_timeframe": config.filter_timeframe.upper() if config.filter_timeframe else None,
                                                    "breakout_lookback": int(breakout_lookback),
                                                    "breakout_atr_buffer": float(breakout_atr_buffer),
                                                    "cooldown_bars": int(cooldown),
                                                    "atr_stop_multiplier": float(atr_stop_multiplier),
                                                    "breakout_rsi_lower": float(breakout_rsi_lower),
                                                    "breakout_rsi_upper": float(breakout_rsi_upper),
                                                    "rr": float(rr),
                                                },
                                                "total_return_pct": _float_metric(stats, "Total Return [%]"),
                                                "total_trades": _int_metric(stats, "Total Trades"),
                                                "win_rate": _float_metric(stats, "Win Rate [%]"),
                                                "profit_factor": _float_metric(stats, "Profit Factor"),
                                                "max_drawdown_pct": _float_metric(stats, "Max Drawdown [%]"),
                                                "sharpe": _float_metric(stats, "Sharpe Ratio"),
                                                "expectancy": _float_metric(stats, "Expectancy"),
                                                "min_trades_for_rank": config.min_trades_for_rank,
                                            }
                                        )

    ranked = sorted(results, key=_rank_key, reverse=True)
    for index, item in enumerate(ranked, start=1):
        item.pop("min_trades_for_rank", None)
        item["rank"] = index

    return QuantResearchResult(
        run={
            "run_id": _now_run_id(config.symbol),
            "strategy": config.strategy,
            "symbol": config.symbol,
            "timeframe": config.timeframe.upper(),
            "filter_timeframe": config.filter_timeframe.upper() if config.filter_timeframe else None,
            "data_from": config.from_date,
            "data_to": config.to_date,
            "init_cash": config.init_cash,
            "fees": config.fees,
            "slippage": config.slippage,
        },
        results=ranked,
    )


def _prepare_filter_frame(filter_candles: pd.DataFrame, base_times: pd.Series) -> pd.DataFrame:
    if filter_candles.empty:
        raise ValueError("No filter timeframe candles available for MTF quant research")
    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(filter_candles.columns))
    if missing:
        raise ValueError(f"Missing required filter candle columns: {', '.join(missing)}")

    prepared = filter_candles.sort_values("time").reset_index(drop=True).copy()
    prepared["time"] = pd.to_datetime(prepared["time"])
    prepared["filter_close"] = prepared["close"].astype(float)
    prepared["filter_ema20"] = prepared["filter_close"].ewm(span=20, adjust=False).mean()
    prepared["filter_ema50"] = prepared["filter_close"].ewm(span=50, adjust=False).mean()
    prepared["filter_rsi14"] = _rsi(prepared["filter_close"], 14)
    prepared["filter_adx14"] = _adx(prepared[["high", "low", "close"]], 14)
    prepared = prepared[["time", "filter_close", "filter_ema20", "filter_ema50", "filter_rsi14", "filter_adx14"]]

    base = pd.DataFrame({"time": pd.to_datetime(base_times)})
    return pd.merge_asof(base.sort_values("time"), prepared, on="time", direction="backward")


def run_bollinger_mtf_research(
    candles: pd.DataFrame,
    filter_candles: pd.DataFrame,
    config: QuantResearchConfig,
) -> QuantResearchResult:
    """Run M15 Bollinger entries filtered by a higher timeframe trend/RSI state."""
    if candles.empty:
        raise ValueError("No candle data available for MTF quant research")
    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(candles.columns))
    if missing:
        raise ValueError(f"Missing required candle columns: {', '.join(missing)}")
    if not config.filter_timeframe:
        raise ValueError("filter_timeframe is required for bollinger_mtf")

    vbt = _load_vectorbt()
    df = candles.sort_values("time").reset_index(drop=True).copy()
    df["time"] = pd.to_datetime(df["time"])
    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    merged_filter = _prepare_filter_frame(filter_candles, df["time"])

    bb_windows = config.bb_windows or [14, 20, 30]
    bb_stds = config.bb_stds or [1.8, 2.0, 2.2]
    rsi_lowers = config.rsi_lowers or [25.0, 30.0, 35.0]
    rsi_uppers = config.rsi_uppers or [65.0, 70.0, 75.0]
    rrs = config.rrs or [1.3, 1.5, 2.0]
    stop_pcts = config.stop_pcts or [0.01]
    filter_rsi_lows = config.filter_rsi_lows or [45.0]
    filter_rsi_highs = config.filter_rsi_highs or [55.0]
    rsi14 = _rsi(close, 14)
    freq = _timeframe_to_freq(config.timeframe)

    results: List[Dict[str, Any]] = []
    for bb_window in bb_windows:
        for bb_std in bb_stds:
            mid, upper, lower = _bollinger_parts(close, bb_window, bb_std)
            lower_band_reclaim = (close > lower) & (close.shift(1) <= lower.shift(1))
            upper_band_reclaim = (close < upper) & (close.shift(1) >= upper.shift(1))
            bullish_reversal = (close > open_) | lower_band_reclaim
            bearish_reversal = (close < open_) | upper_band_reclaim

            for rsi_lower in rsi_lowers:
                for rsi_upper in rsi_uppers:
                    base_long_entries = (close <= lower) & (rsi14 <= rsi_lower) & bullish_reversal
                    base_short_entries = (close >= upper) & (rsi14 >= rsi_upper) & bearish_reversal
                    long_exits = (close >= mid).fillna(False)
                    short_exits = (close <= mid).fillna(False)

                    for filter_rsi_low in filter_rsi_lows:
                        for filter_rsi_high in filter_rsi_highs:
                            strong_downtrend = (
                                (merged_filter["filter_ema20"] < merged_filter["filter_ema50"])
                                & (merged_filter["filter_rsi14"] < filter_rsi_low)
                            )
                            strong_uptrend = (
                                (merged_filter["filter_ema20"] > merged_filter["filter_ema50"])
                                & (merged_filter["filter_rsi14"] > filter_rsi_high)
                            )
                            long_entries = (base_long_entries & ~strong_downtrend).fillna(False)
                            short_entries = (base_short_entries & ~strong_uptrend).fillna(False)

                            for stop_pct in stop_pcts:
                                for rr in rrs:
                                    portfolio = vbt.Portfolio.from_signals(
                                        close,
                                        entries=long_entries.astype(bool),
                                        exits=long_exits.astype(bool),
                                        short_entries=short_entries.astype(bool),
                                        short_exits=short_exits.astype(bool),
                                        init_cash=config.init_cash,
                                        fees=config.fees,
                                        slippage=config.slippage,
                                        sl_stop=stop_pct,
                                        tp_stop=stop_pct * rr,
                                        freq=freq,
                                    )
                                    stats = portfolio.stats()
                                    results.append(
                                        {
                                            "parameter_json": {
                                                "bb_window": int(bb_window),
                                                "bb_std": float(bb_std),
                                                "rsi_lower": float(rsi_lower),
                                                "rsi_upper": float(rsi_upper),
                                                "filter_timeframe": config.filter_timeframe.upper(),
                                                "filter_rsi_low": float(filter_rsi_low),
                                                "filter_rsi_high": float(filter_rsi_high),
                                                "stop_pct": float(stop_pct),
                                                "rr": float(rr),
                                            },
                                            "total_return_pct": _float_metric(stats, "Total Return [%]"),
                                            "total_trades": _int_metric(stats, "Total Trades"),
                                            "win_rate": _float_metric(stats, "Win Rate [%]"),
                                            "profit_factor": _float_metric(stats, "Profit Factor"),
                                            "max_drawdown_pct": _float_metric(stats, "Max Drawdown [%]"),
                                            "sharpe": _float_metric(stats, "Sharpe Ratio"),
                                            "expectancy": _float_metric(stats, "Expectancy"),
                                            "min_trades_for_rank": config.min_trades_for_rank,
                                        }
                                    )

    ranked = sorted(results, key=_rank_key, reverse=True)
    for index, item in enumerate(ranked, start=1):
        item.pop("min_trades_for_rank", None)
        item["rank"] = index

    return QuantResearchResult(
        run={
            "run_id": _now_run_id(config.symbol),
            "strategy": config.strategy,
            "symbol": config.symbol,
            "timeframe": config.timeframe.upper(),
            "filter_timeframe": config.filter_timeframe.upper(),
            "data_from": config.from_date,
            "data_to": config.to_date,
            "init_cash": config.init_cash,
            "fees": config.fees,
            "slippage": config.slippage,
        },
        results=ranked,
    )


def run_macd_research(
    candles: pd.DataFrame,
    config: QuantResearchConfig,
) -> QuantResearchResult:
    """Run a MACD momentum baseline."""
    if candles.empty:
        raise ValueError("No candle data available for macd quant research")
    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(candles.columns))
    if missing:
        raise ValueError(f"Missing required candle columns: {', '.join(missing)}")

    vbt = _load_vectorbt()
    df = candles.sort_values("time").reset_index(drop=True).copy()
    close = df["close"].astype(float)
    atr14 = _atr(df, 14)
    freq = _timeframe_to_freq(config.timeframe)

    macd_fast_windows = config.macd_fast_windows or [12]
    macd_slow_windows = config.macd_slow_windows or [26]
    macd_signal_windows = config.macd_signal_windows or [9]
    ema_trend_windows = config.ema_slow_windows or [0]
    atr_stop_multipliers = config.atr_stop_multipliers or [1.5, 2.0]
    rrs = config.rrs or [1.3, 1.5, 2.0]
    cooldown_bars = config.cooldown_bars or [0]

    results: List[Dict[str, Any]] = []

    for fast_window in macd_fast_windows:
        for slow_window in macd_slow_windows:
            if fast_window >= slow_window:
                continue

            ema_fast = close.ewm(span=fast_window, adjust=False).mean()
            ema_slow = close.ewm(span=slow_window, adjust=False).mean()
            macd_line = ema_fast - ema_slow

            for signal_window in macd_signal_windows:
                signal_line = macd_line.ewm(span=signal_window, adjust=False).mean()
                macd_hist = macd_line - signal_line

                hist_cross_up = (macd_hist > 0) & (macd_hist.shift(1) <= 0)
                hist_cross_down = (macd_hist < 0) & (macd_hist.shift(1) >= 0)

                for trend_window in ema_trend_windows:
                    if trend_window > 0:
                        ema_trend = close.ewm(span=trend_window, adjust=False).mean()
                        trend_up = close > ema_trend
                        trend_down = close < ema_trend
                    else:
                        trend_up = pd.Series(True, index=close.index)
                        trend_down = pd.Series(True, index=close.index)

                    base_long_entries = hist_cross_up & (macd_line < 0) & trend_up
                    base_short_entries = hist_cross_down & (macd_line > 0) & trend_down

                    long_exits = hist_cross_down.fillna(False)
                    short_exits = hist_cross_up.fillna(False)

                    for cooldown in cooldown_bars:
                        long_entries = _apply_cooldown(base_long_entries, cooldown)
                        short_entries = _apply_cooldown(base_short_entries, cooldown)

                        for atr_stop_multiplier in atr_stop_multipliers:
                            sl_stop = ((atr14 * atr_stop_multiplier) / close).clip(lower=0.0001)
                            for rr in rrs:
                                tp_stop = sl_stop * rr
                                portfolio = vbt.Portfolio.from_signals(
                                    close,
                                    entries=long_entries.astype(bool),
                                    exits=long_exits.astype(bool),
                                    short_entries=short_entries.astype(bool),
                                    short_exits=short_exits.astype(bool),
                                    init_cash=config.init_cash,
                                    fees=config.fees,
                                    slippage=config.slippage,
                                    sl_stop=sl_stop,
                                    tp_stop=tp_stop,
                                    freq=freq,
                                )
                                stats = portfolio.stats()
                                results.append(
                                    {
                                        "parameter_json": {
                                            "macd_fast": int(fast_window),
                                            "macd_slow": int(slow_window),
                                            "macd_signal": int(signal_window),
                                            "ema_trend": int(trend_window),
                                            "cooldown_bars": int(cooldown),
                                            "atr_stop_multiplier": float(atr_stop_multiplier),
                                            "rr": float(rr),
                                        },
                                    "total_return_pct": _float_metric(stats, "Total Return [%]"),
                                    "total_trades": _int_metric(stats, "Total Trades"),
                                    "win_rate": _float_metric(stats, "Win Rate [%]"),
                                    "profit_factor": _float_metric(stats, "Profit Factor"),
                                    "max_drawdown_pct": _float_metric(stats, "Max Drawdown [%]"),
                                    "sharpe": _float_metric(stats, "Sharpe Ratio"),
                                    "expectancy": _float_metric(stats, "Expectancy"),
                                    "min_trades_for_rank": config.min_trades_for_rank,
                                }
                            )

    ranked = sorted(results, key=_rank_key, reverse=True)
    for index, item in enumerate(ranked, start=1):
        item.pop("min_trades_for_rank", None)
        item["rank"] = index

    return QuantResearchResult(
        run={
            "run_id": _now_run_id(config.symbol),
            "strategy": config.strategy,
            "symbol": config.symbol,
            "timeframe": config.timeframe.upper(),
            "data_from": config.from_date,
            "data_to": config.to_date,
            "init_cash": config.init_cash,
            "fees": config.fees,
            "slippage": config.slippage,
        },
        results=ranked,
    )
