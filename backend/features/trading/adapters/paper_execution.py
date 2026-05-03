"""Paper execution adapter functions."""

import logging

logger = logging.getLogger(__name__)


def execute_mock_order(symbol: str, action: str, lot_size: float, sl: float, tp: float, price: float = 0.0) -> dict:
    """모의 투자(Paper Trading)용 가상 주문 실행 함수."""
    logger.info(
        "Executing PAPER mock order.",
        extra={
            "event": "trigger.execution.requested",
            "mode": "paper",
            "symbol": symbol,
            "final_action": action,
            "lot_size": lot_size,
        },
    )

    mock_result = {
        "retcode": 10009,
        "deal": 123456789,
        "order": 987654321,
        "volume": lot_size,
        "price": price,
        "bid": price,
        "ask": price,
        "comment": "Mock Paper Trading Order",
        "request_id": 1,
        "mode": "paper",
        "symbol": symbol,
        "action": action,
        "requested_entry_price": price,
        "requested_lot": lot_size,
        "requested_sl": sl,
        "requested_tp": tp,
        "safe_lot": lot_size,
        "success": True,
        "ticket": 987654321,
        "executed_price": price,
        "mt5_retcode": 10009,
        "mt5_comment": "Mock Paper Trading Order",
        "mt5_order": 987654321,
        "mt5_deal": 123456789,
        "mt5_price": price,
        "mt5_request_id": 1,
        "failure_reason": None,
    }
    # raw_response will be the dict itself when processed by services
    mock_result["raw_response"] = mock_result.copy()
    
    logger.info(
        "PAPER mock order executed successfully.",
        extra={
            "event": "trigger.execution.acked",
            "mode": "paper",
            "symbol": symbol,
            "final_action": action,
            "ticket": mock_result["ticket"],
        },
    )
    return mock_result
