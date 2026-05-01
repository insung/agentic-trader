import pytest
import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

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
    get_trigger_snapshot
)
from backend.services.trading_service import run_trading_workflow_async

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
         patch("backend.services.trading_service.save_trigger_snapshot", side_effect=lambda db, tid, data: save_trigger_snapshot(temp_trigger_db, tid, data)):
        
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
