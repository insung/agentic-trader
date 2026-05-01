from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import asyncio
import os
from datetime import datetime
import uvicorn
import sys
import platform
import json
from backend.workflows.graph import get_compiled_graph

class HealthResponse(BaseModel):
    status: str
    message: str
    python_version: str
    system: str
    mt5_available: bool

class TriggerRequest(BaseModel):
    symbol: str = "EURUSD"
    timeframes: List[str] = ["M5"]
    strategy_override: Optional[str] = None
    mode: str = "paper"  # "paper" or "live"

class TriggerResponse(BaseModel):
    status: str
    message: str
    symbol: str
    mode: str

class ReconcileResponse(BaseModel):
    status: str
    reviewed_count: int
    reviewed_trade_ids: List[str]

class SymbolInfo(BaseModel):
    symbol: str
    description: str

class StrategyInfo(BaseModel):
    name: str
    description: str
    allowed_regimes: List[str]

# 1. MT5 모듈 임포트 및 예외 처리 (Wine 환경 고려)
try:
    import MetaTrader5 as mt5
except ImportError:
    print("Warning: MetaTrader5 package not found. (Expected in non-Wine environments)")
    mt5 = None

from backend.features.trading.mt5_adapter import init_mt5_connection, is_mt5_available, SUPPORTED_SYMBOLS
from backend.features.trading.position_tracker import (
    build_decision_context,
    reconcile_tracked_positions,
    track_open_position,
)
from backend.services.scheduler import scheduler
from backend.features.trading.trigger_store import (
    get_trigger_history,
    get_trigger_run,
    get_trigger_events,
    get_trigger_snapshot,
    get_active_schedule_rules,
    upsert_schedule_rule,
    init_trigger_db,
    update_trigger_run,
    add_trigger_event,
)
from backend.services.trading_service import run_trading_workflow_async, run_trading_workflow

async def _position_reconcile_loop():
    try:
        interval = int(os.environ.get("POSITION_RECONCILE_INTERVAL_SECONDS", "30"))
    except ValueError:
        interval = 30
    interval = max(interval, 1)
    while True:
        try:
            reviewed = reconcile_tracked_positions()
            if reviewed:
                ids = [item["trade_id"] for item in reviewed]
                print(f"🧾 Reviewed closed trades: {ids}")
        except Exception as e:
            print(f"❌ Position reconcile loop failed: {e}")
        await asyncio.sleep(interval)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting up Agentic Trader Backend...")
    
    # 2. Startup 로직: MT5 연결 초기화
    if init_mt5_connection():
        print("✅ MT5 initialized successfully.")
    else:
        print("⚠️ MT5 initialization failed. Server will run in limited mode.")

    app.state.position_reconcile_task = asyncio.create_task(_position_reconcile_loop())

    # 3. Start Trigger Scheduler
    init_trigger_db()
    await scheduler.start()

    yield

    task = getattr(app.state, "position_reconcile_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # 4. Stop Trigger Scheduler
    await scheduler.stop()

    print("💤 Shutting down Agentic Trader Backend...")
    
    # 3. Shutdown 로직: MT5 연결 안전 종료
    if mt5 is not None:
        mt5.shutdown()
        print("✅ MT5 shutdown successfully.")

app = FastAPI(
    title="Agentic Trader API", 
    description="FastAPI Backend & LangGraph Orchestrator MVP",
    version="0.2.0",
    lifespan=lifespan
)

@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    """서버와 시스템 상태를 확인하는 가장 기초적인 헬스 체크 엔드포인트"""
    return HealthResponse(
        status="ok",
        message="Backend is running normally.",
        python_version=sys.version.split(" ")[0],
        system=platform.system(),
        mt5_available=is_mt5_available()
    )

@app.get("/api/v1/symbols", response_model=List[SymbolInfo])
async def list_symbols():
    """지원 종목 목록을 반환합니다."""
    descriptions = {
        "EURUSD": "Euro / US Dollar",
        "GBPUSD": "British Pound / US Dollar",
        "USDJPY": "US Dollar / Japanese Yen",
        "AUDUSD": "Australian Dollar / US Dollar",
        "XAUUSD": "Gold / US Dollar",
        "BTCUSD": "Bitcoin / US Dollar",
        "US100": "Nasdaq 100 Index",
    }
    return [
        SymbolInfo(symbol=s, description=descriptions.get(s, s))
        for s in SUPPORTED_SYMBOLS
    ]

@app.get("/api/v1/strategies", response_model=List[StrategyInfo])
async def list_strategies():
    """등록된 전략 목록을 반환합니다."""
    import os
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config", "strategies_config.json"
    )
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return [
            StrategyInfo(
                name=s["name"],
                description=s.get("description", ""),
                allowed_regimes=s.get("allowed_regimes", [])
            )
            for s in config.get("strategies", [])
        ]
    except Exception as e:
        print(f"Error reading strategies config: {e}")
        return []

# --- Trigger Management Endpoints ---

class ScheduleRuleRequest(BaseModel):
    name: str
    symbol: str
    timeframes: List[str]
    mode: str = "paper"
    interval_seconds: int = 900
    strategy_override: Optional[str] = None
    enabled: bool = True

@app.get("/api/v1/triggers/history")
async def list_trigger_history(
    limit: int = 50, 
    status: Optional[str] = None, 
    symbol: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """최근 트리거 실행 이력을 반환합니다."""
    return get_trigger_history(
        limit=limit, 
        status=status, 
        symbol=symbol,
        start_date=start_date,
        end_date=end_date
    )

@app.get("/api/v1/triggers/{trigger_id}")
async def get_trigger_details(trigger_id: str):
    """트리거 실행 상세 정보를 반환합니다."""
    run = get_trigger_run(trigger_id=trigger_id)
    if not run:
        raise HTTPException(status_code=404, detail="Trigger run not found")
    return run

@app.get("/api/v1/triggers/{trigger_id}/events")
async def list_trigger_events(trigger_id: str):
    """트리거 실행 중 발생한 이벤트 목록을 반환합니다."""
    return get_trigger_events(trigger_id=trigger_id)

@app.get("/api/v1/triggers/{trigger_id}/snapshot")
async def get_trigger_execution_snapshot(trigger_id: str):
    """트리거 실행 당시의 데이터 스냅샷을 반환합니다."""
    snapshot = get_trigger_snapshot(trigger_id=trigger_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found for this trigger")
    return snapshot

@app.get("/api/v1/triggers/rules")
async def list_trigger_rules():
    """등록된 스케줄 규칙 목록을 반환합니다."""
    # Note: we use get_active_schedule_rules but for management we might want all.
    # For now just using the store directly or extending it.
    from backend.features.trading.trigger_store import _connect, DEFAULT_TRIGGER_DB_PATH
    import sqlite3
    with _connect(DEFAULT_TRIGGER_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM trigger_schedule_rules")
        return [dict(row) for row in cursor.fetchall()]

@app.post("/api/v1/triggers/rules")
async def create_or_update_rule(request: ScheduleRuleRequest):
    """스케줄 규칙을 생성하거나 업데이트합니다."""
    rule_data = request.model_dump()
    rule_data["schedule_type"] = "interval"
    from backend.features.trading.trigger_store import DEFAULT_TRIGGER_DB_PATH
    rule_id = upsert_schedule_rule(DEFAULT_TRIGGER_DB_PATH, rule_data)
    return {"status": "ok", "rule_id": rule_id}

@app.post("/api/v1/triggers/rules/{rule_id}/toggle")
async def toggle_rule(rule_id: str, enabled: bool):
    """스케줄 규칙의 활성화 상태를 전환합니다."""
    from backend.features.trading.trigger_store import _connect, DEFAULT_TRIGGER_DB_PATH
    with _connect(DEFAULT_TRIGGER_DB_PATH) as conn:
        conn.execute("UPDATE trigger_schedule_rules SET enabled = ?, updated_at = datetime('now') WHERE rule_id = ?", (1 if enabled else 0, rule_id))
        conn.commit()
    return {"status": "ok", "rule_id": rule_id, "enabled": enabled}

@app.delete("/api/v1/triggers/rules/{rule_id}")
async def delete_rule(rule_id: str):
    """스케줄 규칙을 삭제합니다."""
    from backend.features.trading.trigger_store import _connect, DEFAULT_TRIGGER_DB_PATH
    with _connect(DEFAULT_TRIGGER_DB_PATH) as conn:
        conn.execute("DELETE FROM trigger_schedule_rules WHERE rule_id = ?", (rule_id,))
        conn.commit()
    return {"status": "ok", "rule_id": rule_id}

from backend.features.trading.mt5_adapter import MT5Client, execute_mock_order, send_market_order, get_current_price
from backend.core.state_models import Order, OrderAction
from backend.features.trading.market_hours import is_market_open, get_market_status_message
from backend.features.trading.guardrails import validate_order_prices
from backend.features.trading.strategy_validators import validate_strategy_setup

@app.post("/api/v1/trade/trigger", response_model=TriggerResponse)
async def trigger_trading_workflow(request: TriggerRequest, background_tasks: BackgroundTasks):
    """
    트레이딩 파이프라인(LangGraph)의 1회 실행을 트리거합니다.
    """
    # Use the new async workflow from trading_service
    background_tasks.add_task(
        run_trading_workflow_async,
        symbol=request.symbol,
        timeframes=request.timeframes,
        mode=request.mode,
        strategy_override=request.strategy_override
    )
    
    return TriggerResponse(
        status="processing",
        message="Trading workflow triggered in background with logging.",
        symbol=request.symbol,
        mode=request.mode
    )

@app.post("/api/v1/trade/reconcile", response_model=ReconcileResponse)
async def reconcile_trades():
    """수동으로 추적 중인 포지션의 청산 여부를 확인하고 복기를 생성합니다."""
    reviewed = reconcile_tracked_positions()
    return ReconcileResponse(
        status="ok",
        reviewed_count=len(reviewed),
        reviewed_trade_ids=[item["trade_id"] for item in reviewed],
    )

if __name__ == "__main__":
    # Wine 환경 터미널에서 `wine python backend/main.py` 로 직접 실행할 때 쓰입니다.
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8001, reload=True)
