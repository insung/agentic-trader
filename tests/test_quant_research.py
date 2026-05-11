import argparse
import sqlite3
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.features.trading import backtest_store
import backend.features.trading.research.quant_research as quant_research
import backend.scripts.run_quant_research as run_quant_research
from backend.features.trading.research.quant_research import (
    QuantResearchConfig,
    QuantResearchResult,
    run_buy_hold_research,
    run_breakout_research,
    run_bollinger_research,
    run_bollinger_mtf_research,
    run_ma_crossover_research,
    run_macd_research,
    run_random_research,
    run_no_trade_research,
    run_volatility_expansion_breakout_research,
    run_volatility_expansion_breakout_walk_forward,
    run_trend_pullback_reclaim_research,
    run_trend_pullback_research,
)


class _FakePortfolio:
    call_count = 0
    last_kwargs = {}

    @classmethod
    def from_signals(cls, *args, **kwargs):
        cls.call_count += 1
        cls.last_kwargs = kwargs
        return cls()

    def stats(self):
        return pd.Series(
            {
                "Total Return [%]": 12.5,
                "Total Trades": 24,
                "Win Rate [%]": 58.0,
                "Profit Factor": 1.8,
                "Max Drawdown [%]": 4.2,
                "Sharpe Ratio": 1.1,
                "Expectancy": 3.4,
            }
        )


def _sample_candles(periods=80, freq="15min"):
    times = pd.date_range(start="2025-01-01", periods=periods, freq=freq)
    close = pd.Series(
        [100 + ((i % 12) - 6) * 0.7 + (i * 0.03) for i in range(periods)]
    )
    return pd.DataFrame(
        {
            "time": times,
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "tick_volume": [100] * periods,
            "spread": [1] * periods,
            "real_volume": [0] * periods,
        }
    )


def test_run_bollinger_research_uses_vectorbt_and_ranks_results(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "vectorbt", SimpleNamespace(Portfolio=_FakePortfolio))
    _FakePortfolio.call_count = 0
    _FakePortfolio.last_kwargs = {}

    result = run_bollinger_research(
        _sample_candles(),
        QuantResearchConfig(
            symbol="BTCUSD",
            timeframe="M15",
            from_date="2025-01-01",
            to_date="2025-01-01",
            bb_windows=[20],
            bb_stds=[2.0],
            rsi_lowers=[30],
            rsi_uppers=[70],
            rrs=[1.5],
            stop_pcts=[0.01],
        ),
    )

    assert _FakePortfolio.call_count == 1
    assert result.run["strategy"] == "bollinger"
    assert len(result.results) == 1
    assert _FakePortfolio.last_kwargs["freq"] == "15min"
    assert result.results[0]["rank"] == 1
    assert result.results[0]["total_trades"] == 24
    assert result.results[0]["parameter_json"]["bb_window"] == 20


def test_run_buy_hold_research_uses_vectorbt_and_one_trade(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "vectorbt", SimpleNamespace(Portfolio=_FakePortfolio))
    _FakePortfolio.call_count = 0
    _FakePortfolio.last_kwargs = {}

    result = run_buy_hold_research(
        _sample_candles(),
        QuantResearchConfig(
            symbol="BTCUSD",
            timeframe="M15",
            from_date="2025-01-01",
            to_date="2025-01-01",
        ),
    )

    assert _FakePortfolio.call_count == 1
    assert result.run["strategy"] == "buy_hold"
    assert len(result.results) == 1
    assert result.results[0]["rank"] == 1
    assert result.results[0]["total_trades"] == 24
    assert result.results[0]["parameter_json"]["benchmark"] == "buy_hold"


def test_run_no_trade_research_uses_vectorbt_and_zero_trades(tmp_path, monkeypatch):
    class _FakeNoTradePortfolio(_FakePortfolio):
        def stats(self):
            return pd.Series(
                {
                    "Total Return [%]": 0.0,
                    "Total Trades": 0,
                    "Win Rate [%]": 0.0,
                    "Profit Factor": float("nan"),
                    "Max Drawdown [%]": 0.0,
                    "Sharpe Ratio": 0.0,
                    "Expectancy": 0.0,
                }
            )

    monkeypatch.setitem(sys.modules, "vectorbt", SimpleNamespace(Portfolio=_FakeNoTradePortfolio))
    _FakeNoTradePortfolio.call_count = 0
    _FakeNoTradePortfolio.last_kwargs = {}

    result = run_no_trade_research(
        _sample_candles(),
        QuantResearchConfig(
            symbol="BTCUSD",
            timeframe="M15",
            from_date="2025-01-01",
            to_date="2025-01-01",
        ),
    )

    assert _FakeNoTradePortfolio.call_count == 1
    assert result.run["strategy"] == "no_trade"
    assert len(result.results) == 1
    assert result.results[0]["rank"] == 1
    assert result.results[0]["total_trades"] == 0
    assert result.results[0]["parameter_json"]["benchmark"] == "no_trade"


def test_run_random_research_is_deterministic_with_seed(tmp_path, monkeypatch):
    class _CapturePortfolio(_FakePortfolio):
        captured_kwargs = []

        @classmethod
        def from_signals(cls, *args, **kwargs):
            cls.captured_kwargs.append(
                {
                    key: value.copy() if hasattr(value, "copy") else value
                    for key, value in kwargs.items()
                }
            )
            return super().from_signals(*args, **kwargs)

    monkeypatch.setitem(sys.modules, "vectorbt", SimpleNamespace(Portfolio=_CapturePortfolio))
    _CapturePortfolio.call_count = 0
    _CapturePortfolio.last_kwargs = {}
    _CapturePortfolio.captured_kwargs = []

    config = QuantResearchConfig(
        symbol="BTCUSD",
        timeframe="M15",
        from_date="2025-01-01",
        to_date="2025-01-01",
        strategy="random",
        random_seed=7,
        random_entry_prob=0.5,
        random_long_bias=0.6,
        random_min_hold_bars=1,
        random_max_hold_bars=3,
    )

    first = run_random_research(_sample_candles(), config)
    second = run_random_research(_sample_candles(), config)

    assert _CapturePortfolio.call_count == 2
    assert first.run["strategy"] == "random"
    assert first.results[0]["parameter_json"]["seed"] == 7
    assert first.results[0]["parameter_json"]["benchmark"] == "random"
    assert first.results[0]["rank"] == 1
    assert _CapturePortfolio.captured_kwargs[0]["entries"].equals(_CapturePortfolio.captured_kwargs[1]["entries"])
    assert _CapturePortfolio.captured_kwargs[0]["exits"].equals(_CapturePortfolio.captured_kwargs[1]["exits"])
    assert _CapturePortfolio.captured_kwargs[0]["short_entries"].equals(_CapturePortfolio.captured_kwargs[1]["short_entries"])
    assert _CapturePortfolio.captured_kwargs[0]["short_exits"].equals(_CapturePortfolio.captured_kwargs[1]["short_exits"])
    assert first.results[0]["total_trades"] == second.results[0]["total_trades"]


def test_run_bollinger_mtf_research_applies_filter_timeframe(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "vectorbt", SimpleNamespace(Portfolio=_FakePortfolio))
    _FakePortfolio.call_count = 0
    _FakePortfolio.last_kwargs = {}

    result = run_bollinger_mtf_research(
        _sample_candles(),
        _sample_candles(periods=40),
        QuantResearchConfig(
            symbol="BTCUSD",
            timeframe="M15",
            filter_timeframe="M30",
            from_date="2025-01-01",
            to_date="2025-01-01",
            strategy="bollinger_mtf",
            bb_windows=[20],
            bb_stds=[2.0],
            rsi_lowers=[30],
            rsi_uppers=[70],
            rrs=[1.5],
            stop_pcts=[0.01],
            filter_rsi_lows=[45],
            filter_rsi_highs=[55],
        ),
    )

    assert _FakePortfolio.call_count == 1
    assert result.run["strategy"] == "bollinger_mtf"
    assert result.run["filter_timeframe"] == "M30"
    assert _FakePortfolio.last_kwargs["entries"].dtype == bool
    assert _FakePortfolio.last_kwargs["short_entries"].dtype == bool
    assert result.results[0]["parameter_json"]["filter_timeframe"] == "M30"
    assert result.results[0]["parameter_json"]["filter_rsi_low"] == 45.0


def test_run_trend_pullback_research_uses_filter_timeframe_and_atr_stops(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "vectorbt", SimpleNamespace(Portfolio=_FakePortfolio))
    _FakePortfolio.call_count = 0
    _FakePortfolio.last_kwargs = {}

    result = run_trend_pullback_research(
        _sample_candles(),
        _sample_candles(periods=40),
        QuantResearchConfig(
            symbol="BTCUSD",
            timeframe="M15",
            filter_timeframe="M30",
            from_date="2025-01-01",
            to_date="2025-01-01",
            strategy="trend_pullback",
            ema_fast_windows=[20],
            ema_slow_windows=[50],
            ma_adx_mins=[30],
            atr_stop_multipliers=[1.0],
            rrs=[1.5],
            trend_rsi_lowers=[45],
            trend_rsi_uppers=[55],
        ),
    )

    assert _FakePortfolio.call_count >= 1
    assert result.run["strategy"] == "trend_pullback"
    assert result.run["filter_timeframe"] == "M30"
    assert _FakePortfolio.last_kwargs["sl_stop"].notna().any()
    assert _FakePortfolio.last_kwargs["tp_stop"].notna().any()
    assert result.results[0]["parameter_json"]["ma_adx_min"] == 30.0
    assert result.results[0]["parameter_json"]["atr_stop_multiplier"] == 1.0


def test_run_trend_pullback_reclaim_research_uses_reclaim_and_cooldown(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "vectorbt", SimpleNamespace(Portfolio=_FakePortfolio))
    _FakePortfolio.call_count = 0
    _FakePortfolio.last_kwargs = {}

    result = run_trend_pullback_reclaim_research(
        _sample_candles(),
        _sample_candles(periods=40),
        QuantResearchConfig(
            symbol="BTCUSD",
            timeframe="M15",
            filter_timeframe="M30",
            from_date="2025-01-01",
            to_date="2025-01-01",
            strategy="trend_pullback_reclaim",
            ema_fast_windows=[20],
            ema_slow_windows=[50],
            reclaim_lookbacks=[5],
            cooldown_bars=[8],
            atr_stop_multipliers=[2.0],
            rrs=[2.0],
            trend_rsi_lowers=[50],
            trend_rsi_uppers=[50],
        ),
    )

    assert _FakePortfolio.call_count == 1
    assert result.run["strategy"] == "trend_pullback_reclaim"
    assert result.run["filter_timeframe"] == "M30"
    assert _FakePortfolio.last_kwargs["entries"].dtype == bool
    assert _FakePortfolio.last_kwargs["short_entries"].dtype == bool
    assert _FakePortfolio.last_kwargs["sl_stop"].notna().any()
    assert result.results[0]["parameter_json"]["reclaim_lookback"] == 5
    assert result.results[0]["parameter_json"]["cooldown_bars"] == 8
    assert result.results[0]["parameter_json"]["atr_stop_multiplier"] == 2.0


def test_run_ma_crossover_research_uses_filter_timeframe_and_adx(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "vectorbt", SimpleNamespace(Portfolio=_FakePortfolio))
    _FakePortfolio.call_count = 0
    _FakePortfolio.last_kwargs = {}

    result = run_ma_crossover_research(
        _sample_candles(),
        _sample_candles(periods=40),
        QuantResearchConfig(
            symbol="BTCUSD",
            timeframe="M15",
            filter_timeframe="M30",
            from_date="2025-01-01",
            to_date="2025-01-01",
            strategy="ma_crossover",
            ema_fast_windows=[20],
            ema_slow_windows=[50],
            ma_adx_mins=[25],
            ma_max_cross_age_bars=[6],
            cooldown_bars=[8],
            atr_stop_multipliers=[1.0],
            rrs=[2.0],
        ),
    )

    assert _FakePortfolio.call_count == 1
    assert result.run["strategy"] == "ma_crossover"
    assert result.run["filter_timeframe"] == "M30"
    assert _FakePortfolio.last_kwargs["entries"].dtype == bool
    assert _FakePortfolio.last_kwargs["short_entries"].dtype == bool
    assert _FakePortfolio.last_kwargs["sl_stop"].notna().any()
    assert result.results[0]["parameter_json"]["ma_adx_min"] == 25.0
    assert result.results[0]["parameter_json"]["max_cross_age_bars"] == 6


def test_run_breakout_research_supports_optional_filter_timeframe(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "vectorbt", SimpleNamespace(Portfolio=_FakePortfolio))
    _FakePortfolio.call_count = 0
    _FakePortfolio.last_kwargs = {}

    result = run_breakout_research(
        _sample_candles(),
        _sample_candles(periods=40),
        QuantResearchConfig(
            symbol="BTCUSD",
            timeframe="M15",
            filter_timeframe="H1",
            from_date="2025-01-01",
            to_date="2025-01-01",
            strategy="breakout",
            ema_fast_windows=[20],
            ema_slow_windows=[50],
            breakout_lookbacks=[20],
            breakout_atr_buffers=[0.0],
            breakout_rsi_lowers=[50],
            breakout_rsi_uppers=[50],
            cooldown_bars=[8],
            atr_stop_multipliers=[2.0],
            rrs=[2.0],
        ),
    )

    assert _FakePortfolio.call_count == 1
    assert result.run["strategy"] == "breakout"
    assert result.run["filter_timeframe"] == "H1"
    assert _FakePortfolio.last_kwargs["entries"].dtype == bool
    assert _FakePortfolio.last_kwargs["short_entries"].dtype == bool
    assert result.results[0]["parameter_json"]["breakout_lookback"] == 20
    assert result.results[0]["parameter_json"]["breakout_atr_buffer"] == 0.0
    assert result.results[0]["parameter_json"]["cooldown_bars"] == 8


def test_run_volatility_expansion_breakout_research_uses_vectorbt_and_parameters(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "vectorbt", SimpleNamespace(Portfolio=_FakePortfolio))
    _FakePortfolio.call_count = 0
    _FakePortfolio.last_kwargs = {}

    result = run_volatility_expansion_breakout_research(
        _sample_candles(periods=90, freq="5min"),
        _sample_candles(periods=40, freq="15min"),
        QuantResearchConfig(
            symbol="BTCUSD",
            timeframe="M5",
            filter_timeframe="M15",
            from_date="2025-01-01",
            to_date="2025-01-31",
            strategy="volatility_expansion_breakout",
            rrs=[1.5, 2.0],
            veb_lookbacks=[30],
            veb_atr_expansions=[1.5],
            veb_adx_mins=[20.0],
            veb_sl_atr_buffers=[0.5],
            veb_bandwidth_windows=[144],
            veb_bandwidth_quantiles=[0.6],
            veb_bandwidth_expansion_ratios=[1.1],
        ),
    )

    assert _FakePortfolio.call_count == 1
    assert result.run["strategy"] == "volatility_expansion_breakout"
    assert result.run["filter_timeframe"] == "M15"
    assert result.results[0]["parameter_json"]["strategy_variant"] == "w_m_volatility_expansion"
    assert result.results[0]["parameter_json"]["lookback"] == 30
    assert result.results[0]["parameter_json"]["atr_expansion"] == 1.5
    assert result.results[0]["parameter_json"]["adx_min"] == 20.0
    assert result.results[0]["parameter_json"]["sl_atr_buffer"] == 0.5
    assert result.results[0]["parameter_json"]["bandwidth_window"] == 144
    assert result.results[0]["parameter_json"]["bandwidth_quantile"] == 0.6
    assert result.results[0]["parameter_json"]["bandwidth_expansion_ratio"] == 1.1
    assert result.results[0]["parameter_json"]["rr"] == 2.0
    assert result.results[0]["parameter_json"]["filter_timeframe"] == "M15"
    assert _FakePortfolio.last_kwargs["entries"].dtype == bool
    assert _FakePortfolio.last_kwargs["short_entries"].dtype == bool


def test_run_volatility_expansion_walk_forward_uses_is_rank1_params_for_oos(monkeypatch):
    is_result = QuantResearchResult(
        run={
            "run_id": "QR-IS",
            "strategy": "volatility_expansion_breakout",
            "symbol": "BTCUSD",
            "timeframe": "M5",
            "filter_timeframe": "M15",
            "data_from": "2025-01-01",
            "data_to": "2025-06-30",
            "init_cash": 10000.0,
            "fees": 0.0,
            "slippage": 0.0,
        },
        results=[
            {
                "parameter_json": {
                    "strategy_variant": "w_m_volatility_expansion",
                    "lookback": 45,
                    "atr_expansion": 1.5,
                    "adx_min": 20.0,
                    "sl_atr_buffer": 0.5,
                    "rr": 2.0,
                    "filter_timeframe": "M15",
                    "walk_forward_phase": "IS",
                },
                "total_return_pct": 11.0,
                "total_trades": 21,
                "win_rate": 55.0,
                "profit_factor": 1.9,
                "max_drawdown_pct": 5.0,
                "sharpe": 1.0,
                "expectancy": 2.0,
                "rank": 1,
            },
            {
                "parameter_json": {
                    "strategy_variant": "w_m_volatility_expansion",
                    "lookback": 30,
                    "atr_expansion": 1.5,
                    "adx_min": 20.0,
                    "sl_atr_buffer": 0.5,
                    "rr": 2.0,
                    "filter_timeframe": "M15",
                    "walk_forward_phase": "IS",
                },
                "total_return_pct": 8.0,
                "total_trades": 18,
                "win_rate": 52.0,
                "profit_factor": 1.6,
                "max_drawdown_pct": 4.0,
                "sharpe": 0.9,
                "expectancy": 1.5,
                "rank": 2,
            },
        ],
    )
    oos_result = QuantResearchResult(
        run={
            "run_id": "QR-OOS",
            "strategy": "volatility_expansion_breakout",
            "symbol": "BTCUSD",
            "timeframe": "M5",
            "filter_timeframe": "M15",
            "data_from": "2025-07-01",
            "data_to": "2025-12-31",
            "init_cash": 10000.0,
            "fees": 0.0,
            "slippage": 0.0,
        },
        results=[
            {
                "parameter_json": {
                    "strategy_variant": "w_m_volatility_expansion",
                    "lookback": 45,
                    "atr_expansion": 1.5,
                    "adx_min": 20.0,
                    "sl_atr_buffer": 0.5,
                    "rr": 2.0,
                    "filter_timeframe": "M15",
                    "walk_forward_phase": "OOS",
                },
                "total_return_pct": 7.0,
                "total_trades": 14,
                "win_rate": 50.0,
                "profit_factor": 1.4,
                "max_drawdown_pct": 6.0,
                "sharpe": 0.8,
                "expectancy": 1.1,
                "rank": 1,
            }
        ],
    )

    calls = []

    def fake_runner(candles, filter_candles, config, fixed_parameters=None, walk_forward_phase=None):
        calls.append(
            {
                "from_date": config.from_date,
                "to_date": config.to_date,
                "fixed_parameters": fixed_parameters,
                "walk_forward_phase": walk_forward_phase,
            }
        )
        if fixed_parameters is None:
            return is_result
        assert fixed_parameters["lookback"] == 45
        assert fixed_parameters["rr"] == 2.0
        return oos_result

    monkeypatch.setattr(quant_research, "_run_volatility_expansion_breakout_research", fake_runner)

    result = run_volatility_expansion_breakout_walk_forward(
        _sample_candles(periods=90, freq="5min"),
        _sample_candles(periods=40, freq="15min"),
        _sample_candles(periods=90, freq="5min"),
        _sample_candles(periods=40, freq="15min"),
        QuantResearchConfig(
            symbol="BTCUSD",
            timeframe="M5",
            filter_timeframe="M15",
            from_date="2025-01-01",
            to_date="2025-12-31",
            strategy="volatility_expansion_breakout",
        ),
        is_from="2025-01-01",
        is_to="2025-06-30",
        oos_from="2025-07-01",
        oos_to="2025-12-31",
    )

    assert calls[0]["walk_forward_phase"] == "IS"
    assert calls[1]["walk_forward_phase"] == "OOS"
    assert calls[1]["fixed_parameters"]["lookback"] == 45
    assert result["is_result"].run["run_id"] == "QR-IS"
    assert result["oos_result"].run["run_id"] == "QR-OOS"
    assert result["selected_parameters"]["lookback"] == 45


def test_run_macd_research_uses_macd_parameters(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "vectorbt", SimpleNamespace(Portfolio=_FakePortfolio))
    _FakePortfolio.call_count = 0
    _FakePortfolio.last_kwargs = {}

    result = run_macd_research(
        _sample_candles(),
        QuantResearchConfig(
            symbol="BTCUSD",
            timeframe="M15",
            from_date="2025-01-01",
            to_date="2025-01-01",
            strategy="macd",
            macd_fast_windows=[12],
            macd_slow_windows=[26],
            macd_signal_windows=[9],
            cooldown_bars=[8],
            atr_stop_multipliers=[1.5],
            rrs=[1.3],
        ),
    )

    assert _FakePortfolio.call_count == 1
    assert result.run["strategy"] == "macd"
    assert result.run["timeframe"] == "M15"
    assert _FakePortfolio.last_kwargs["freq"] == "15min"
    assert _FakePortfolio.last_kwargs["entries"].dtype == bool
    assert _FakePortfolio.last_kwargs["short_entries"].dtype == bool
    assert result.results[0]["parameter_json"]["macd_fast"] == 12
    assert result.results[0]["parameter_json"]["macd_slow"] == 26
    assert result.results[0]["parameter_json"]["macd_signal"] == 9


def test_persist_quant_research_result_records_run_and_ranked_results(tmp_path):
    db_path = tmp_path / "market_data.sqlite"

    run_id = backtest_store.persist_quant_research_result(
        str(db_path),
        QuantResearchResult(
            run={
                "run_id": "QR-TEST",
                "strategy": "bollinger",
                "symbol": "BTCUSD",
                "timeframe": "M15",
                "data_from": "2025-01-01",
                "data_to": "2025-01-31",
                "init_cash": 10000.0,
                "fees": 0.0005,
                "slippage": 0.0002,
            },
            results=[
                {
                    "parameter_json": {"bb_window": 20, "rr": 1.5},
                    "total_return_pct": 12.5,
                    "total_trades": 24,
                    "win_rate": 58.0,
                    "profit_factor": 1.8,
                    "max_drawdown_pct": 4.2,
                    "sharpe": 1.1,
                    "expectancy": 3.4,
                    "rank": 1,
                }
            ],
        ),
    )

    assert run_id == "QR-TEST"
    with sqlite3.connect(db_path) as conn:
        run = conn.execute(
            "SELECT strategy, symbol, timeframe FROM quant_runs WHERE run_id = ?",
            ("QR-TEST",),
        ).fetchone()
        row = conn.execute(
            "SELECT total_trades, rank, parameter_json FROM quant_results WHERE run_id = ?",
            ("QR-TEST",),
        ).fetchone()

    assert run == ("bollinger", "BTCUSD", "M15")
    assert row[0] == 24
    assert row[1] == 1
    assert '"bb_window": 20' in row[2]


def test_persist_quant_research_result_records_wfo_metadata(tmp_path):
    db_path = tmp_path / "market_data.sqlite"

    run_id = backtest_store.persist_quant_research_result(
        str(db_path),
        QuantResearchResult(
            run={
                "run_id": "QR-WFO",
                "strategy": "volatility_expansion_breakout",
                "symbol": "BTCUSD",
                "timeframe": "M5",
                "filter_timeframe": "M15",
                "data_from": "2025-07-01",
                "data_to": "2025-12-31",
                "init_cash": 10000.0,
                "fees": 0.0,
                "slippage": 0.0,
            },
            results=[
                {
                    "parameter_json": {
                        "strategy_variant": "w_m_volatility_expansion",
                        "lookback": 45,
                        "atr_expansion": 1.5,
                        "adx_min": 20.0,
                        "sl_atr_buffer": 0.5,
                        "rr": 2.0,
                        "filter_timeframe": "M15",
                        "walk_forward_phase": "OOS",
                    },
                    "total_return_pct": 9.0,
                    "total_trades": 16,
                    "win_rate": 54.0,
                    "profit_factor": 1.7,
                    "max_drawdown_pct": 4.8,
                    "sharpe": 1.0,
                    "expectancy": 2.1,
                    "rank": 1,
                }
            ],
        ),
    )

    assert run_id == "QR-WFO"
    with sqlite3.connect(db_path) as conn:
        run = conn.execute(
            "SELECT strategy, symbol, timeframe FROM quant_runs WHERE run_id = ?",
            ("QR-WFO",),
        ).fetchone()
        row = conn.execute(
            "SELECT parameter_json FROM quant_results WHERE run_id = ?",
            ("QR-WFO",),
        ).fetchone()

    assert run == ("volatility_expansion_breakout", "BTCUSD", "M5")
    assert '"strategy_variant": "w_m_volatility_expansion"' in row[0]
    assert '"walk_forward_phase": "OOS"' in row[0]


def test_walk_forward_cli_loads_only_is_and_oos_windows(monkeypatch):
    load_calls = []

    def fake_load_candles(db_path, symbol, timeframe, from_date, to_date):
        load_calls.append((symbol, timeframe, from_date, to_date))
        return _sample_candles(periods=40, freq="5min" if timeframe == "M5" else "15min")

    monkeypatch.setattr(run_quant_research, "load_candles", fake_load_candles)
    monkeypatch.setattr(
        run_quant_research,
        "run_volatility_expansion_breakout_walk_forward",
        lambda *args, **kwargs: {
            "is_result": QuantResearchResult(
                run={
                    "run_id": "QR-IS",
                    "strategy": "volatility_expansion_breakout",
                    "symbol": "BTCUSD",
                    "timeframe": "M5",
                    "filter_timeframe": "M15",
                    "data_from": "2025-01-01",
                    "data_to": "2025-06-30",
                    "init_cash": 10000.0,
                    "fees": 0.0,
                    "slippage": 0.0,
                },
                results=[{"parameter_json": {}, "total_return_pct": 1.0, "total_trades": 1, "win_rate": 1.0, "profit_factor": 1.0, "max_drawdown_pct": 1.0, "sharpe": 1.0, "expectancy": 1.0, "rank": 1}],
            ),
            "oos_result": QuantResearchResult(
                run={
                    "run_id": "QR-OOS",
                    "strategy": "volatility_expansion_breakout",
                    "symbol": "BTCUSD",
                    "timeframe": "M5",
                    "filter_timeframe": "M15",
                    "data_from": "2025-07-01",
                    "data_to": "2025-12-31",
                    "init_cash": 10000.0,
                    "fees": 0.0,
                    "slippage": 0.0,
                },
                results=[{"parameter_json": {}, "total_return_pct": 2.0, "total_trades": 2, "win_rate": 1.0, "profit_factor": 1.0, "max_drawdown_pct": 1.0, "sharpe": 1.0, "expectancy": 1.0, "rank": 1}],
            ),
            "selected_parameters": {"lookback": 45},
        },
    )
    persisted = []
    monkeypatch.setattr(
        run_quant_research,
        "persist_quant_research_result",
        lambda db_path, result: persisted.append(result.run["run_id"]) or result.run["run_id"],
    )

    args = argparse.Namespace(
        data_db="/tmp/test.sqlite",
        symbol="BTCUSD",
        timeframe="M5",
        filter_timeframe="M15",
        from_date="2025-01-01",
        to_date="2025-12-31",
        strategy="volatility_expansion_breakout",
        init_cash=10000.0,
        fees=0.0,
        slippage=0.0,
        bb_windows="14,20,30",
        bb_stds="1.8,2.0,2.2",
        rsi_lowers="25,30,35",
        rsi_uppers="65,70,75",
        filter_rsi_lows="45",
        filter_rsi_highs="55",
        rrs="1.3,1.5,2.0",
        stop_pcts="0.01",
        ema_fast_windows="20",
        ema_slow_windows="50",
        pullback_atrs="0.25,0.5,0.75",
        atr_stop_multipliers="1.0,1.5",
        trend_rsi_lowers="45",
        trend_rsi_uppers="55",
        reclaim_lookbacks="3,5,8",
        cooldown_bars="8,12,20",
        ma_adx_mins="25,30",
        ma_max_cross_age_bars="3,6",
        breakout_lookbacks="20,30,50",
        breakout_atr_buffers="0.0,0.25,0.5",
        breakout_rsi_lowers="50,55",
        breakout_rsi_uppers="45,50",
        veb_lookbacks="30,45,60",
        veb_atr_expansions="1.5,2.0",
        veb_adx_mins="20,25",
        veb_sl_atr_buffers="0.5",
        macd_fast_windows="12",
        macd_slow_windows="26",
        macd_signal_windows="9",
        walk_forward=True,
        is_from="2025-01-01",
        is_to="2025-06-30",
        oos_from="2025-07-01",
        oos_to="2025-12-31",
        random_seed=42,
        random_entry_prob=0.01,
        random_long_bias=0.5,
        random_min_hold_bars=3,
        random_max_hold_bars=12,
        top=10,
    )
    config = run_quant_research._build_config(args)

    run_quant_research._run_volatility_expansion_walk_forward_from_args(args, config)

    assert load_calls == [
        ("BTCUSD", "M5", "2025-01-01", "2025-06-30"),
        ("BTCUSD", "M15", "2025-01-01", "2025-06-30"),
        ("BTCUSD", "M5", "2025-07-01", "2025-12-31"),
        ("BTCUSD", "M15", "2025-07-01", "2025-12-31"),
    ]
    assert persisted == ["QR-IS", "QR-OOS"]


def test_parse_args_allows_walk_forward_without_from_to(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_quant_research",
            "--symbol",
            "BTCUSD",
            "--timeframe",
            "M5",
            "--filter-timeframe",
            "M15",
            "--strategy",
            "volatility_expansion_breakout",
            "--walk-forward",
            "--is-from",
            "2025-01-01",
            "--is-to",
            "2025-06-30",
            "--oos-from",
            "2025-07-01",
            "--oos-to",
            "2025-12-31",
        ],
    )

    args = run_quant_research.parse_args()

    assert args.from_date is None
    assert args.to_date is None
    assert args.walk_forward is True
    assert args.is_from == "2025-01-01"
    assert args.oos_to == "2025-12-31"


def test_standard_research_requires_from_and_to(monkeypatch):
    args = argparse.Namespace(
        data_db="/tmp/test.sqlite",
        symbol="BTCUSD",
        timeframe="M5",
        filter_timeframe=None,
        from_date=None,
        to_date=None,
        strategy="buy_hold",
        init_cash=10000.0,
        fees=0.0,
        slippage=0.0,
        bb_windows="14,20,30",
        bb_stds="1.8,2.0,2.2",
        rsi_lowers="25,30,35",
        rsi_uppers="65,70,75",
        filter_rsi_lows="45",
        filter_rsi_highs="55",
        rrs="1.3,1.5,2.0",
        stop_pcts="0.01",
        ema_fast_windows="20",
        ema_slow_windows="50",
        pullback_atrs="0.25,0.5,0.75",
        atr_stop_multipliers="1.0,1.5",
        trend_rsi_lowers="45",
        trend_rsi_uppers="55",
        reclaim_lookbacks="3,5,8",
        cooldown_bars="8,12,20",
        ma_adx_mins="25,30",
        ma_max_cross_age_bars="3,6",
        breakout_lookbacks="20,30,50",
        breakout_atr_buffers="0.0,0.25,0.5",
        breakout_rsi_lowers="50,55",
        breakout_rsi_uppers="45,50",
        veb_lookbacks="30,45,60",
        veb_atr_expansions="1.5,2.0",
        veb_adx_mins="20,25",
        veb_sl_atr_buffers="0.5",
        macd_fast_windows="12",
        macd_slow_windows="26",
        macd_signal_windows="9",
        walk_forward=False,
        is_from=None,
        is_to=None,
        oos_from=None,
        oos_to=None,
        random_seed=42,
        random_entry_prob=0.01,
        random_long_bias=0.5,
        random_min_hold_bars=3,
        random_max_hold_bars=12,
        top=10,
    )
    config = run_quant_research._build_config(args)

    with pytest.raises(SystemExit, match="--from and --to are required"):
        run_quant_research._run_standard_research_from_args(args, config)
