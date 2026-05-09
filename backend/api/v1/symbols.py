from typing import List

from fastapi import APIRouter

from backend.features.trading.adapters.mt5_market_data import SUPPORTED_SYMBOLS
from backend.features.trading.schemas import SymbolInfo

router = APIRouter(prefix="/api/v1")


@router.get("/symbols", response_model=List[SymbolInfo])
async def list_symbols():
    """지원 종목 목록을 반환합니다."""
    descriptions = {
        "EURUSD": "Euro / US Dollar",
        "GBPUSD": "British Pound / US Dollar",
        "USDJPY": "US Dollar / Japanese Yen",
        "AUDUSD": "Australian Dollar / US Dollar",
        "XAUUSD": "Gold / US Dollar",
        "BTCUSD": "Bitcoin / US Dollar",
        "NAS100ft.r": "Nasdaq 100 Index",
    }
    return [
        SymbolInfo(symbol=s, description=descriptions.get(s, s))
        for s in SUPPORTED_SYMBOLS
    ]
