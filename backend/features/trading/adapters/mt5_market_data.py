"""MT5 market data adapter functions."""
import pandas as pd

from backend.features.trading.adapters.mt5_connection import mt5


SUPPORTED_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
    "XAUUSD", "BTCUSD", "US100",
]

TIMEFRAME_MAP = {
    "M1": 1, "1": 1,
    "M5": 5, "5": 5,
    "M15": 15, "15": 15,
    "M30": 30, "30": 30,
    "H1": 16385, "60": 16385,
    "H4": 16388, "240": 16388,
    "D1": 16408, "1440": 16408,
    "W1": 32769,
}


def fetch_ohlcv(symbol: str, timeframe_str: str, count: int = 100) -> pd.DataFrame:
    """특정 심볼의 과거 캔들(OHLCV) 데이터를 조회하여 DataFrame으로 반환합니다."""
    if mt5 is None:
        print(f"MT5 not available. Cannot fetch OHLCV for {symbol}.")
        return pd.DataFrame()

    tf = TIMEFRAME_MAP.get(timeframe_str.upper())
    if tf is None:
        print(f"지원하지 않는 타임프레임: {timeframe_str}")
        return pd.DataFrame()

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"Symbol {symbol} not found. Enable it in MT5 Market Watch.")
        return pd.DataFrame()

    if not symbol_info.visible:
        if not mt5.symbol_select(symbol, True):
            print(f"Failed to enable {symbol} in Market Watch.")
            return pd.DataFrame()

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None:
        print(f"Failed to fetch rates for {symbol}. Error: {mt5.last_error()}")
        return pd.DataFrame()

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def get_current_price(symbol: str) -> dict:
    """특정 심볼의 현재 Bid/Ask 가격을 반환합니다."""
    if mt5 is None:
        return {}

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"Failed to get tick for {symbol}. Error: {mt5.last_error()}")
        return {}

    return {
        "bid": tick.bid,
        "ask": tick.ask,
        "last": tick.last,
        "time": tick.time,
    }
