import pytest
from unittest.mock import MagicMock, patch
from backend.services.trading_service import run_trading_workflow_async
from backend.features.trading.adapters.mt5_execution import send_market_order
from backend.core.state_models import OrderResult, Order, OrderAction
from collections import namedtuple

# 1. MT5 adapter namedtuple to dict test
def test_mt5_adapter_namedtuple_conversion():
    # Simulate MT5 result object
    Result = namedtuple("OrderSendResult", ["retcode", "comment", "order", "deal", "price", "request_id"])
    mock_result = Result(retcode=10009, comment="Done", order=12345, deal=67890, price=65000.0, request_id=111)
    
    # We need to mock mt5 module within the adapter to avoid real calls
    with patch("backend.features.trading.adapters.mt5_execution.mt5") as mock_mt5:
        mock_mt5.ORDER_TYPE_BUY = 0
        mock_mt5.TRADE_ACTION_DEAL = 1
        mock_mt5.ORDER_TIME_GTC = 0
        mock_mt5.ORDER_FILLING_IOC = 1
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=65000.0, bid=64999.0)
        mock_mt5.order_send.return_value = mock_result
        
        res_dict = send_market_order("BTCUSD", "buy", 0.01, 64500, 66500)
        
        assert isinstance(res_dict, dict)
        assert res_dict["retcode"] == 10009
        assert res_dict["order"] == 12345
        assert res_dict["price"] == 65000.0

# 2. Live failure/success branching tests
@pytest.mark.asyncio
@patch("backend.services.trading_service.create_trigger_run")
@patch("backend.services.trading_service.update_trigger_run")
@patch("backend.services.trading_service.add_trigger_event")
@patch("backend.services.trading_service.save_trigger_snapshot")
@patch("backend.services.trading_service.get_compiled_graph")
@patch("backend.services.trading_service.TradeExecutionUseCase")
@patch("backend.services.trading_service.track_open_position")
async def test_live_execution_branching(
    mock_track, mock_usecase_cls, mock_graph, mock_snapshot, mock_event, mock_update, mock_create
):
    # Setup mocks
    mock_usecase = mock_usecase_cls.return_value
    
    # Use real dict for final_order to avoid MagicMock comparison issues in guardrails
    final_order_dict = {
        "action": "BUY",
        "entry_price": 65000.0,
        "sl_price": 64500.0,
        "tp_price": 66500.0,
        "reasoning": "test"
    }
    
    mock_graph.return_value.stream.return_value = [
        {"node": {
            "final_order": final_order_dict, 
            "account_info": {"balance": 10000.0},
            "indicator_data": {},
            "strategy_hypothesis": {}
        }}
    ]
    
    # Mock validate_strategy_setup to ensure it doesn't block the path
    with patch("backend.services.trading_service.validate_strategy_setup", return_value=(True, "Success")):
        # Test Case A: Live Failure (ticket=0)
        failed_result = OrderResult(
            success=False,
            ticket=0,
            executed_price=0.0,
            failure_reason="Invalid ticket",
            timestamp="2026-05-03T00:00:00",
            mode="live",
            raw_response={"retcode": 10009, "order": 0, "price": 0.0}
        )
        mock_usecase.execute_trade.return_value = failed_result
        
        await run_trading_workflow_async("BTCUSD", mode="live")
        
        # Verify order_failed was called
        event_names = [call.args[2] for call in mock_event.call_args_list]
        assert "order_failed" in event_names
        
        # Verify track_open_position was NOT called
        mock_track.assert_not_called()
        
        # Verify trigger status set to failed
        status_updates = [call.args[2].get("status") for call in mock_update.call_args_list if call.args[2].get("status")]
        assert "failed" in status_updates

        # Reset for next test
        mock_track.reset_mock()
        mock_event.reset_mock()
        mock_update.reset_mock()
        mock_snapshot.reset_mock()

        # Test Case B: Live Success
        success_result = OrderResult(
            success=True,
            ticket=12345,
            executed_price=65000.0,
            timestamp="2026-05-03T00:00:00",
            mode="live",
            raw_response={"retcode": 10009, "order": 12345, "price": 65000.0}
        )
        mock_usecase.execute_trade.return_value = success_result
        
        await run_trading_workflow_async("BTCUSD", mode="live")
        
        # Verify order_acked was called
        event_names = [call.args[2] for call in mock_event.call_args_list]
        assert "order_acked" in event_names
        
        # Verify track_open_position WAS called
        mock_track.assert_called_once()
        
        # Verify trigger status set to success
        status_updates = [call.args[2].get("status") for call in mock_update.call_args_list if call.args[2].get("status")]
        assert "success" in status_updates
        
        # Verify snapshot contains execution_details
        snapshot_call = mock_snapshot.call_args
        snapshot_data = snapshot_call.args[2]
        assert "guardrail_result" in snapshot_data
