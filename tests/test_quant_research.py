import sqlite3
import sys
from types import SimpleNamespace

import pandas as pd

from backend.features.trading import backtest_store
from backend.features.trading.quant_research import (
    QuantResearchConfig,
    QuantResearchResult,
    run_buy_hold_research,
    run_breakout_research,
    run_bollinger_research,
    run_bollinger_mtf_research,
    run_macd_research,
    run_no_trade_research,
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


def _sample_candles(periods=80):
    times = pd.date_range(start="2025-01-01", periods=periods, freq="15min")
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
            pullback_atrs=[0.5],
            atr_stop_multipliers=[1.0],
            rrs=[1.5],
            trend_rsi_lowers=[45],
            trend_rsi_uppers=[55],
        ),
    )

    assert _FakePortfolio.call_count == 1
    assert result.run["strategy"] == "trend_pullback"
    assert result.run["filter_timeframe"] == "M30"
    assert _FakePortfolio.last_kwargs["sl_stop"].notna().any()
    assert _FakePortfolio.last_kwargs["tp_stop"].notna().any()
    assert result.results[0]["parameter_json"]["pullback_atr"] == 0.5
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
