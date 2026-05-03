from unittest.mock import patch

import pytest

from backend.api.v1.triggers import (
    get_trigger_execution_snapshot,
    list_trigger_events,
    list_trigger_history,
)

# 1. Failed live execution API test
@patch("backend.api.v1.triggers.get_trigger_events")
@patch("backend.api.v1.triggers.get_trigger_snapshot")
@pytest.mark.asyncio
async def test_failed_live_execution_api(mock_snapshot, mock_events):
    trigger_id = "failed_run_123"
    
    # Mock events containing order_failed with raw_response
    mock_events.return_value = [
        {
            "event_type": "order_failed",
            "message": "Invalid ticket",
            "payload": {
                "success": False,
                "failure_reason": "Invalid ticket",
                "raw_response": {"retcode": 10009, "order": 0, "price": 0.0}
            }
        }
    ]
    
    # Mock snapshot containing guardrail_result.execution_details
    mock_snapshot.return_value = {
        "guardrail_result": {
            "type": "execution_error",
            "success": False,
            "message": "Invalid ticket",
            "execution_details": {
                "success": False,
                "ticket": 0,
                "failure_reason": "Invalid ticket",
                "raw_response": {"retcode": 10009, "order": 0, "price": 0.0}
            }
        }
    }
    
    events = await list_trigger_events(trigger_id)
    order_failed_event = next(e for e in events if e["event_type"] == "order_failed")
    assert order_failed_event["payload"]["raw_response"]["order"] == 0
    
    snapshot = await get_trigger_execution_snapshot(trigger_id)
    assert snapshot["guardrail_result"]["execution_details"]["ticket"] == 0
    assert "Invalid ticket" in snapshot["guardrail_result"]["message"]

# 2. Success live execution API test
@patch("backend.api.v1.triggers.get_trigger_events")
@patch("backend.api.v1.triggers.get_trigger_snapshot")
@pytest.mark.asyncio
async def test_success_live_execution_api(mock_snapshot, mock_events):
    trigger_id = "success_run_456"
    
    # Mock events containing order_acked with ticket/deal/price/raw_response
    mock_events.return_value = [
        {
            "event_type": "order_acked",
            "message": "Order success: ticket 12345",
            "payload": {
                "success": True,
                "ticket": 12345,
                "executed_price": 65000.5,
                "mt5_deal": 98765432,
                "raw_response": {"retcode": 10009, "order": 12345, "deal": 98765432, "price": 65000.5}
            }
        }
    ]
    
    # Mock snapshot containing execution_details
    mock_snapshot.return_value = {
        "guardrail_result": {
            "type": "all_pass",
            "success": True,
            "details": {
                "execution_details": {
                    "success": True,
                    "ticket": 12345,
                    "deal": 98765432,
                    "executed_price": 65000.5,
                    "raw_response": {"retcode": 10009, "order": 12345, "deal": 98765432, "price": 65000.5}
                }
            }
        }
    }
    
    events = await list_trigger_events(trigger_id)
    order_acked_event = next(e for e in events if e["event_type"] == "order_acked")
    assert order_acked_event["payload"]["ticket"] == 12345
    assert order_acked_event["payload"]["raw_response"]["deal"] == 98765432
    
    snapshot = await get_trigger_execution_snapshot(trigger_id)
    assert snapshot["guardrail_result"]["success"] is True
    assert snapshot["guardrail_result"]["details"]["execution_details"]["ticket"] == 12345
    assert snapshot["guardrail_result"]["details"]["execution_details"]["deal"] == 98765432
    assert snapshot["guardrail_result"]["details"]["execution_details"]["executed_price"] == 65000.5

# 3. History filter test
@patch("backend.api.v1.triggers.get_trigger_history")
@pytest.mark.asyncio
async def test_history_filter_api(mock_history):
    # Mock history filter result
    mock_history.return_value = [
        {
            "trigger_id": "failed_run_123",
            "status": "failed",
            "mode": "live",
            "symbol": "BTCUSD"
        }
    ]
    
    history = await list_trigger_history(status="failed", mode="live", symbol="BTCUSD")
    assert len(history) == 1
    assert history[0]["status"] == "failed"
    assert history[0]["mode"] == "live"
    assert history[0]["symbol"] == "BTCUSD"
    
    # Verify mock was called with correct parameters
    mock_history.assert_called_once_with(
        limit=50,
        status="failed",
        symbol="BTCUSD",
        mode="live",
        rule_id=None,
        start_date=None,
        end_date=None
    )
