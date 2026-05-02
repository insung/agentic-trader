"""MT5 live execution adapter functions."""
from backend.features.trading.adapters.mt5_connection import mt5


def send_market_order(symbol: str, action: str, lot_size: float, sl: float, tp: float) -> dict:
    """
    안전장치를 통과한 최종 시장가 주문(Buy/Sell)을 MT5로 전송합니다.
    이 함수 호출 전 반드시 Python guardrail 검증을 거쳐야 합니다.
    """
    if mt5 is None:
        return {}

    order_type = mt5.ORDER_TYPE_BUY if action.lower() == "buy" else mt5.ORDER_TYPE_SELL

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"Failed to get tick info for {symbol}, error code: {mt5.last_error()}")
        return {}

    price = tick.ask if action.lower() == "buy" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot_size),
        "type": order_type,
        "price": price,
        "sl": float(sl),
        "tp": float(tp),
        "deviation": 20,
        "magic": 100000,
        "comment": "python script open",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        print(f"order_send failed, error code: {mt5.last_error()}")
        return {}

    return result._asdict()


class MT5Client:
    """Class wrapper for MT5 interactions to support Dependency Injection."""

    def send_order(self, symbol: str, order_type: str, volume: float, price: float, sl: float, tp: float) -> dict:
        return send_market_order(symbol, order_type, volume, sl, tp)
