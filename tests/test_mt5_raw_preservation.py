import json
import pytest
from unittest.mock import MagicMock
from backend.features.trading.adapters.mt5_execution import send_market_order, MT5Client
from backend.features.trading.usecase import TradeExecutionUseCase
from backend.core.state_models import Order, OrderAction

def test_mt5_adapter_none_response_preservation(monkeypatch):
    # Mock mt5 to simulate order_send returning None
    mock_mt5 = MagicMock()
    mock_mt5.symbol_info_tick.return_value = MagicMock(ask=65000.0, bid=64999.0)
    mock_mt5.order_send.return_value = None
    mock_mt5.last_error.return_value = 1234
    
    monkeypatch.setattr("backend.features.trading.adapters.mt5_execution.mt5", mock_mt5)
    
    result = send_market_order("BTCUSD", "buy", 0.01, 64500, 66500)
    
    assert result["retcode"] == -3
    assert "order_send returned None" in result["comment"]
    assert "1234" in result["comment"]
    assert result["order"] == 0

def test_usecase_preserves_raw_response():
    mock_client = MagicMock()
    raw_response = {
        "retcode": 10009,
        "order": 12345,
        "price": 65000.0,
        "comment": "Done",
        "some_extra_field": "val"
    }
    mock_client.send_order.return_value = raw_response
    
    usecase = TradeExecutionUseCase(mock_client)
    # Entry 65000, SL 64500 (500 loss), TP 66500 (1500 profit) -> RR 3.0
    order = Order(action=OrderAction.BUY, symbol="BTCUSD", entry_price=65000, sl_price=64500, tp_price=66500)
    
    result = usecase.execute_trade(order, 0.0, 0, 10000, 0.01)
    
    assert result.success is True
    assert result.raw_response == raw_response
    assert result.raw_response["some_extra_field"] == "val"
    # Ensure JSON serializable
    assert json.loads(json.dumps(result.model_dump()))["raw_response"] == raw_response

def test_usecase_preserves_failure_raw_response():
    mock_client = MagicMock()
    raw_response = {
        "retcode": 10013,
        "comment": "Invalid SL/TP",
        "order": 0
    }
    mock_client.send_order.return_value = raw_response
    
    usecase = TradeExecutionUseCase(mock_client)
    # Entry 65000, SL 64500 (500 loss), TP 66500 (1500 profit) -> RR 3.0
    order = Order(action=OrderAction.BUY, symbol="BTCUSD", entry_price=65000, sl_price=64500, tp_price=66500)
    
    result = usecase.execute_trade(order, 0.0, 0, 10000, 0.01)
    
    assert result.success is False
    assert result.raw_response == raw_response
    assert result.failure_reason is not None
    # Ensure JSON serializable
    dumped = json.loads(json.dumps(result.model_dump()))
    assert dumped["raw_response"] == raw_response
    assert dumped["success"] is False
