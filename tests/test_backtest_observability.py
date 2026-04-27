import json

import pandas as pd

from backend.scripts import run_backtest
from backend.scripts.run_backtest import BacktestEngine


def _sample_backtest_df(periods=120):
    times = pd.date_range("2025-01-01 00:00:00", periods=periods, freq="15min")
    return pd.DataFrame(
        {
            "time": times,
            "open": [100.0 + i * 0.1 for i in range(periods)],
            "high": [101.0 + i * 0.1 for i in range(periods)],
            "low": [99.0 + i * 0.1 for i in range(periods)],
            "close": [100.5 + i * 0.1 for i in range(periods)],
            "tick_volume": [100 + i for i in range(periods)],
            "spread": [2 for _ in range(periods)],
            "real_volume": [0 for _ in range(periods)],
        }
    )


class _HoldGraph:
    def __init__(self):
        self.calls = 0

    def stream(self, _initial_state):
        self.calls += 1
        yield {
            "fetch_data": {
                "indicator_data": {"M15": {"latest": {"close": 100.0}}},
                "account_info": {"balance": 10000.0},
                "error_flag": False,
            }
        }
        yield {
            "tech_analyst": {
                "tech_summary": {"market_regime": "Ranging"},
                "error_flag": False,
            }
        }
        yield {
            "chief_trader": {
                "final_order": {"action": "HOLD", "reasoning": "No edge"},
                "error_flag": False,
            }
        }


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_backtest_max_steps_limits_graph_calls_and_writes_jsonl(monkeypatch, tmp_path):
    graph = _HoldGraph()
    monkeypatch.setattr("backend.workflows.graph.get_compiled_graph", lambda: graph)
    log_path = tmp_path / "backtest.jsonl"
    df = _sample_backtest_df()
    engine = BacktestEngine(
        symbol="BTCUSD",
        timeframes=["M15"],
        dfs={"M15": df},
        step_interval=1,
        max_steps=3,
        run_id="BT-OBS",
        event_log_path=str(log_path),
    )

    trades = engine.run()
    engine.event_logger.close()

    assert trades == []
    assert graph.calls == 3
    events = _read_jsonl(log_path)
    assert events[0]["event"] == "backtest_start"
    assert events[0]["total_steps"] == 3
    assert events[0]["max_steps"] == 3
    assert len([event for event in events if event["event"] == "node_complete"]) == 9
    assert len([event for event in events if event["event"] == "decision_recorded"]) == 3
    assert events[-1]["event"] == "backtest_complete"


def test_backtest_start_step_skips_initial_decision_positions(monkeypatch, tmp_path):
    graph = _HoldGraph()
    monkeypatch.setattr("backend.workflows.graph.get_compiled_graph", lambda: graph)
    log_path = tmp_path / "backtest.jsonl"
    df = _sample_backtest_df()
    engine = BacktestEngine(
        symbol="BTCUSD",
        timeframes=["M15"],
        dfs={"M15": df},
        step_interval=1,
        start_step=5,
        max_steps=2,
        run_id="BT-START-STEP",
        event_log_path=str(log_path),
    )

    engine.run()
    engine.event_logger.close()

    events = _read_jsonl(log_path)
    assert graph.calls == 2
    assert events[0]["event"] == "backtest_start"
    assert events[0]["start_step"] == 5
    step_starts = [event for event in events if event["event"] == "step_start"]
    assert [event["step_index"] for event in step_starts] == [105, 106]


def test_backtest_log_level_filters_lower_priority_events(monkeypatch, tmp_path):
    graph = _HoldGraph()
    monkeypatch.setattr("backend.workflows.graph.get_compiled_graph", lambda: graph)
    log_path = tmp_path / "backtest.jsonl"
    df = _sample_backtest_df()
    engine = BacktestEngine(
        symbol="BTCUSD",
        timeframes=["M15"],
        dfs={"M15": df},
        step_interval=1,
        max_steps=1,
        run_id="BT-LOG-LEVEL",
        event_log_path=str(log_path),
        event_log_level="INFO",
    )

    engine.run()
    engine.event_logger.close()

    events = _read_jsonl(log_path)
    assert [event["event"] for event in events] == ["backtest_start", "backtest_complete"]
    assert all(event["level"] == "INFO" for event in events)


def test_no_review_skips_closed_trade_reviewer(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(run_backtest, "review_closed_trade", lambda *_args, **_kwargs: calls.append(True))
    log_path = tmp_path / "backtest.jsonl"
    df = _sample_backtest_df()
    engine = BacktestEngine(
        symbol="BTCUSD",
        timeframes=["M15"],
        dfs={"M15": df},
        review_trades=False,
        run_id="BT-NO-REVIEW",
        event_log_path=str(log_path),
    )

    engine._record_closed_trade(
        {
            "trade_id": "BT-1",
            "action": "BUY",
            "entry_time": "2025-01-01 00:00:00",
            "exit_time": "2025-01-01 01:00:00",
            "exit_reason": "Take Profit",
            "pnl": 12.5,
        }
    )
    engine.event_logger.close()

    assert calls == []
    events = _read_jsonl(log_path)
    assert [event["event"] for event in events] == ["trade_closed", "trade_review_skipped"]
