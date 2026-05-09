import pytest
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

from backend.features.trading.trigger_store import (
    init_trigger_db,
    upsert_schedule_rule,
    get_active_schedule_rules,
    create_trigger_run,
    update_trigger_run,
    get_trigger_run,
    get_trigger_history,
    add_trigger_event,
    get_trigger_events,
    save_trigger_snapshot,
    get_trigger_snapshot,
    list_schedule_rules,
    set_schedule_rule_enabled,
    delete_schedule_rule,
)
from backend.services.trading_service import run_trading_workflow_async
from backend.api.app import create_app, lifespan as app_lifespan
from backend.api.v1.triggers import (
    get_trigger_details as api_get_trigger_details,
    list_trigger_events as api_list_trigger_events,
    get_trigger_execution_snapshot as api_get_trigger_execution_snapshot,
)

@pytest.fixture
def temp_trigger_db(tmp_path):
    db_path = str(tmp_path / "test_triggers.sqlite")
    init_trigger_db(db_path)
    return db_path


def test_trigger_store_rules(temp_trigger_db):
    rule = {
        "name": "Test Rule",
        "symbol": "EURUSD",
        "timeframes": ["M5"],
        "mode": "paper",
        "interval_seconds": 60,
        "enabled": 1
    }
    rule_id = upsert_schedule_rule(temp_trigger_db, rule)
    assert rule_id is not None
    
    active_rules = get_active_schedule_rules(temp_trigger_db)
    assert len(active_rules) == 1
    assert active_rules[0]["name"] == "Test Rule"
    assert active_rules[0]["symbol"] == "EURUSD"

    all_rules = list_schedule_rules(temp_trigger_db)
    assert len(all_rules) == 1

    set_schedule_rule_enabled(temp_trigger_db, rule_id, False)
    assert get_active_schedule_rules(temp_trigger_db) == []
    disabled_rules = list_schedule_rules(temp_trigger_db)
    assert disabled_rules[0]["enabled"] == 0

    delete_schedule_rule(temp_trigger_db, rule_id)
    assert list_schedule_rules(temp_trigger_db) == []

def test_trigger_run_lifecycle(temp_trigger_db):
    trigger_id = create_trigger_run(temp_trigger_db, {
        "symbol": "GBPUSD",
        "mode": "paper",
        "status": "scheduled"
    })
    assert trigger_id.startswith("trig_")
    
    update_trigger_run(temp_trigger_db, trigger_id, {"status": "running", "started_at": "now"})
    run = get_trigger_run(temp_trigger_db, trigger_id)
    assert run["status"] == "running"
    assert run["symbol"] == "GBPUSD"

def test_trigger_events_and_snapshots(temp_trigger_db):
    trigger_id = "test_trig_123"
    create_trigger_run(temp_trigger_db, {"trigger_id": trigger_id, "symbol": "EURUSD", "mode": "paper", "status": "running"})
    
    add_trigger_event(temp_trigger_db, trigger_id, "test_event", message="Hello world")
    events = get_trigger_events(temp_trigger_db, trigger_id)
    assert len(events) == 1
    assert events[0]["event_type"] == "test_event"
    
    save_trigger_snapshot(temp_trigger_db, trigger_id, {"final_state": {"foo": "bar"}})
    snapshot = get_trigger_snapshot(temp_trigger_db, trigger_id)
    assert snapshot is not None
    assert snapshot["final_state"]["foo"] == "bar"

@pytest.mark.asyncio
@patch("backend.services.trading_service.get_compiled_graph")
async def test_run_trading_workflow_async_success(mock_get_graph, temp_trigger_db):
    # Mock LangGraph behavior
    mock_graph = MagicMock()
    mock_graph.stream.return_value = [
        {"node1": {"account_info": {"balance": 10000}, "error_flag": False}},
        {"node2": {"final_order": {"action": "HOLD", "reasoning": "Wait"}}}
    ]
    mock_get_graph.return_value = mock_graph
    
    # We need to patch the store functions to use our temp DB
    with patch("backend.services.trading_service.create_trigger_run", side_effect=lambda db, data: create_trigger_run(temp_trigger_db, data)), \
         patch("backend.services.trading_service.update_trigger_run", side_effect=lambda db, tid, data: update_trigger_run(temp_trigger_db, tid, data)), \
         patch("backend.services.trading_service.add_trigger_event", side_effect=lambda db, tid, et, **kwargs: add_trigger_event(temp_trigger_db, tid, et, **kwargs)), \
         patch("backend.services.trading_service.save_trigger_snapshot", side_effect=lambda db, tid, data: save_trigger_snapshot(temp_trigger_db, tid, data)):
        
        await run_trading_workflow_async("EURUSD", ["M5"], mode="paper")
        
    # Verify DB state
    runs = get_active_schedule_rules(temp_trigger_db) # Just checking if something exists
    from backend.features.trading.trigger_store import get_trigger_history
    history = get_trigger_history(temp_trigger_db)
    assert len(history) == 1
    assert history[0]["status"] == "success"
    assert history[0]["final_action"] == "HOLD"

@pytest.mark.asyncio
@patch("backend.services.trading_service.get_compiled_graph")
@patch("backend.services.trading_service.validate_order_prices", return_value=False)
async def test_run_trading_workflow_async_blocked(mock_validate, mock_get_graph, temp_trigger_db):
    mock_graph = MagicMock()
    mock_graph.stream.return_value = [
        {"node1": {"final_order": {"action": "BUY", "entry_price": 1.0, "sl": 1.1, "tp": 1.2}}}
    ]
    mock_get_graph.return_value = mock_graph
    
    with patch("backend.services.trading_service.create_trigger_run", side_effect=lambda db, data: create_trigger_run(temp_trigger_db, data)), \
         patch("backend.services.trading_service.update_trigger_run", side_effect=lambda db, tid, data: update_trigger_run(temp_trigger_db, tid, data)), \
         patch("backend.services.trading_service.add_trigger_event", side_effect=lambda db, tid, et, **kwargs: add_trigger_event(temp_trigger_db, tid, et, **kwargs)), \
         patch("backend.services.trading_service.save_trigger_snapshot", side_effect=lambda db, tid, data: save_trigger_snapshot(temp_trigger_db, tid, data)), \
         patch("backend.services.trading_service.resolve_strategy_profile", return_value=("M15", ["M30"])), \
         patch("backend.services.trading_service.validate_strategy_setup", return_value=(True, "OK", None, None)):
        
        await run_trading_workflow_async("EURUSD", ["M5"], mode="paper")
        
    from backend.features.trading.trigger_store import get_trigger_history
    history = get_trigger_history(temp_trigger_db)
    assert len(history) == 1
    assert history[0]["status"] == "blocked"
    assert "Invalid SL/TP" in history[0]["error_message"]
    
    # Verify snapshot exists even for blocked
    snapshot = get_trigger_snapshot(temp_trigger_db, history[0]["trigger_id"])
    assert snapshot is not None
    assert snapshot["guardrail_result"]["type"] == "price_guardrail"
    assert snapshot["request"]["symbol"] == "EURUSD"
    assert snapshot["request"]["mode"] == "paper"

@pytest.mark.asyncio
@patch("backend.services.trading_service.get_compiled_graph")
async def test_run_trading_workflow_async_failed_still_saves_snapshot(mock_get_graph, temp_trigger_db):
    mock_graph = MagicMock()
    mock_graph.stream.side_effect = RuntimeError("boom")
    mock_get_graph.return_value = mock_graph

    with patch("backend.services.trading_service.create_trigger_run", side_effect=lambda db, data: create_trigger_run(temp_trigger_db, data)), \
         patch("backend.services.trading_service.update_trigger_run", side_effect=lambda db, tid, data: update_trigger_run(temp_trigger_db, tid, data)), \
         patch("backend.services.trading_service.add_trigger_event", side_effect=lambda db, tid, et, **kwargs: add_trigger_event(temp_trigger_db, tid, et, **kwargs)), \
         patch("backend.services.trading_service.save_trigger_snapshot", side_effect=lambda db, tid, data: save_trigger_snapshot(temp_trigger_db, tid, data)):

        await run_trading_workflow_async("EURUSD", ["M5"], mode="paper")

    from backend.features.trading.trigger_store import get_trigger_history
    history = get_trigger_history(temp_trigger_db)
    assert len(history) == 1
    assert history[0]["status"] == "failed"
    assert "boom" in (history[0]["error_message"] or "")

    snapshot = get_trigger_snapshot(temp_trigger_db, history[0]["trigger_id"])
    assert snapshot is not None
    assert snapshot["request"]["symbol"] == "EURUSD"
    assert snapshot["final_state"]["symbol"] == "EURUSD"
    assert snapshot["final_state"]["timeframes"] == ["M5"]

def test_cleanup_history(temp_trigger_db):
    # Create an old record
    trigger_id = create_trigger_run(temp_trigger_db, {
        "symbol": "OLD",
        "mode": "paper",
        "status": "success",
        "created_at": "2020-01-01T00:00:00Z" 
    })
    
    # Create a new record
    create_trigger_run(temp_trigger_db, {
        "symbol": "NEW",
        "mode": "paper",
        "status": "success"
    })
    
    from backend.features.trading.trigger_store import cleanup_trigger_history
    deleted = cleanup_trigger_history(temp_trigger_db, days_to_keep=1)
    assert deleted >= 1
    
    history = get_trigger_history(temp_trigger_db)
    symbols = [r["symbol"] for r in history]
    assert "OLD" not in symbols
    assert "NEW" in symbols

@pytest.mark.asyncio
@patch("backend.services.trading_service.get_compiled_graph")
async def test_run_trading_workflow_async_exception_traceback(mock_get_graph, temp_trigger_db):
    mock_graph = MagicMock()
    mock_graph.stream.side_effect = ValueError("crash")
    mock_get_graph.return_value = mock_graph
    
    with patch("backend.services.trading_service.create_trigger_run", side_effect=lambda db, data: create_trigger_run(temp_trigger_db, data)), \
         patch("backend.services.trading_service.update_trigger_run", side_effect=lambda db, tid, data: update_trigger_run(temp_trigger_db, tid, data)), \
         patch("backend.services.trading_service.add_trigger_event", side_effect=lambda db, tid, et, **kwargs: add_trigger_event(temp_trigger_db, tid, et, **kwargs)), \
         patch("backend.services.trading_service.save_trigger_snapshot", side_effect=lambda db, tid, data: save_trigger_snapshot(temp_trigger_db, tid, data)):
        
        await run_trading_workflow_async("CRASH", ["M5"], mode="paper")
        
    history = get_trigger_history(temp_trigger_db, symbol="CRASH")
    assert history[0]["status"] == "failed"
    assert "Traceback:" in history[0]["error_message"]
    assert "ValueError: crash" in history[0]["error_message"]


def test_schedule_rule_request_validation():
    from backend.features.trading.schemas import ScheduleRuleRequest
    
    # Valid interval
    req = ScheduleRuleRequest(name="test", symbol="EURUSD", timeframes=["M5"], schedule_type="interval", interval_seconds=60)
    assert req.schedule_type == "interval"
    
    # Valid cron
    req = ScheduleRuleRequest(name="test", symbol="EURUSD", timeframes=["M5"], schedule_type="cron", cron_expression="0 * * * *")
    assert req.schedule_type == "cron"
    
    # Invalid type
    with pytest.raises(ValueError, match="schedule_type must be 'interval' or 'cron'"):
        ScheduleRuleRequest(name="test", symbol="EURUSD", timeframes=["M5"], schedule_type="invalid")
        
    # Invalid interval
    with pytest.raises(ValueError, match="interval_seconds must be > 0"):
        ScheduleRuleRequest(name="test", symbol="EURUSD", timeframes=["M5"], schedule_type="interval", interval_seconds=0)

    # Missing cron
    with pytest.raises(ValueError, match="cron_expression is required for cron type"):
        ScheduleRuleRequest(name="test", symbol="EURUSD", timeframes=["M5"], schedule_type="cron", cron_expression=None)


def test_trigger_history_filters(temp_trigger_db):
    rule_id_1 = str(uuid.uuid4())
    rule_id_2 = str(uuid.uuid4())
    
    # Create rules first to satisfy FK constraint
    upsert_schedule_rule(temp_trigger_db, {"rule_id": rule_id_1, "name": "rule1", "symbol": "EURUSD", "schedule_type": "interval"})
    upsert_schedule_rule(temp_trigger_db, {"rule_id": rule_id_2, "name": "rule2", "symbol": "GBPUSD", "schedule_type": "interval"})
    
    create_trigger_run(temp_trigger_db, {"trigger_id": "t1", "rule_id": rule_id_1, "symbol": "EURUSD", "mode": "paper", "status": "success"})
    create_trigger_run(temp_trigger_db, {"trigger_id": "t2", "rule_id": rule_id_2, "symbol": "GBPUSD", "mode": "live", "status": "success"})
    
    # Filter by mode
    history_live = get_trigger_history(temp_trigger_db, mode="live")
    assert len(history_live) == 1
    assert history_live[0]["symbol"] == "GBPUSD"
    
    # Filter by rule_id
    history_rule1 = get_trigger_history(temp_trigger_db, rule_id=rule_id_1)
    assert len(history_rule1) == 1
    assert history_rule1[0]["symbol"] == "EURUSD"


def test_list_schedule_rules_filter(temp_trigger_db):
    upsert_schedule_rule(temp_trigger_db, {"rule_id": "r1", "name": "enabled", "enabled": 1, "symbol": "EURUSD", "schedule_type": "interval"})
    upsert_schedule_rule(temp_trigger_db, {"rule_id": "r2", "name": "disabled", "enabled": 0, "symbol": "EURUSD", "schedule_type": "interval"})
    
    all_rules = list_schedule_rules(temp_trigger_db)
    assert len(all_rules) >= 2
    
    enabled_rules = list_schedule_rules(temp_trigger_db, enabled=True)
    assert any(r["rule_id"] == "r1" for r in enabled_rules)
    assert not any(r["rule_id"] == "r2" for r in enabled_rules)
    
    disabled_rules = list_schedule_rules(temp_trigger_db, enabled=False)
    assert not any(r["rule_id"] == "r1" for r in disabled_rules)
    assert any(r["rule_id"] == "r2" for r in disabled_rules)


def test_market_hours_crypto_is_open_on_weekend():
    from backend.features.trading.market_hours import is_market_open, get_market_status_message

    saturday = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)

    assert is_market_open(saturday, symbol="BTCUSD") is True
    assert "Crypto 시장 열림" in get_market_status_message(saturday, symbol="BTCUSD")
    assert is_market_open(saturday, symbol="EURUSD") is False


@pytest.mark.asyncio
async def test_scheduler_interval_due_and_update(temp_trigger_db):
    from backend.services.scheduler import TriggerScheduler
    
    scheduler = TriggerScheduler()
    now = datetime.now(timezone.utc)
    rule_id = "r_interval_due"
    
    rule = {
        "rule_id": rule_id,
        "name": "Interval Due",
        "symbol": "EURUSD",
        "timeframes_json": '["M5"]',
        "mode": "paper",
        "enabled": 1,
        "next_trigger_at": (now - timedelta(seconds=10)).isoformat(),
        "schedule_type": "interval",
        "interval_seconds": 60
    }
    
    with patch("backend.services.scheduler.get_active_schedule_rules", return_value=[rule]), \
         patch("backend.services.scheduler.update_rule_last_triggered") as mock_update, \
         patch("backend.services.scheduler.run_trading_workflow_async", new_callable=AsyncMock) as mock_wf, \
         patch("backend.services.scheduler.create_trigger_run", return_value="t123"), \
         patch("backend.services.scheduler.add_trigger_event"):
        
        await scheduler._check_and_trigger()
        
        # 1. Verify next_trigger_at was updated
        assert mock_update.called
        args = mock_update.call_args[0]
        assert args[1] == rule_id
        
        # 2. Verify workflow started
        await asyncio.sleep(0.1)
        mock_wf.assert_called_once()


@pytest.mark.asyncio
async def test_scheduler_cron_due_and_timezone_utc(temp_trigger_db):
    from backend.services.scheduler import get_next_cron_time
    from zoneinfo import ZoneInfo
    
    # 10:00 KST (Seoul) is 01:00 UTC
    # Hourly cron at 0 minutes
    # If now is 10:05 KST, next is 11:00 KST (02:00 UTC)
    
    now_kst = datetime(2026, 5, 1, 10, 5, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    
    next_dt = get_next_cron_time("0 * * * *", "Asia/Seoul", now=now_kst)
    
    # Next hourly in Seoul (11:00 KST) is 02:00 UTC
    assert next_dt is not None
    assert next_dt.hour == 2
    assert next_dt.minute == 0
    assert next_dt.tzinfo == timezone.utc


@pytest.mark.asyncio
@patch("backend.services.trading_service.get_compiled_graph")
@patch("backend.services.trading_service.execute_mock_order")
async def test_run_trading_workflow_async_order_failed_with_payload(mock_exec, mock_get_graph, temp_trigger_db):
    mock_graph = MagicMock()
    mock_graph.stream.return_value = [
        {"node": {
            "final_order": {"action": "BUY", "entry_price": 1.1, "sl": 1.0, "tp": 1.4},
            "indicator_data": {"M5": {"latest": {"close": 1.1, "atr14": 0.1}}}
        }}
    ]
    mock_get_graph.return_value = mock_graph
    
    # Simulate execution failure
    mock_exec.return_value = {"retcode": 10001, "comment": "Invalid volume"}
    
    with patch("backend.services.trading_service.create_trigger_run", side_effect=lambda db, data: create_trigger_run(temp_trigger_db, data)), \
         patch("backend.services.trading_service.update_trigger_run", side_effect=lambda db, tid, data: update_trigger_run(temp_trigger_db, tid, data)), \
         patch("backend.services.trading_service.add_trigger_event", side_effect=lambda db, tid, et, **kwargs: add_trigger_event(temp_trigger_db, tid, et, **kwargs)), \
         patch("backend.services.trading_service.save_trigger_snapshot", side_effect=lambda db, tid, data: save_trigger_snapshot(temp_trigger_db, tid, data)), \
         patch("backend.services.trading_service.validate_strategy_setup", return_value=(True, "OK", None, None)), \
         patch("backend.services.trading_service.resolve_strategy_profile", return_value=("M15", ["M30"])):
        
        await run_trading_workflow_async("EURUSD", ["M5"], mode="paper")
        
    trigger_id = get_trigger_history(temp_trigger_db)[0]["trigger_id"]
    
    # 1. Verify Event Payload
    events = get_trigger_events(temp_trigger_db, trigger_id)
    fail_event = next((e for e in events if e["event_type"] == "order_failed"), None)
    assert fail_event is not None
    
    import json
    payload = json.loads(fail_event["payload_json"])
    assert payload["success"] is False
    assert payload["raw_response"]["retcode"] == 10001

    # 2. Verify Snapshot Payload
    snapshot = get_trigger_snapshot(temp_trigger_db, trigger_id)
    res = snapshot["guardrail_result"]
    assert res["type"] == "execution_error"
    assert res["execution_details"]["raw_response"]["retcode"] == 10001


@pytest.mark.asyncio
async def test_scheduler_lock_deduplication(temp_trigger_db):
    from backend.services.scheduler import TriggerScheduler
    
    scheduler = TriggerScheduler()
    rule_id = "r_locked"
    scheduler._rule_locks[rule_id] = True # Locked
    
    now = datetime.now(timezone.utc)
    rule = {
        "rule_id": rule_id,
        "name": "Locked Rule",
        "symbol": "EURUSD",
        "timeframes_json": '["M5"]',
        "mode": "paper",
        "enabled": 1,
        "next_trigger_at": (now - timedelta(seconds=10)).isoformat(),
        "schedule_type": "interval",
        "interval_seconds": 60
    }
    
    with patch("backend.services.scheduler.get_active_schedule_rules", return_value=[rule]), \
         patch("backend.services.scheduler.update_rule_last_triggered") as mock_update, \
         patch("backend.services.scheduler.create_trigger_run") as mock_create_run, \
         patch("backend.services.scheduler.add_trigger_event"):
        
        await scheduler._check_and_trigger()
        
        # Should update next_trigger_at to set next tick
        assert mock_update.called
        # Should create a 'skipped' run
        assert mock_create_run.called
        run_data = mock_create_run.call_args[0][1]
        assert run_data["status"] == "skipped"


@pytest.mark.asyncio
async def test_scheduler_market_hours_gating(temp_trigger_db):
    from backend.services.scheduler import TriggerScheduler
    
    scheduler = TriggerScheduler()
    now = datetime.now(timezone.utc)
    rule = {
        "rule_id": "r_market",
        "market_hours_only": 1,
        "next_trigger_at": (now - timedelta(seconds=10)).isoformat(),
        "schedule_type": "interval",
        "interval_seconds": 60
    }
    
    with patch("backend.services.scheduler.get_active_schedule_rules", return_value=[rule]), \
         patch("backend.services.scheduler.is_market_open", return_value=False), \
         patch("backend.services.scheduler.update_rule_last_triggered") as mock_update, \
         patch("backend.services.scheduler.create_trigger_run") as mock_create:
        
        await scheduler._check_and_trigger()
        
        # Should update next_trigger_at to avoid hot-looping
        assert mock_update.called
        # Should NOT create a run
        mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_scheduler_loop_exception_resilience():
    from backend.services.scheduler import TriggerScheduler
    
    scheduler = TriggerScheduler()
    scheduler.check_interval = 0.01
    
    call_count = 0
    async def side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Tick 1 failed")
        return # Success for Tick 2
        
    with patch.object(scheduler, "_check_and_trigger", side_effect=side_effect):
        scheduler.running = True
        task = asyncio.create_task(scheduler._loop())
        
        await asyncio.sleep(0.05)
        scheduler.running = False
        await task
        
        assert call_count > 1 # Tick 2 occurred despite Tick 1 failure


@pytest.mark.asyncio
@patch("backend.services.trading_service.get_compiled_graph")
async def test_run_trading_workflow_async_rich_success(mock_get_graph, temp_trigger_db):
    mock_graph = MagicMock()
    # R/R = (1.4 - 1.1) / (1.1 - 1.0) = 3.0 (safe from float issues)
    mock_graph.stream.return_value = [
        {"node": {
            "final_order": {"action": "BUY", "entry_price": 1.1, "sl": 1.0, "tp": 1.4}, 
            "account_info": {"balance": 10000},
            "indicator_data": {"M5": {"latest": {"close": 1.1, "atr14": 0.1}}}
        }}
    ]
    mock_get_graph.return_value = mock_graph
    
    with patch("backend.services.trading_service.create_trigger_run", side_effect=lambda db, data: create_trigger_run(temp_trigger_db, data)), \
         patch("backend.services.trading_service.update_trigger_run", side_effect=lambda db, tid, data: update_trigger_run(temp_trigger_db, tid, data)), \
         patch("backend.services.trading_service.add_trigger_event", side_effect=lambda db, tid, et, **kwargs: add_trigger_event(temp_trigger_db, tid, et, **kwargs)), \
         patch("backend.services.trading_service.save_trigger_snapshot", side_effect=lambda db, tid, data: save_trigger_snapshot(temp_trigger_db, tid, data)), \
         patch("backend.services.trading_service.validate_strategy_setup", return_value=(True, "OK", None, None)), \
         patch("backend.services.trading_service.resolve_strategy_profile", return_value=("M15", ["M30"])):
        
        await run_trading_workflow_async("EURUSD", ["M5"], mode="paper")
        
    history = get_trigger_history(temp_trigger_db)
    assert history[0]["status"] == "success"
    
    snapshot = get_trigger_snapshot(temp_trigger_db, history[0]["trigger_id"])
    res = snapshot["guardrail_result"]
    assert res["type"] == "all_pass"
    assert res["success"] is True
    assert "price_guardrail" in res["details"]

@pytest.mark.asyncio
async def test_fastapi_lifespan_scheduler_integration():
    """FastAPI lifespan이 scheduler.start/stop을 호출하는지 mock 테스트"""
    app = create_app()

    with patch("backend.api.app.scheduler.start", new_callable=AsyncMock) as mock_start, \
         patch("backend.api.app.scheduler.stop", new_callable=AsyncMock) as mock_stop, \
         patch("backend.api.app.init_mt5_connection", return_value=True), \
         patch("backend.api.app.shutdown_mt5_connection", return_value=True), \
         patch("backend.api.app.init_trigger_db"):
        async with app_lifespan(app):
            mock_start.assert_called_once()

        mock_stop.assert_called_once()


def test_api_trigger_detail_and_not_found(temp_trigger_db):
    """GET /api/v1/triggers/{id} API 성공 및 404 테스트"""
    trigger_id = "trig_api_test"
    with patch(
        "backend.api.v1.triggers.get_trigger_run",
        side_effect=lambda trigger_id: get_trigger_run(temp_trigger_db, trigger_id),
    ):
        import asyncio
        with pytest.raises(HTTPException) as exc:
            asyncio.run(api_get_trigger_details("non_existent"))
        assert exc.value.status_code == 404

        create_trigger_run(
            temp_trigger_db,
            {"trigger_id": trigger_id, "symbol": "EURUSD", "mode": "paper", "status": "success"},
        )
        run = asyncio.run(api_get_trigger_details(trigger_id))
        assert run["trigger_id"] == trigger_id


def test_api_trigger_events_and_snapshot(temp_trigger_db):
    """/events, /snapshot API가 데이터를 올바르게 반환하는지 테스트"""
    trigger_id = "trig_api_events"

    with patch(
        "backend.api.v1.triggers.get_trigger_events",
        side_effect=lambda trigger_id: get_trigger_events(temp_trigger_db, trigger_id),
    ), patch(
        "backend.api.v1.triggers.get_trigger_snapshot",
        side_effect=lambda trigger_id: get_trigger_snapshot(temp_trigger_db, trigger_id),
    ):
        import asyncio
        with pytest.raises(HTTPException) as exc:
            asyncio.run(api_get_trigger_execution_snapshot(trigger_id))
        assert exc.value.status_code == 404

        empty_events = asyncio.run(api_list_trigger_events(trigger_id))
        assert empty_events == []

        create_trigger_run(
            temp_trigger_db,
            {
                "trigger_id": trigger_id,
                "symbol": "EURUSD",
                "mode": "paper",
                "status": "running",
            },
        )
        add_trigger_event(temp_trigger_db, trigger_id, "test_event", message="API test")
        save_trigger_snapshot(temp_trigger_db, trigger_id, {"final_state": {"status": "ok"}})

        events = asyncio.run(api_list_trigger_events(trigger_id))
        assert len(events) == 1
        assert events[0]["event_type"] == "test_event"

        snapshot = asyncio.run(api_get_trigger_execution_snapshot(trigger_id))
        assert snapshot["final_state"]["status"] == "ok"
