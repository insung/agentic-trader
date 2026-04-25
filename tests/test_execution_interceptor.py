import pytest
from unittest.mock import patch, MagicMock
from backend.main import run_trading_workflow

@patch('backend.main.get_compiled_graph')
@patch('backend.main.track_open_position')
@patch('backend.main.execute_mock_order')
@patch('backend.main.get_current_price', return_value={"bid": 1.055, "ask": 1.0555})
def test_execution_interceptor(mock_price, mock_execute, mock_track, mock_graph):
    """Paper Trading 모드에서 execution interceptor가 정상 작동하는지 확인."""
    mock_compiled = MagicMock()
    mock_compiled.stream.return_value = [
        {"fetch_data": {"raw_data": "test", "account_info": {"balance": 10000.0}, "error_flag": False}},
        {"chief_trader": {"final_order": {"action": "BUY", "sl": 1.05, "tp": 1.06, "entry_price": 1.055, "reasoning": "Test"}, "error_flag": False}}
    ]
    mock_graph.return_value = mock_compiled
    
    run_trading_workflow("EURUSD", mode="paper")
    
    mock_execute.assert_called_once()
    call_args = mock_execute.call_args
    assert call_args[0][0] == "EURUSD"  # symbol
    assert call_args[0][1] == "BUY"  # action
    mock_track.assert_called_once()
