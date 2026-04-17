from backend.main import run_trading_workflow
from unittest.mock import patch, MagicMock

@patch('backend.main.get_compiled_graph')
@patch('backend.main.execute_mock_order')
@patch('backend.main.enforce_one_percent_rule')
@patch('backend.main.validate_risk_reward_ratio')
def test_execution_interceptor(mock_rr, mock_one_percent, mock_execute, mock_graph):
    mock_compiled = MagicMock()
    mock_compiled.stream.return_value = [
        {"chief_trader": {"final_order": {"action": "BUY", "sl": 1.05, "tp": 1.06, "final_reasoning": "Test"}}}
    ]
    mock_graph.return_value = mock_compiled
    
    mock_rr.return_value = True
    mock_one_percent.return_value = 0.1
    
    run_trading_workflow("EURUSD")
    
    mock_rr.assert_called_once()
    mock_one_percent.assert_called_once()
    mock_execute.assert_called_once_with("EURUSD", "BUY", 0.1, 1.05, 1.06, 1.055)
