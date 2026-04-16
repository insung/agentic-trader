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

def init_mt5_connection() -> bool:
    """MT5 터미널과 IPC 통신을 초기화합니다."""
    if mt5 is None:
        print("MT5 library is not loaded.")
        return False
        
    # .env 파일에서 MT5 실행 파일 경로 동적 로드 (Wine 환경 기본값 제공)
    mt5_path = os.environ.get("MT5_PATH", "C:\\Program Files\\MetaTrader 5\\terminal64.exe")
    
    if not mt5.initialize(path=mt5_path):
        print(f"MT5 initialize() failed with path '{mt5_path}', error code: {mt5.last_error()}")
        return False
    return True

def get_account_summary() -> dict:
    """현재 계좌의 잔고, 증거금, 레버리지 정보를 반환합니다."""
    if mt5 is None:
        return {}
        
    account_info = mt5.account_info()
    if account_info is None:
        print(f"Failed to get account info, error code: {mt5.last_error()}")
        return {}
    return account_info._asdict()

def fetch_ohlcv(symbol: str, timeframe: int, count: int = 100) -> pd.DataFrame:
    """
    특정 심볼의 과거 캔들(OHLCV) 데이터를 조회하여 DataFrame으로 반환합니다.
    이 데이터는 향후 pandas-ta 지표 계산에 사용됩니다.
    """
    if mt5 is None:
        return pd.DataFrame()
        
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None:
        print(f"Failed to fetch rates for {symbol}, error code: {mt5.last_error()}")
        return pd.DataFrame()
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

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
