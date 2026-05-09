import pytest
from unittest.mock import MagicMock, patch
from backend.services.trading_service import run_trading_workflow_async

@pytest.mark.asyncio
async def test_llm_agent_visibility_events():
    """Verify that structured agent outputs are recorded as trigger events."""
    trigger_id = "test_step9_123"
    symbol = "EURUSD"
    
    # 1. Mock LangGraph stream to emit agent outputs
    mock_graph = MagicMock()
    mock_graph.stream.return_value = [
        {"tech_analyst": {
            "tech_summary": {
                "market_regime": "Bullish",
                "trade_worthy": True,
                "trend": "bullish",
                "summary": "Trend is clean.",
                "prompt": "must not be stored",
                "chain_of_thought": "must not be stored"
            }
        }},
        {"strategist": {
            "strategy_hypothesis": {
                "selected_strategy": "MA_CROSS",
                "action": "BUY",
                "confidence": 0.85,
                "reasoning": "Strong trend",
                "prompt": "must not be stored",
                "hidden_reasoning": "must not be stored"
            }
        }},
        {"chief_trader": {
            "final_order": {
                "action": "BUY",
                "entry_price": 1.1000,
                "sl_price": 1.0950,
                "tp_price": 1.1100,
                "target_rr": 2.0,
                "reasoning": "Confirmed by all",
                "prompt": "must not be stored",
                "chain_of_thought": "must not be stored"
            }
        }}
    ]
    
    # 2. Patch trading_service dependencies
    with patch("backend.services.trading_service.get_compiled_graph", return_value=mock_graph), \
         patch("backend.services.trading_service.create_trigger_run", return_value=trigger_id), \
         patch("backend.services.trading_service.update_trigger_run"), \
         patch("backend.services.trading_service.add_trigger_event") as mock_add_event, \
         patch("backend.services.trading_service.save_trigger_snapshot"), \
         patch("backend.services.trading_service.validate_strategy_setup", return_value=(True, "OK", None, None)), \
         patch("backend.services.trading_service.execute_mock_order", return_value={"retcode": 10009, "order": 12345}), \
         patch("backend.services.trading_service.track_open_position"):
        
        await run_trading_workflow_async(symbol, mode="paper", trigger_id=trigger_id)
        
    # 3. Verify add_trigger_event calls
    event_types = [call.args[2] for call in mock_add_event.call_args_list]
    assert "agent_tech" in event_types
    assert "agent_strat" in event_types
    assert "agent_chief" in event_types
    
    # Verify payloads
    tech_event = next(call for call in mock_add_event.call_args_list if call.args[2] == "agent_tech")
    assert tech_event.kwargs["payload"]["market_regime"] == "Bullish"
    assert "prompt" not in tech_event.kwargs["payload"]
    assert "chain_of_thought" not in tech_event.kwargs["payload"]
    
    strat_event = next(call for call in mock_add_event.call_args_list if call.args[2] == "agent_strat")
    assert strat_event.kwargs["payload"]["selected_strategy"] == "MA_CROSS"
    assert strat_event.kwargs["payload"]["action"] == "BUY"
    assert "reasoning" in strat_event.kwargs["payload"]
    assert "prompt" not in strat_event.kwargs["payload"]
    assert "hidden_reasoning" not in strat_event.kwargs["payload"]
    
    chief_event = next(call for call in mock_add_event.call_args_list if call.args[2] == "agent_chief")
    assert chief_event.kwargs["payload"]["action"] == "BUY"
    assert chief_event.kwargs["payload"]["target_rr"] == 2.0
    assert "reasoning" in chief_event.kwargs["payload"]
    assert "prompt" not in chief_event.kwargs["payload"]
    assert "chain_of_thought" not in chief_event.kwargs["payload"]
