import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.core.state_models import Order, OrderAction
from backend.features.trading.usecase import TradeExecutionUseCase
from backend.services.scheduler import TriggerScheduler
from backend.services.trading_service import run_trading_workflow_async


def _events(caplog):
    return {getattr(record, "event", None) for record in caplog.records}


def _records_with_event(caplog, event):
    return [record for record in caplog.records if getattr(record, "event", None) == event]


def test_trade_execution_logs_mt5_request_response_and_success_predicate(caplog):
    class FakeMT5:
        def send_order(self, **_kwargs):
            return {
                "retcode": 10009,
                "comment": "Done",
                "order": 12345,
                "deal": 67890,
                "price": 65000.5,
            }

    order = Order(
        action=OrderAction.BUY,
        symbol="BTCUSD",
        entry_price=65000.0,
        sl_price=64500.0,
        tp_price=66500.0,
    )

    caplog.set_level(logging.INFO)
    result = TradeExecutionUseCase(FakeMT5()).execute_trade(
        order=order,
        current_loss_pct=0.0,
        today_trade_count=0,
        account_balance=10000.0,
        risk_per_trade_pct=0.005,
        trigger_id="trig_log",
        workflow_run_id="run_log",
        rule_id="rule_log",
        mode="live",
    )

    assert result.success is True
    assert {
        "trigger.execution.requested",
        "trigger.execution.mt5_response",
        "trigger.execution.success_predicate",
    }.issubset(_events(caplog))

    predicate = _records_with_event(caplog, "trigger.execution.success_predicate")[0]
    assert predicate.trigger_id == "trig_log"
    assert predicate.workflow_run_id == "run_log"
    assert predicate.rule_id == "rule_log"
    assert predicate.symbol == "BTCUSD"
    assert predicate.success is True


@pytest.mark.asyncio
async def test_scheduler_logs_not_due_market_hours_and_lock_skips(caplog):
    now = datetime.now(timezone.utc)
    future = (now + timedelta(minutes=5)).replace(microsecond=0).isoformat()
    due = (now - timedelta(seconds=1)).replace(microsecond=0).isoformat()
    rules = [
        {
            "rule_id": "rule_not_due",
            "name": "Not Due",
            "symbol": "BTCUSD",
            "mode": "paper",
            "timeframes_json": '["M15"]',
            "next_trigger_at": future,
        },
        {
            "rule_id": "rule_market",
            "name": "Market Closed",
            "symbol": "EURUSD",
            "mode": "paper",
            "timeframes_json": '["M15"]',
            "next_trigger_at": due,
            "interval_seconds": 60,
            "market_hours_only": True,
        },
        {
            "rule_id": "rule_lock",
            "name": "Locked",
            "symbol": "BTCUSD",
            "mode": "paper",
            "timeframes_json": '["M15"]',
            "next_trigger_at": due,
            "interval_seconds": 60,
        },
    ]
    scheduler = TriggerScheduler()
    scheduler._rule_locks["rule_lock"] = True

    caplog.set_level(logging.DEBUG)
    with patch("backend.services.scheduler.get_active_schedule_rules", return_value=rules), \
         patch("backend.services.scheduler.is_market_open", return_value=False), \
         patch("backend.services.scheduler.update_rule_last_triggered"), \
         patch("backend.services.scheduler.create_trigger_run", return_value="trig_lock"), \
         patch("backend.services.scheduler.add_trigger_event"):
        await scheduler._check_and_trigger()

    skipped = _records_with_event(caplog, "trigger.scheduler.rule_skipped")
    reasons = {record.skip_reason for record in skipped}
    assert {"not_due", "market_hours_skip", "lock_skip"}.issubset(reasons)
    lock_record = next(record for record in skipped if record.skip_reason == "lock_skip")
    assert lock_record.rule_id == "rule_lock"
    assert lock_record.trigger_id == "trig_lock"


@pytest.mark.asyncio
async def test_trading_service_logs_hold_decision(caplog):
    graph = MagicMock()
    graph.stream.return_value = [{"node": {"final_order": {"action": "HOLD", "reasoning": "wait"}}}]

    caplog.set_level(logging.INFO)
    with patch("backend.services.trading_service.get_compiled_graph", return_value=graph), \
         patch("backend.services.trading_service.create_trigger_run", return_value="trig_hold"), \
         patch("backend.services.trading_service.update_trigger_run"), \
         patch("backend.services.trading_service.add_trigger_event"), \
         patch("backend.services.trading_service.save_trigger_snapshot"):
        await run_trading_workflow_async(
            "BTCUSD",
            ["M15"],
            mode="paper",
            strategy_override="Moving Average Crossover",
            rule_id="rule_hold",
        )

    hold = _records_with_event(caplog, "trigger.decision.hold")[0]
    assert hold.trigger_id == "trig_hold"
    assert hold.rule_id == "rule_hold"
    assert hold.symbol == "BTCUSD"
    assert hold.mode == "paper"
    assert hold.final_action == "HOLD"


@pytest.mark.asyncio
async def test_trading_service_logs_price_guardrail_rejection(caplog):
    graph = MagicMock()
    graph.stream.return_value = [
        {
            "node": {
                "final_order": {
                    "action": "BUY",
                    "entry_price": 1.0,
                    "sl_price": 1.1,
                    "tp_price": 1.2,
                    "reasoning": "invalid",
                },
                "account_info": {"balance": 10000.0},
            }
        }
    ]

    caplog.set_level(logging.WARNING)
    with patch("backend.services.trading_service.get_compiled_graph", return_value=graph), \
         patch("backend.services.trading_service.create_trigger_run", return_value="trig_reject"), \
         patch("backend.services.trading_service.update_trigger_run"), \
         patch("backend.services.trading_service.add_trigger_event"), \
         patch("backend.services.trading_service.save_trigger_snapshot"), \
         patch("backend.services.trading_service.resolve_strategy_profile", return_value=("M15", ["M30"])), \
         patch("backend.services.trading_service.validate_strategy_setup", return_value=(True, "OK", None, None)):
        await run_trading_workflow_async("BTCUSD", ["M15"], mode="paper", rule_id="rule_reject")

    rejected = _records_with_event(caplog, "trigger.guardrail.rejected")[0]
    assert rejected.trigger_id == "trig_reject"
    assert rejected.rule_id == "rule_reject"
    assert rejected.blocked_stage == "price_guardrail"
    assert "Invalid SL/TP" in rejected.failure_reason


@pytest.mark.asyncio
async def test_trading_service_logs_node_and_snapshot_events(caplog):
    graph = MagicMock()
    # Mock stream to emit two nodes
    graph.stream.return_value = [
        {"tech_analyst": {"tech_summary": {"trend": "bullish"}}},
        {"chief_trader": {"final_order": {"action": "HOLD"}}}
    ]

    caplog.set_level(logging.INFO)
    with patch("backend.services.trading_service.get_compiled_graph", return_value=graph), \
         patch("backend.services.trading_service.create_trigger_run", return_value="trig_node"), \
         patch("backend.services.trading_service.update_trigger_run"), \
         patch("backend.services.trading_service.add_trigger_event"), \
         patch("backend.services.trading_service.save_trigger_snapshot"):
        await run_trading_workflow_async("BTCUSD", ["M15"], mode="paper", trigger_id="trig_node")

    events = _events(caplog)
    assert "trigger.workflow.node_completed" in events
    assert "trigger.snapshot.saved" in events

    node_logs = _records_with_event(caplog, "trigger.workflow.node_completed")
    assert len(node_logs) == 2
    assert node_logs[0].node_name == "tech_analyst"
    assert node_logs[1].node_name == "chief_trader"

    snapshot_logs = _records_with_event(caplog, "trigger.snapshot.saved")
    assert len(snapshot_logs) == 1
    assert snapshot_logs[0].trigger_id == "trig_node"
