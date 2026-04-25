import pytest
from unittest.mock import patch, MagicMock
from backend.main import run_trading_workflow
from backend.features.trading.mt5_adapter import MT5Client

@patch('backend.main.get_compiled_graph')
@patch('backend.main.execute_mock_order')
@patch('backend.main.TradeExecutionUseCase')
def test_execution_interceptor(mock_usecase_class, mock_execute, mock_graph):
    mock_compiled = MagicMock()
    mock_compiled.stream.return_value = [
        {"chief_trader": {"final_order": {"action": "BUY", "sl": 1.05, "tp": 1.06, "reasoning": "Test"}}}
    ]
    mock_graph.return_value = mock_compiled
    
    mock_usecase_instance = MagicMock()
    mock_usecase_instance.execute_trade.return_value = {"success": True}
    mock_usecase_class.return_value = mock_usecase_instance
    
    run_trading_workflow("EURUSD")
    
    mock_usecase_instance.execute_trade.assert_called_once()
    mock_execute.assert_called_once_with("EURUSD", "BUY", 0.0, 1.05, 1.06, 1.055)
