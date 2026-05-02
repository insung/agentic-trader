import platform
import sys

from fastapi import APIRouter

from backend.features.trading.adapters.mt5_connection import is_mt5_available
from backend.features.trading.schemas import HealthResponse

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """서버와 시스템 상태를 확인하는 가장 기초적인 헬스 체크 엔드포인트"""
    return HealthResponse(
        status="ok",
        message="Backend is running normally.",
        python_version=sys.version.split(" ")[0],
        system=platform.system(),
        mt5_available=is_mt5_available(),
    )
