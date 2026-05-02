"""MT5 account, position, and deal-history adapter functions."""
from datetime import datetime, timedelta

from backend.features.trading.adapters.mt5_connection import mt5


def get_account_summary() -> dict:
    """현재 계좌의 잔고, 증거금, 레버리지 정보를 반환합니다."""
    if mt5 is None:
        print("MT5 not available. Returning empty account info.")
        return {}

    account_info = mt5.account_info()
    if account_info is None:
        print(f"Failed to get account info. Error: {mt5.last_error()}")
        return {}
    return account_info._asdict()


def get_open_positions(symbol: str = None) -> list[dict]:
    """Return currently open MT5 positions as dictionaries."""
    if mt5 is None:
        return []

    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if positions is None:
        print(f"Failed to get open positions. Error: {mt5.last_error()}")
        return []

    return [position._asdict() for position in positions]


def get_deals_history(days: int = 14) -> list[dict]:
    """Return recent MT5 deal history as dictionaries."""
    if mt5 is None:
        return []

    date_to = datetime.now()
    date_from = date_to - timedelta(days=days)
    deals = mt5.history_deals_get(date_from, date_to)
    if deals is None:
        print(f"Failed to get deal history. Error: {mt5.last_error()}")
        return []

    return [deal._asdict() for deal in deals]
