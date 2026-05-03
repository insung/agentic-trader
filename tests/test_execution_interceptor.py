import pytest
from unittest.mock import patch, MagicMock
from backend.services.trading_service import run_trading_workflow

@patch('backend.services.trading_service.get_compiled_graph')
@patch('backend.services.trading_service.track_open_position')
@patch('backend.services.trading_service.execute_mock_order')
def test_execution_interceptor(mock_execute, mock_track, mock_graph):
    """Paper Trading 모드에서 execution interceptor가 정상 작동하는지 확인."""
    mock_compiled = MagicMock()
    mock_execute.return_value = {
        "retcode": 10009,
        "deal": 987654789,
        "order": 123,
        "volume": 0.1,
        "price": 1.0555,
        "bid": 1.0555,
        "ask": 1.0555,
        "comment": "Mock Paper Trading Order",
        "request_id": 1,
        "mode": "paper",
        "symbol": "EURUSD",
        "action": "BUY",
        "requested_entry_price": 1.055,
        "requested_lot": 0.1,
        "requested_sl": 1.045,
        "requested_tp": 1.075,
        "safe_lot": 0.1,
        "success": True,
        "ticket": 123,
        "executed_price": 1.0555,
        "mt5_retcode": 10009,
        "mt5_comment": "Mock Paper Trading Order",
        "mt5_order": 123,
        "mt5_deal": 987654789,
        "mt5_price": 1.0555,
        "mt5_request_id": 1,
        "failure_reason": None,
        "raw_response": {"retcode": 10009, "order": 123, "price": 1.0555},
    }
    indicator_data = {
        "M5": {
            "latest": {
                "close": 1.0555,
                "ema20": 1.05,
                "ema50": 1.04,
                "atr14": 0.005,
                "adx14": 30.0,
            },
            "ema_cross_age_bars": {"bullish": 2, "bearish": None},
            "recent_rows": [],
        }
    }
    mock_compiled.stream.return_value = [
        {"fetch_data": {"raw_data": "test", "account_info": {"balance": 10000.0}, "indicator_data": indicator_data, "error_flag": False}},
        {"strategist": {"strategy_hypothesis": {"selected_strategy": "Moving Average Crossover", "action": "BUY"}}},
        {"chief_trader": {"final_order": {"action": "BUY", "sl": 1.045, "tp": 1.075, "entry_price": 1.055, "reasoning": "Test"}, "error_flag": False}}
    ]
    mock_graph.return_value = mock_compiled
    
    run_trading_workflow("EURUSD", mode="paper")
    
    mock_execute.assert_called_once()
    call_args = mock_execute.call_args
    assert call_args[0][0] == "EURUSD"  # symbol
    assert call_args[0][1] == "BUY"  # action
    mock_track.assert_called_once()
    track_args = mock_track.call_args.kwargs
    order_result = track_args["order_result"]
    assert order_result["mode"] == "paper"
    assert order_result["symbol"] == "EURUSD"
    assert order_result["action"] == "BUY"
    assert order_result["ticket"] == 123
    assert order_result["executed_price"] == 1.0555
    assert order_result["requested_entry_price"] == 1.055
    assert "raw_response" in order_result
