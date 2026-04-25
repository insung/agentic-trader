"""
MetaTrader 5 (MT5) API 연동 래퍼(Wrapper) 모듈
오직 이 모듈을 통해서만 MT5 데스크톱 터미널과 IPC 통신을 수행합니다.
"""
import os
import pandas as pd
from dotenv import load_dotenv

# 주의: 이 라이브러리는 Windows(Wine) 환경에서만 정상 임포트됩니다.
try:
    import MetaTrader5 as mt5 
except ImportError:
    print("Warning: MetaTrader5 package not found. This is expected in non-Windows (or non-Wine) environments.")
    mt5 = None

load_dotenv()

# 지원 종목 목록
SUPPORTED_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
    "XAUUSD", "BTCUSD", "US100",
]


def is_mt5_available() -> bool:
    """MT5 라이브러리가 로드되어 사용 가능한지 확인합니다."""
    return mt5 is not None


def init_mt5_connection() -> bool:
    """MT5 터미널과 IPC 통신을 초기화합니다. .env의 계정 정보로 자동 로그인합니다."""
    if mt5 is None:
        print("❌ MT5 library is not loaded. Run this server with Wine Python.")
        return False
        
    # .env 파일에서 MT5 설정 동적 로드
    mt5_path = os.environ.get("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")
    mt5_login = os.environ.get("MT5_LOGIN")
    mt5_password = os.environ.get("MT5_PASSWORD")
    mt5_server = os.environ.get("MT5_SERVER")
    
    # 계정 정보가 있으면 자동 로그인 시도
    init_kwargs = {"path": mt5_path}
    if mt5_login and mt5_password and mt5_server:
        init_kwargs["login"] = int(mt5_login)
        init_kwargs["password"] = mt5_password
        init_kwargs["server"] = mt5_server
    
    if not mt5.initialize(**init_kwargs):
        error = mt5.last_error()
        print(f"❌ MT5 initialize() failed. Error: {error}")
        print(f"   Path: {mt5_path}")
        if mt5_login:
            print(f"   Login: {mt5_login}, Server: {mt5_server}")
        return False
    
    print(f"✅ MT5 initialized. Path: {mt5_path}")
    
    # 로그인 상태 확인
    account = mt5.account_info()
    if account:
        print(f"✅ Logged in: {account.login} @ {account.server}")
        print(f"   Balance: {account.balance}, Leverage: 1:{account.leverage}")
    else:
        print("⚠️ MT5 initialized but no account logged in.")
    
    return True

def get_account_summary() -> dict:
    """현재 계좌의 잔고, 증거금, 레버리지 정보를 반환합니다."""
    if mt5 is None:
        print("⚠️ MT5 not available. Returning empty account info.")
        return {}
        
    account_info = mt5.account_info()
    if account_info is None:
        error = mt5.last_error()
        print(f"❌ Failed to get account info. Error: {error}")
        return {}
    return account_info._asdict()

def fetch_ohlcv(symbol: str, timeframe: int, count: int = 100) -> pd.DataFrame:
    """
    특정 심볼의 과거 캔들(OHLCV) 데이터를 조회하여 DataFrame으로 반환합니다.
    이 데이터는 향후 pandas-ta 지표 계산에 사용됩니다.
    """
    if mt5 is None:
        print(f"❌ MT5 not available. Cannot fetch OHLCV for {symbol}.")
        return pd.DataFrame()
    
    # 심볼이 마켓워치에 활성화되어 있는지 확인
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"❌ Symbol {symbol} not found. Enable it in MT5 Market Watch.")
        return pd.DataFrame()
    
    if not symbol_info.visible:
        if not mt5.symbol_select(symbol, True):
            print(f"❌ Failed to enable {symbol} in Market Watch.")
            return pd.DataFrame()
        
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None:
        error = mt5.last_error()
        print(f"❌ Failed to fetch rates for {symbol}. Error: {error}")
        return pd.DataFrame()
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def get_current_price(symbol: str) -> dict:
    """특정 심볼의 현재 Bid/Ask 가격을 반환합니다."""
    if mt5 is None:
        return {}
    
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"❌ Failed to get tick for {symbol}. Error: {mt5.last_error()}")
        return {}
    
    return {
        "bid": tick.bid,
        "ask": tick.ask,
        "last": tick.last,
        "time": tick.time,
    }

def send_market_order(symbol: str, action: str, lot_size: float, sl: float, tp: float) -> dict:
    """
    안전장치를 통과한 최종 시장가 주문(Buy/Sell)을 MT5로 전송합니다.
    (주의: 이 함수 호출 전 반드시 backend.core.guardrails 검증을 거쳐야 함)
    """
    if mt5 is None:
        return {}
        
    order_type = mt5.ORDER_TYPE_BUY if action.lower() == 'buy' else mt5.ORDER_TYPE_SELL
    
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"Failed to get tick info for {symbol}, error code: {mt5.last_error()}")
        return {}
        
    price = tick.ask if action.lower() == 'buy' else tick.bid
    
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

def execute_mock_order(symbol: str, action: str, lot_size: float, sl: float, tp: float, price: float = 0.0) -> dict:
    """
    모의 투자(Paper Trading)용 가상 주문 실행 함수.
    실제 MT5 API를 호출하지 않고, 주문 결과를 로깅 및 반환합니다.
    """
    print(f"[Paper Trading] Executing mock order:")
    print(f"  Action: {action}, Symbol: {symbol}")
    print(f"  Lot Size: {lot_size}, Price: {price}, SL: {sl}, TP: {tp}")
    
    # 가상의 체결 결과 반환
    mock_result = {
        "retcode": 10009, # TRADE_RETCODE_DONE
        "deal": 123456789,
        "order": 987654321,
        "volume": lot_size,
        "price": price,
        "bid": price,
        "ask": price,
        "comment": "Mock Paper Trading Order",
        "request_id": 1
    }
    print("[Paper Trading] Mock order executed successfully.")
    return mock_result

class MT5Client:
    """Class wrapper for MT5 interactions to support Dependency Injection."""
    def send_order(self, symbol: str, order_type: str, volume: float, price: float, sl: float, tp: float) -> dict:
        return send_market_order(symbol, order_type, volume, sl, tp)
