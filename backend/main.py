from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
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
    strategy_override: Optional[str] = None
    mode: str = "paper"  # "paper" or "live"

class TriggerResponse(BaseModel):
    status: str
    message: str
    symbol: str
    mode: str

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting up Agentic Trader Backend...")
    
    # 2. Startup 로직: MT5 연결 초기화
    if init_mt5_connection():
        print("✅ MT5 initialized successfully.")
    else:
        print("⚠️ MT5 initialization failed. Server will run in limited mode.")
        
    yield
    
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

from backend.features.trading.mt5_adapter import MT5Client, execute_mock_order, send_market_order, get_current_price
from backend.core.state_models import Order, OrderAction
from backend.features.trading.market_hours import is_market_open, get_market_status_message

def run_trading_workflow(symbol: str, strategy_override: str = None, mode: str = "paper"):
    """
    백그라운드에서 실행될 트레이딩 워크플로우 함수
    """
    try:
        print(f"🚀 Starting trading workflow for {symbol} (mode: {mode})")
        
        graph = get_compiled_graph()
        initial_state = {"symbol": symbol, "timeframe": "M15"}
        
        final_state = initial_state.copy()
        
        # Stream the graph execution
        for s in graph.stream(initial_state):
            node_name = list(s.keys())[0]
            print(f"--- Node Executed: {node_name} ---")
            final_state.update(list(s.values())[0])
            
        print(f"✅ Trading workflow for {symbol} completed successfully.")
        
        # --- EXECUTION INTERCEPTOR ---
        if final_state.get("error_flag"):
            error_msg = final_state.get("error_message", "Unknown error")
            print(f"❌ Workflow ended with error: {error_msg}")
            return

        final_order = final_state.get("final_order")
        if not final_order:
            print("⚠️ No final order found in state. (Possibly filtered by Tech Analyst)")
            return
            
        action = final_order.get("action", "HOLD")
        if action.upper() == "HOLD" or action.upper() == "WAIT":
            print(f"🛑 Chief Trader decided to {action}. No order sent.")
            return
            
        sl = final_order.get("sl", 0.0)
        tp = final_order.get("tp", 0.0)
        entry_price = final_order.get("entry_price", 0.0)
        
        account_balance = final_state.get("account_info", {}).get("balance", 10000.0)
        
        order = Order(
            action=OrderAction(action.upper()),
            symbol=symbol,
            entry_price=entry_price,
            sl_price=sl,
            tp_price=tp,
            reasoning=final_order.get("reasoning", "")
        )
        
        if mode == "live":
            # 실전 모드: MT5로 실제 주문 전송
            from backend.features.trading.usecase import TradeExecutionUseCase
            usecase = TradeExecutionUseCase(MT5Client())
            result = usecase.execute_trade(
                order=order,
                current_loss_pct=0.0,
                today_trade_count=0,
                account_balance=account_balance
            )
            print(f"🔥 LIVE Order Result: {result}")
        else:
            # Paper Trading 모드
            from backend.features.trading.guardrails import enforce_one_percent_rule
            safe_lot = enforce_one_percent_rule(account_balance, entry_price, sl)
            execute_mock_order(symbol, action, safe_lot, sl, tp, entry_price)
        
    except Exception as e:
        print(f"❌ Error in trading workflow for {symbol}: {e}")
        import traceback
        traceback.print_exc()

@app.post("/api/v1/trade/trigger", response_model=TriggerResponse)
async def trigger_trading_workflow(request: TriggerRequest, background_tasks: BackgroundTasks):
    """
    트레이딩 파이프라인(LangGraph)의 1회 실행을 트리거합니다.
    """
    # Background task로 실행하여 API 응답 지연 방지
    background_tasks.add_task(
        run_trading_workflow, 
        request.symbol, 
        request.strategy_override, 
        request.mode
    )
    
    return TriggerResponse(
        status="processing",
        message="Trading workflow triggered in background.",
        symbol=request.symbol,
        mode=request.mode
    )

if __name__ == "__main__":
    # Wine 환경 터미널에서 `wine python backend/main.py` 로 직접 실행할 때 쓰입니다.
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8001, reload=True)
