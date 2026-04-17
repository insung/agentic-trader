from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import uvicorn
import sys
import platform
from backend.workflows.graph import get_compiled_graph

class HealthResponse(BaseModel):
    status: str
    message: str
    python_version: str
    system: str

class TriggerRequest(BaseModel):
    symbol: str = "EURUSD"

class TriggerResponse(BaseModel):
    status: str
    message: str
    symbol: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting up Agentic Trader Backend...")
    # TODO: MT5 연결 초기화 로직 (backend.services.mt5_client.init_mt5_connection)
    yield
    print("💤 Shutting down Agentic Trader Backend...")
    # TODO: MT5 연결 안전하게 종료 (mt5.shutdown)

app = FastAPI(
    title="Agentic Trader API", 
    description="FastAPI Backend & LangGraph Orchestrator MVP",
    version="0.1.0",
    lifespan=lifespan
)

@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    """서버와 시스템 상태를 확인하는 가장 기초적인 헬스 체크 엔드포인트"""
    return HealthResponse(
        status="ok",
        message="Backend is running normally.",
        python_version=sys.version.split(" ")[0],
        system=platform.system()
    )

from backend.core.guardrails import (
    validate_risk_reward_ratio, 
    enforce_one_percent_rule,
    validate_daily_drawdown_lock,
    validate_max_trades_per_day
)
from backend.services.mt5_client import execute_mock_order, send_market_order

def run_trading_workflow(symbol: str):
    """
    백그라운드에서 실행될 트레이딩 워크플로우 함수
    """
    try:
        print(f"🚀 Starting trading workflow for {symbol}")
        graph = get_compiled_graph()
        initial_state = {"symbol": symbol, "timeframe": "M15"}
        
        final_state = initial_state.copy()
        
        # Stream the graph execution
        for s in graph.stream(initial_state):
            print(f"--- Node Executed: {list(s.keys())[0]} ---")
            final_state.update(list(s.values())[0])
            
        print(f"✅ Trading workflow for {symbol} completed successfully.")
        
        # --- EXECUTION INTERCEPTOR ---
        if final_state.get("error_flag"):
            print("❌ Workflow failed due to LLM errors. Aborting execution.")
            return

        final_order = final_state.get("final_order")
        if not final_order:
            print("⚠️ No final order found in state.")
            return
            
        action = final_order.get("action", "HOLD")
        if action.upper() == "HOLD" or action.upper() == "WAIT":
            print(f"🛑 Chief Trader decided to {action}. No order sent.")
            return
            
        sl = final_order.get("sl", 0.0)
        tp = final_order.get("tp", 0.0)
        
        account_balance = final_state.get("account_info", {}).get("balance", 10000.0)
        entry_price = 1.055 # Mock entry price, should fetch from data
        current_loss_pct = 0.0
        today_trade_count = 0
        
        if not validate_daily_drawdown_lock(current_loss_pct): return
        if not validate_max_trades_per_day(today_trade_count): return
        if not validate_risk_reward_ratio(entry_price, sl, tp): return
            
        safe_lot_size = enforce_one_percent_rule(account_balance, entry_price, sl)
        if safe_lot_size <= 0: return
            
        print(f"🔥 Executing order: {action} {symbol} | Lot: {safe_lot_size} | SL: {sl} | TP: {tp}")
        execute_mock_order(symbol, action, safe_lot_size, sl, tp, entry_price)
        
    except Exception as e:
        print(f"❌ Error in trading workflow for {symbol}: {e}")

@app.post("/api/v1/trade/trigger", response_model=TriggerResponse)
async def trigger_trading_workflow(request: TriggerRequest, background_tasks: BackgroundTasks):
    """
    트레이딩 파이프라인(LangGraph)의 1회 실행을 트리거합니다.
    """
    # Background task로 실행하여 API 응답 지연 방지
    background_tasks.add_task(run_trading_workflow, request.symbol)
    
    return TriggerResponse(
        status="processing",
        message="Trading workflow triggered in background.",
        symbol=request.symbol
    )

if __name__ == "__main__":
    # Wine 환경 터미널에서 `wine python backend/main.py` 로 직접 실행할 때 쓰입니다.
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
