import json
from pathlib import Path
from typing import List

from fastapi import APIRouter

from backend.features.trading.schemas import StrategyInfo

router = APIRouter(prefix="/api/v1")


@router.get("/strategies", response_model=List[StrategyInfo])
async def list_strategies():
    """등록된 전략 목록을 반환합니다."""
    config_path = Path(__file__).resolve().parents[2] / "config" / "strategies_config.json"
    try:
        with config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)
        return [
            StrategyInfo(
                name=s["name"],
                description=s.get("description", ""),
                allowed_regimes=s.get("allowed_regimes", []),
            )
            for s in config.get("strategies", [])
        ]
    except Exception as e:
        print(f"Error reading strategies config: {e}")
        return []
