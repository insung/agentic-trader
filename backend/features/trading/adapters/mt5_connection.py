"""MetaTrader 5 connection lifecycle helpers."""
import os

from dotenv import load_dotenv

try:
    import MetaTrader5 as mt5
except ImportError:
    print("Warning: MetaTrader5 package not found. This is expected in non-Windows (or non-Wine) environments.")
    mt5 = None

load_dotenv()


def is_mt5_available() -> bool:
    """MT5 라이브러리가 로드되어 사용 가능한지 확인합니다."""
    return mt5 is not None


def init_mt5_connection() -> bool:
    """MT5 터미널과 IPC 통신을 초기화합니다. .env의 계정 정보로 자동 로그인합니다."""
    if mt5 is None:
        print("MT5 library is not loaded. Run this server with Wine Python.")
        return False

    mt5_path = os.environ.get("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")
    mt5_login = os.environ.get("MT5_LOGIN")
    mt5_password = os.environ.get("MT5_PASSWORD")
    mt5_server = os.environ.get("MT5_SERVER")

    init_kwargs = {"path": mt5_path}
    if mt5_login and mt5_password and mt5_server:
        init_kwargs["login"] = int(mt5_login)
        init_kwargs["password"] = mt5_password
        init_kwargs["server"] = mt5_server

    if not mt5.initialize(**init_kwargs):
        error = mt5.last_error()
        print(f"MT5 initialize() failed. Error: {error}")
        print(f"   Path: {mt5_path}")
        if mt5_login:
            print(f"   Login: {mt5_login}, Server: {mt5_server}")
        return False

    print(f"MT5 initialized. Path: {mt5_path}")

    account = mt5.account_info()
    if account:
        print(f"Logged in: {account.login} @ {account.server}")
        print(f"   Balance: {account.balance}, Leverage: 1:{account.leverage}")
    else:
        print("MT5 initialized but no account logged in.")

    return True


def shutdown_mt5_connection() -> bool:
    if mt5 is not None:
        mt5.shutdown()
        return True
    return False
