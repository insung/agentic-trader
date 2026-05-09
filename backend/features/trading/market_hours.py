"""Market-hours policy by asset class."""
from datetime import datetime, timezone


CRYPTO_SYMBOLS = {"BTCUSD", "ETHUSD"}
INDEX_KEYWORDS = ("NAS", "US100", "USTEC", "SPX", "US500", "DJ", "US30", "GER", "DAX", "UK100")
METAL_SYMBOLS = {"XAUUSD", "XAGUSD"}
COMMODITY_KEYWORDS = ("WTI", "BRENT", "OIL", "NGAS")


def get_asset_class(symbol: str = None) -> str:
    """Return the broad market-hours policy bucket for a broker symbol."""
    if not symbol:
        return "forex"

    normalized = symbol.upper()
    base = normalized.split(".")[0]

    if normalized in CRYPTO_SYMBOLS or base in CRYPTO_SYMBOLS:
        return "crypto"
    if base in METAL_SYMBOLS:
        return "metal"
    if any(keyword in normalized for keyword in INDEX_KEYWORDS):
        return "index"
    if any(keyword in normalized for keyword in COMMODITY_KEYWORDS):
        return "commodity"
    return "forex"


def _is_weekday_session_open(now: datetime) -> bool:
    """Shared weekend policy: Sunday 22:00 UTC through Friday before 22:00 UTC."""
    weekday = now.weekday()
    hour = now.hour

    if weekday == 4 and hour >= 22:
        return False
    if weekday == 5:
        return False
    if weekday == 6 and hour < 22:
        return False
    return True


def is_market_open(now: datetime = None, symbol: str = None) -> bool:
    """Return whether the symbol's broad asset-class session is open."""
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    asset_class = get_asset_class(symbol)
    if asset_class == "crypto":
        return True

    return _is_weekday_session_open(now)


def get_market_status_message(now: datetime = None, symbol: str = None) -> str:
    """
    현재 시장 상태를 사람이 읽을 수 있는 메시지로 반환합니다.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    asset_class = get_asset_class(symbol)
    if asset_class == "crypto":
        return f"Crypto 시장 열림: 24/7 정책 적용 ({(symbol or 'crypto').upper()})"

    if is_market_open(now, symbol=symbol):
        return f"{asset_class.upper()} 시장 열림 (현재: {now.strftime('%A %H:%M UTC')})"

    weekday = now.weekday()
    if weekday == 5:  # Saturday
        return f"{asset_class.upper()} 시장 닫힘: 주말 (토요일). 일요일 22:00 UTC에 개장합니다."
    elif weekday == 6:  # Sunday before 22:00
        return f"{asset_class.upper()} 시장 닫힘: 주말 (일요일). 22:00 UTC에 개장합니다. (현재: {now.strftime('%H:%M UTC')})"
    else:  # Friday after 22:00
        return f"{asset_class.upper()} 시장 닫힘: 금요일 22:00 UTC 이후. 일요일 22:00 UTC에 개장합니다."
