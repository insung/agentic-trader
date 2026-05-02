"""
Market-hours policy.

Forex markets use the Sunday 22:00 UTC to Friday 22:00 UTC session.
Crypto symbols are treated as 24/7 unless a broker-specific policy is added.
"""
from datetime import datetime, timezone


CRYPTO_SYMBOLS = {"BTCUSD", "ETHUSD"}


def _asset_class(symbol: str = None) -> str:
    if symbol and symbol.upper() in CRYPTO_SYMBOLS:
        return "crypto"
    return "forex"


def is_market_open(now: datetime = None, symbol: str = None) -> bool:
    """
    현재 시장이 열려 있는지 확인합니다.

    Forex 시장 운영 시간:
    - 개장: 일요일 22:00 UTC (월요일 시드니 시장 개장)
    - 폐장: 금요일 22:00 UTC (금요일 뉴욕 시장 폐장)

    Args:
        now: 현재 시간 (기본값: UTC 기준 현재 시각). 테스트 시 주입 가능.

    Returns:
        True: 시장 열림, False: 시장 닫힘 (주말)
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if _asset_class(symbol) == "crypto":
        return True

    weekday = now.weekday()  # 0=Monday, 6=Sunday
    hour = now.hour

    # 금요일 22:00 UTC 이후 → 시장 닫힘
    if weekday == 4 and hour >= 22:
        return False

    # 토요일 전체 → 시장 닫힘
    if weekday == 5:
        return False

    # 일요일 22:00 UTC 이전 → 시장 닫힘
    if weekday == 6 and hour < 22:
        return False

    return True


def get_market_status_message(now: datetime = None, symbol: str = None) -> str:
    """
    현재 시장 상태를 사람이 읽을 수 있는 메시지로 반환합니다.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if _asset_class(symbol) == "crypto":
        return f"Crypto 시장 열림: 24/7 정책 적용 ({(symbol or 'crypto').upper()})"

    if is_market_open(now, symbol=symbol):
        return f"Forex 시장 열림 (현재: {now.strftime('%A %H:%M UTC')})"

    weekday = now.weekday()
    if weekday == 5:  # Saturday
        return "Forex 시장 닫힘: 주말 (토요일). 일요일 22:00 UTC에 개장합니다."
    elif weekday == 6:  # Sunday before 22:00
        return f"Forex 시장 닫힘: 주말 (일요일). 22:00 UTC에 개장합니다. (현재: {now.strftime('%H:%M UTC')})"
    else:  # Friday after 22:00
        return "Forex 시장 닫힘: 금요일 22:00 UTC 이후. 일요일 22:00 UTC에 개장합니다."
