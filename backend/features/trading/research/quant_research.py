"""
Fast deterministic strategy research helpers backed by vectorbt.

This module is intentionally separate from the agentic backtest runner. It reads
already-stored candles, generates mechanical signals, and lets vectorbt simulate
portfolio results for parameter sweeps.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class QuantResearchConfig:
    symbol: str
    timeframe: str
    from_date: Optional[str]
    to_date: Optional[str]
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
    veb_lookbacks: List[int] | None = None
    veb_atr_expansions: List[float] | None = None
    veb_adx_mins: List[float] | None = None
    veb_sl_atr_buffers: List[float] | None = None
    veb_bandwidth_windows: List[int] | None = None
    veb_bandwidth_quantiles: List[float] | None = None
    veb_bandwidth_expansion_ratios: List[float] | None = None
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
    adx14 = _adx(df, 14)
    merged_filter = _prepare_filter_frame(filter_candles, df["time"])

    ema_fast_windows = config.ema_fast_windows or [20]
    ema_slow_windows = config.ema_slow_windows or [50]
    ma_adx_mins = config.ma_adx_mins or [25.0, 30.0]
    atr_stop_multipliers = config.atr_stop_multipliers or [1.0, 1.5]
    trend_rsi_lowers = config.trend_rsi_lowers or [45.0, 50.0]
    trend_rsi_uppers = config.trend_rsi_uppers or [50.0, 55.0]
    rrs = config.rrs or [1.5, 2.0]
    freq = _timeframe_to_freq(config.timeframe)

    # 캔들 몸통 비율 계산 (분모가 0일 경우 NaN 처리)
    candle_length = high - low
    body_size = abs(close - open_)
    import numpy as np
    body_ratio = body_size / candle_length.replace(0, np.nan)
    body_ratio_ok = body_ratio >= 0.3

    results: List[Dict[str, Any]] = []
    for ema_fast_window in ema_fast_windows:
        ema_fast = close.ewm(span=ema_fast_window, adjust=False).mean()
        for ema_slow_window in ema_slow_windows:
            ema_slow = close.ewm(span=ema_slow_window, adjust=False).mean()
            
            for ma_adx_min in ma_adx_mins:
                trend_up = (ema_fast > ema_slow) & (adx14 >= ma_adx_min)
                trend_down = (ema_fast < ema_slow) & (adx14 >= ma_adx_min)
                filter_up = merged_filter["filter_ema20"] > merged_filter["filter_ema50"]
                filter_down = merged_filter["filter_ema20"] < merged_filter["filter_ema50"]

                # RSI 3캔들 내 눌림목 (Rolling window=3)
                rsi14_min_3 = rsi14.rolling(window=3).min()
                rsi14_max_3 = rsi14.rolling(window=3).max()

                # 반등 조건 (Body Ratio 30% 이상 포함)
                resume_long = (close > open_) & (close > ema_fast) & body_ratio_ok
                resume_short = (close < open_) & (close < ema_fast) & body_ratio_ok

                for trend_rsi_lower in trend_rsi_lowers:
                    for trend_rsi_upper in trend_rsi_uppers:
                        # RSI 눌림목 조건: 최근 3캔들 내에 RSI가 설정된 lower값 미만으로 떨어진 적이 있는지
                        pullback_long = rsi14_min_3 < trend_rsi_lower
                        # 숏의 경우 RSI가 설정된 upper값 초과로 오른 적이 있는지
                        pullback_short = rsi14_max_3 > trend_rsi_upper

                        long_entries = (
                            trend_up
                            & filter_up
                            & pullback_long
                            & resume_long
                            & (rsi14 >= trend_rsi_lower) # 회복 조건 유지
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
                                            "ma_adx_min": float(ma_adx_min),
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
    prepared["filter_adx_slope_positive"] = prepared["filter_adx14"] > prepared["filter_adx14"].shift(1)
    prepared = prepared[
        [
            "time",
            "filter_close",
            "filter_ema20",
            "filter_ema50",
            "filter_rsi14",
            "filter_adx14",
            "filter_adx_slope_positive",
        ]
    ]

    base = pd.DataFrame({"time": pd.to_datetime(base_times)})
    return pd.merge_asof(base.sort_values("time"), prepared, on="time", direction="backward")


def _resolve_veb_parameters(
    config: QuantResearchConfig,
    fixed_parameters: Dict[str, Any] | None = None,
) -> List[Dict[str, float]]:
    if fixed_parameters:
        rr = float(fixed_parameters.get("rr", 2.0))
        return [
            {
                "lookback": float(fixed_parameters.get("lookback", 30)),
                "atr_expansion": float(fixed_parameters.get("atr_expansion", 1.5)),
                "adx_min": float(fixed_parameters.get("adx_min", 20.0)),
                "sl_atr_buffer": float(fixed_parameters.get("sl_atr_buffer", 0.5)),
                "bandwidth_window": float(fixed_parameters.get("bandwidth_window", 0)),
                "bandwidth_quantile": float(fixed_parameters.get("bandwidth_quantile", 0.0)),
                "bandwidth_expansion_ratio": float(fixed_parameters.get("bandwidth_expansion_ratio", 0.0)),
                "rr": max(float(rr), 2.0),
            }
        ]

    lookbacks = config.veb_lookbacks or [30, 45, 60]
    atr_expansions = config.veb_atr_expansions or [1.5, 2.0]
    adx_mins = config.veb_adx_mins or [20.0, 25.0]
    sl_atr_buffers = config.veb_sl_atr_buffers or [0.5]
    bandwidth_windows = config.veb_bandwidth_windows or [0]
    bandwidth_quantiles = config.veb_bandwidth_quantiles or [0.0]
    bandwidth_expansion_ratios = config.veb_bandwidth_expansion_ratios or [0.0]
    rrs = [float(rr) for rr in (config.rrs or [2.0]) if float(rr) >= 2.0] or [2.0]

    return [
        {
            "lookback": float(lookback),
            "atr_expansion": float(atr_expansion),
            "adx_min": float(adx_min),
            "sl_atr_buffer": float(sl_atr_buffer),
            "bandwidth_window": float(bandwidth_window),
            "bandwidth_quantile": float(bandwidth_quantile),
            "bandwidth_expansion_ratio": float(bandwidth_expansion_ratio),
            "rr": float(rr),
        }
        for lookback in lookbacks
        for atr_expansion in atr_expansions
        for adx_min in adx_mins
        for sl_atr_buffer in sl_atr_buffers
        for bandwidth_window in bandwidth_windows
        for bandwidth_quantile in bandwidth_quantiles
        for bandwidth_expansion_ratio in bandwidth_expansion_ratios
        for rr in rrs
    ]


def _veb_find_long_pattern(df: pd.DataFrame, current_idx: int, lookback: int) -> Dict[str, float] | None:
    start_idx = max(0, current_idx - lookback + 1)
    window = df.iloc[start_idx : current_idx + 1]
    if len(window) < lookback:
        return None

    bottom1_local_idx = None
    for local_idx in range(max(0, len(window) - 5)):
        row = window.iloc[local_idx]
        low = row.get("low")
        lower = row.get("bb_lower20")
        if low is None or lower is None or pd.isna(low) or pd.isna(lower):
            continue
        if low <= lower:
            bottom1_local_idx = local_idx
            break

    if bottom1_local_idx is None:
        return None

    bottom2_local_idx = None
    for local_idx in range(len(window) - 2, bottom1_local_idx, -1):
        row = window.iloc[local_idx]
        prev_row = window.iloc[local_idx - 1]
        next_row = window.iloc[local_idx + 1]
        low = row.get("low")
        lower = row.get("bb_lower20")
        if any(
            value is None or pd.isna(value)
            for value in (low, lower, prev_row.get("low"), next_row.get("low"))
        ):
            continue
        if low > lower and low < prev_row["low"] and low < next_row["low"]:
            bottom2_local_idx = local_idx
            break

    if bottom2_local_idx is None:
        return None

    bottom1_low = window.iloc[bottom1_local_idx]["low"]
    bottom2_low = window.iloc[bottom2_local_idx]["low"]
    if bottom2_low <= bottom1_low:
        return None

    neckline_slice = window.iloc[bottom1_local_idx:bottom2_local_idx]
    if neckline_slice.empty:
        return None
    if neckline_slice[["high", "low"]].isna().any().any():
        return None

    return {
        "bottom1_idx": float(start_idx + bottom1_local_idx),
        "bottom2_idx": float(start_idx + bottom2_local_idx),
        "bottom2_low": float(bottom2_low),
        "neckline": float(neckline_slice["high"].max()),
    }


def _veb_find_short_pattern(df: pd.DataFrame, current_idx: int, lookback: int) -> Dict[str, float] | None:
    start_idx = max(0, current_idx - lookback + 1)
    window = df.iloc[start_idx : current_idx + 1]
    if len(window) < lookback:
        return None

    top1_local_idx = None
    for local_idx in range(max(0, len(window) - 5)):
        row = window.iloc[local_idx]
        high = row.get("high")
        upper = row.get("bb_upper20")
        if high is None or upper is None or pd.isna(high) or pd.isna(upper):
            continue
        if high >= upper:
            top1_local_idx = local_idx
            break

    if top1_local_idx is None:
        return None

    top2_local_idx = None
    for local_idx in range(len(window) - 2, top1_local_idx, -1):
        row = window.iloc[local_idx]
        prev_row = window.iloc[local_idx - 1]
        next_row = window.iloc[local_idx + 1]
        high = row.get("high")
        upper = row.get("bb_upper20")
        if any(
            value is None or pd.isna(value)
            for value in (high, upper, prev_row.get("high"), next_row.get("high"))
        ):
            continue
        if high < upper and high > prev_row["high"] and high > next_row["high"]:
            top2_local_idx = local_idx
            break

    if top2_local_idx is None:
        return None

    top1_high = window.iloc[top1_local_idx]["high"]
    top2_high = window.iloc[top2_local_idx]["high"]
    if top2_high >= top1_high:
        return None

    neckline_slice = window.iloc[top1_local_idx:top2_local_idx]
    if neckline_slice.empty:
        return None
    if neckline_slice[["high", "low"]].isna().any().any():
        return None

    return {
        "top1_idx": float(start_idx + top1_local_idx),
        "top2_idx": float(start_idx + top2_local_idx),
        "top2_high": float(top2_high),
        "neckline": float(neckline_slice["low"].min()),
    }


def _build_veb_signals(
    df: pd.DataFrame,
    filter_frame: pd.DataFrame,
    *,
    lookback: int,
    atr_expansion: float,
    adx_min: float,
    sl_atr_buffer: float,
    rr: float,
) -> Dict[str, pd.Series]:
    index = df.index
    long_entries = pd.Series(False, index=index, dtype=bool)
    short_entries = pd.Series(False, index=index, dtype=bool)
    exits = pd.Series(False, index=index, dtype=bool)
    short_exits = pd.Series(False, index=index, dtype=bool)
    long_sl_stop = pd.Series(np.nan, index=index, dtype=float)
    long_tp_stop = pd.Series(np.nan, index=index, dtype=float)
    short_sl_stop = pd.Series(np.nan, index=index, dtype=float)
    short_tp_stop = pd.Series(np.nan, index=index, dtype=float)

    if not df.empty:
        exits.iloc[-1] = True
        short_exits.iloc[-1] = True

    required_fields = ("high", "low", "close", "atr14")

    for current_idx in range(max(lookback - 1, 0), len(df)):
        latest = df.iloc[current_idx]
        filt = filter_frame.iloc[current_idx] if current_idx < len(filter_frame) else None
        if filt is None:
            continue
        if any(latest.get(field) is None or pd.isna(latest.get(field)) for field in required_fields):
            continue
        if latest["high"] - latest["low"] < latest["atr14"] * atr_expansion:
            continue
        if pd.isna(filt.get("filter_adx14")) or float(filt["filter_adx14"]) <= adx_min:
            continue
        if pd.isna(filt.get("filter_adx_slope_positive")) or not bool(filt.get("filter_adx_slope_positive")):
            continue

        prev_close = df.iloc[current_idx - 1]["close"] if current_idx > 0 else None

        if pd.notna(filt.get("filter_ema20")) and pd.notna(filt.get("filter_ema50")):
            if float(filt["filter_ema20"]) >= float(filt["filter_ema50"]):
                long_pattern = _veb_find_long_pattern(df, current_idx, lookback)
                if long_pattern is not None and prev_close is not None and pd.notna(prev_close):
                    if prev_close <= long_pattern["neckline"] and latest["close"] > long_pattern["neckline"]:
                        sl_price = long_pattern["bottom2_low"] - (latest["atr14"] * sl_atr_buffer)
                        if sl_price < latest["close"]:
                            risk_distance = latest["close"] - sl_price
                            stop_fraction = risk_distance / latest["close"]
                            long_entries.iloc[current_idx] = True
                            long_sl_stop.iloc[current_idx] = stop_fraction
                            long_tp_stop.iloc[current_idx] = stop_fraction * rr

            if float(filt["filter_ema20"]) <= float(filt["filter_ema50"]):
                short_pattern = _veb_find_short_pattern(df, current_idx, lookback)
                if short_pattern is not None and prev_close is not None and pd.notna(prev_close):
                    if prev_close >= short_pattern["neckline"] and latest["close"] < short_pattern["neckline"]:
                        sl_price = short_pattern["top2_high"] + (latest["atr14"] * sl_atr_buffer)
                        if sl_price > latest["close"]:
                            risk_distance = sl_price - latest["close"]
                            stop_fraction = risk_distance / latest["close"]
                            short_entries.iloc[current_idx] = True
                            short_sl_stop.iloc[current_idx] = stop_fraction
                            short_tp_stop.iloc[current_idx] = stop_fraction * rr

    return {
        "entries": long_entries,
        "exits": exits,
        "short_entries": short_entries,
        "short_exits": short_exits,
        "long_sl_stop": long_sl_stop,
        "long_tp_stop": long_tp_stop,
        "short_sl_stop": short_sl_stop,
        "short_tp_stop": short_tp_stop,
    }


def _apply_veb_bandwidth_filter(
    signals: Dict[str, pd.Series],
    close: pd.Series,
    upper_band: pd.Series,
    lower_band: pd.Series,
    *,
    bandwidth_window: int,
    bandwidth_quantile: float,
    bandwidth_expansion_ratio: float,
) -> None:
    """Keep VEB entries only when Bollinger bandwidth is in expansion."""
    if bandwidth_window <= 0 or bandwidth_quantile <= 0 or bandwidth_expansion_ratio <= 0:
        return

    bandwidth = ((upper_band - lower_band) / close).replace([np.inf, -np.inf], np.nan)
    threshold = bandwidth.rolling(bandwidth_window).quantile(bandwidth_quantile)
    expansion_ok = (bandwidth >= threshold * bandwidth_expansion_ratio).fillna(False)
    signals["entries"] = signals["entries"] & expansion_ok
    signals["short_entries"] = signals["short_entries"] & expansion_ok


def _run_volatility_expansion_breakout_research(
    candles: pd.DataFrame,
    filter_candles: pd.DataFrame,
    config: QuantResearchConfig,
    *,
    fixed_parameters: Dict[str, Any] | None = None,
    walk_forward_phase: str | None = None,
) -> QuantResearchResult:
    if candles.empty:
        raise ValueError("No candle data available for volatility expansion breakout quant research")
    if filter_candles is None or filter_candles.empty:
        raise ValueError("No filter timeframe candles available for volatility expansion breakout quant research")
    if not config.filter_timeframe:
        raise ValueError("filter_timeframe is required for volatility_expansion_breakout")

    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(candles.columns))
    if missing:
        raise ValueError(f"Missing required candle columns: {', '.join(missing)}")

    vbt = _load_vectorbt()
    df = candles.sort_values("time").reset_index(drop=True).copy()
    df["time"] = pd.to_datetime(df["time"])
    close = df["close"].astype(float)
    df["ema50"] = close.ewm(span=50, adjust=False).mean()
    df["atr14"] = _atr(df, 14)
    df["adx14"] = _adx(df, 14)
    _, upper, lower = _bollinger_parts(close, 20, 2.0)
    df["bb_upper20"] = upper
    df["bb_lower20"] = lower

    prepared_filter = _prepare_filter_frame(filter_candles, df["time"])
    parameter_grid = _resolve_veb_parameters(config, fixed_parameters=fixed_parameters)
    freq = _timeframe_to_freq(config.timeframe)

    results: List[Dict[str, Any]] = []
    for params in parameter_grid:
        signals = _build_veb_signals(
            df,
            prepared_filter,
            lookback=int(params["lookback"]),
            atr_expansion=float(params["atr_expansion"]),
            adx_min=float(params["adx_min"]),
            sl_atr_buffer=float(params["sl_atr_buffer"]),
            rr=float(params["rr"]),
        )
        _apply_veb_bandwidth_filter(
            signals,
            close,
            upper,
            lower,
            bandwidth_window=int(params["bandwidth_window"]),
            bandwidth_quantile=float(params["bandwidth_quantile"]),
            bandwidth_expansion_ratio=float(params["bandwidth_expansion_ratio"]),
        )

        portfolio = vbt.Portfolio.from_signals(
            close,
            entries=signals["entries"].astype(bool),
            exits=signals["exits"].astype(bool),
            short_entries=signals["short_entries"].astype(bool),
            short_exits=signals["short_exits"].astype(bool),
            init_cash=config.init_cash,
            fees=config.fees,
            slippage=config.slippage,
            sl_stop=signals["long_sl_stop"].combine_first(signals["short_sl_stop"]),
            tp_stop=signals["long_tp_stop"].combine_first(signals["short_tp_stop"]),
            freq=freq,
        )
        stats = portfolio.stats()
        parameter_json = {
            "strategy_variant": "w_m_volatility_expansion",
            "lookback": int(params["lookback"]),
            "atr_expansion": float(params["atr_expansion"]),
            "adx_min": float(params["adx_min"]),
            "sl_atr_buffer": float(params["sl_atr_buffer"]),
            "bandwidth_window": int(params["bandwidth_window"]),
            "bandwidth_quantile": float(params["bandwidth_quantile"]),
            "bandwidth_expansion_ratio": float(params["bandwidth_expansion_ratio"]),
            "rr": float(params["rr"]),
            "filter_timeframe": config.filter_timeframe.upper(),
        }
        if walk_forward_phase:
            parameter_json["walk_forward_phase"] = walk_forward_phase
        results.append(
            {
                "parameter_json": parameter_json,
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


def run_volatility_expansion_breakout_research(
    candles: pd.DataFrame,
    filter_candles: pd.DataFrame,
    config: QuantResearchConfig,
) -> QuantResearchResult:
    """Run the VEB parameter sweep with vectorbt portfolios."""
    return _run_volatility_expansion_breakout_research(candles, filter_candles, config)


def run_volatility_expansion_breakout_walk_forward(
    is_candles: pd.DataFrame,
    is_filter_candles: pd.DataFrame,
    oos_candles: pd.DataFrame,
    oos_filter_candles: pd.DataFrame,
    config: QuantResearchConfig,
    *,
    is_from: str,
    is_to: str,
    oos_from: str,
    oos_to: str,
) -> Dict[str, Any]:
    """Run an IS sweep, select rank-1 parameters, and replay them on OOS data."""
    is_config = replace(config, from_date=is_from, to_date=is_to, strategy="volatility_expansion_breakout")
    oos_config = replace(config, from_date=oos_from, to_date=oos_to, strategy="volatility_expansion_breakout")

    is_result = _run_volatility_expansion_breakout_research(
        is_candles,
        is_filter_candles,
        is_config,
        walk_forward_phase="IS",
    )
    if not is_result.results:
        raise ValueError("No IS results produced for volatility expansion breakout walk-forward")

    selected_parameters = dict(is_result.results[0]["parameter_json"])
    selected_parameters.pop("walk_forward_phase", None)
    oos_result = _run_volatility_expansion_breakout_research(
        oos_candles,
        oos_filter_candles,
        oos_config,
        fixed_parameters=selected_parameters,
        walk_forward_phase="OOS",
    )
    return {
        "is_result": is_result,
        "oos_result": oos_result,
        "selected_parameters": selected_parameters,
    }


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
