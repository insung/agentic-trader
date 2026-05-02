from fastapi import APIRouter, BackgroundTasks

from backend.features.trading.operations.position_tracker import reconcile_tracked_positions
from backend.features.trading.schemas import (
    ReconcileResponse,
    TriggerRequest,
    TriggerResponse,
)
from backend.services.trading_service import run_trading_workflow_async

router = APIRouter(prefix="/api/v1")


@router.post("/trade/trigger", response_model=TriggerResponse)
async def trigger_trading_workflow(
    request: TriggerRequest,
    background_tasks: BackgroundTasks,
):
    """
    트레이딩 파이프라인(LangGraph)의 1회 실행을 트리거합니다.
    """
    background_tasks.add_task(
        run_trading_workflow_async,
        symbol=request.symbol,
        timeframes=request.timeframes,
        mode=request.mode,
        strategy_override=request.strategy_override,
    )

    return TriggerResponse(
        status="processing",
        message="Trading workflow triggered in background with logging.",
        symbol=request.symbol,
        mode=request.mode,
    )


@router.post("/trade/reconcile", response_model=ReconcileResponse)
async def reconcile_trades():
    """수동으로 추적 중인 포지션의 청산 여부를 확인하고 복기를 생성합니다."""
    reviewed = reconcile_tracked_positions()
    return ReconcileResponse(
        status="ok",
        reviewed_count=len(reviewed),
        reviewed_trade_ids=[item["trade_id"] for item in reviewed],
    )
