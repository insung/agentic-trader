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

def run_trading_workflow(symbol: str):
    """
    백그라운드에서 실행될 트레이딩 워크플로우 함수
    """
    try:
        print(f"🚀 Starting trading workflow for {symbol}")
        graph = get_compiled_graph()
        initial_state = {"symbol": symbol}
        
        # Stream the graph execution
        for s in graph.stream(initial_state):
            print(f"--- Node Executed: {list(s.keys())[0]} ---")
        
        print(f"✅ Trading workflow for {symbol} completed successfully.")
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
