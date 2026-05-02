from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.features.trading.schemas import ScheduleRuleRequest
from backend.features.trading.persistence.trigger_store import (
    delete_schedule_rule,
    get_trigger_events,
    get_trigger_history,
    get_trigger_run,
    get_trigger_snapshot,
    list_schedule_rules,
    set_schedule_rule_enabled,
    upsert_schedule_rule,
)

router = APIRouter(prefix="/api/v1/triggers")


@router.get("/history")
async def list_trigger_history(
    limit: int = 50,
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """최근 트리거 실행 이력을 반환합니다."""
    return get_trigger_history(
        limit=limit,
        status=status,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/rules")
async def list_trigger_rules():
    """등록된 스케줄 규칙 목록을 반환합니다."""
    return list_schedule_rules()


@router.post("/rules")
async def create_or_update_rule(request: ScheduleRuleRequest):
    """스케줄 규칙을 생성하거나 업데이트합니다."""
    rule_data = request.model_dump()
    rule_data["schedule_type"] = "interval"
    rule_id = upsert_schedule_rule(None, rule_data)
    return {"status": "ok", "rule_id": rule_id}


@router.post("/rules/{rule_id}/toggle")
async def toggle_rule(rule_id: str, enabled: bool):
    """스케줄 규칙의 활성화 상태를 전환합니다."""
    set_schedule_rule_enabled(rule_id=rule_id, enabled=enabled)
    return {"status": "ok", "rule_id": rule_id, "enabled": enabled}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    """스케줄 규칙을 삭제합니다."""
    delete_schedule_rule(rule_id=rule_id)
    return {"status": "ok", "rule_id": rule_id}


@router.get("/{trigger_id}")
async def get_trigger_details(trigger_id: str):
    """트리거 실행 상세 정보를 반환합니다."""
    run = get_trigger_run(trigger_id=trigger_id)
    if not run:
        raise HTTPException(status_code=404, detail="Trigger run not found")
    return run


@router.get("/{trigger_id}/events")
async def list_trigger_events(trigger_id: str):
    """트리거 실행 중 발생한 이벤트 목록을 반환합니다."""
    return get_trigger_events(trigger_id=trigger_id)


@router.get("/{trigger_id}/snapshot")
async def get_trigger_execution_snapshot(trigger_id: str):
    """트리거 실행 당시의 데이터 스냅샷을 반환합니다."""
    snapshot = get_trigger_snapshot(trigger_id=trigger_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found for this trigger")
    return snapshot
