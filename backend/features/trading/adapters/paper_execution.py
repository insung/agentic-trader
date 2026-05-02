"""Paper execution adapter functions."""


def execute_mock_order(symbol: str, action: str, lot_size: float, sl: float, tp: float, price: float = 0.0) -> dict:
    """모의 투자(Paper Trading)용 가상 주문 실행 함수."""
    print("[Paper Trading] Executing mock order:")
    print(f"  Action: {action}, Symbol: {symbol}")
    print(f"  Lot Size: {lot_size}, Price: {price}, SL: {sl}, TP: {tp}")

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
    }
    print("[Paper Trading] Mock order executed successfully.")
    return mock_result
