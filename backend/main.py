from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
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

    yield

    task = getattr(app.state, "position_reconcile_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

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
from backend.features.trading.guardrails import validate_order_prices
from backend.features.trading.strategy_validators import validate_strategy_setup

def _model_to_dict(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value

def run_trading_workflow(symbol: str, strategy_override: str = None, mode: str = "paper", timeframes: List[str] = None):
    """
    백그라운드에서 실행될 트레이딩 워크플로우 함수
    """
    try:
        mode = mode.lower()
        if timeframes is None:
            timeframes = ["M5"]
        print(f"🚀 Starting trading workflow for {symbol} (mode: {mode}, timeframes: {timeframes})")
        
        graph = get_compiled_graph()
        initial_state = {"symbol": symbol, "timeframes": timeframes}
        
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

        final_order = _model_to_dict(final_state.get("final_order"))
        if not final_order:
            print("⚠️ No final order found in state. (Possibly filtered by Tech Analyst)")
            return
            
        action = final_order.get("action", "HOLD")
        if action.upper() == "HOLD" or action.upper() == "WAIT":
            print(f"🛑 Chief Trader decided to {action}. No order sent.")
            return
            
        sl = final_order.get("sl_price", final_order.get("sl", 0.0))
        tp = final_order.get("tp_price", final_order.get("tp", 0.0))
        entry_price = final_order.get("entry_price", 0.0)
        
        account_balance = final_state.get("account_info", {}).get("balance", 10000.0)
        risk_per_trade_pct = float(os.environ.get("RISK_PER_TRADE_PCT", "0.005"))
        if not validate_order_prices(action, entry_price, sl, tp):
            print(
                f"⛔ Guardrail blocked order: invalid SL/TP direction or risk/reward "
                f"(action={action}, entry={entry_price}, sl={sl}, tp={tp})"
            )
            return
        setup_ok, setup_reason = validate_strategy_setup(
            action,
            entry_price,
            sl,
            final_state.get("strategy_hypothesis", {}),
            final_state.get("indicator_data", {}),
        )
        if not setup_ok:
            print(f"⛔ Strategy validator blocked order: {setup_reason}")
            return
        
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
                account_balance=account_balance,
                risk_per_trade_pct=risk_per_trade_pct,
            )
            print(f"🔥 LIVE Order Result: {result}")
            order_result = result.model_dump()
        else:
            # Paper Trading 모드
            from backend.features.trading.guardrails import enforce_one_percent_rule
            safe_lot = enforce_one_percent_rule(account_balance, entry_price, sl, risk_pct=risk_per_trade_pct)
            if safe_lot <= 0:
                print("⛔ Guardrail blocked paper order: lot size calculated to <= 0")
                return
            result = execute_mock_order(symbol, action, safe_lot, sl, tp, entry_price)
            order_result = {
                "success": result.get("retcode") == 10009,
                "ticket": result.get("order"),
                "executed_price": result.get("price"),
                "timestamp": result.get("time") or datetime.now().isoformat(),
            }

        if order_result.get("success"):
            lot_size = order.lot_size
            if mode != "live":
                lot_size = safe_lot
            tracked = track_open_position(
                mode=mode,
                symbol=symbol,
                action=action,
                entry_price=order_result.get("executed_price") or entry_price,
                sl=sl,
                tp=tp,
                lot_size=lot_size,
                order_result=order_result,
                decision_context=build_decision_context(final_state, order_result),
            )
            print(f"📌 Tracking open position until close: {tracked['trade_id']}")
        
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
        request.mode,
        request.timeframes
    )
    
    return TriggerResponse(
        status="processing",
        message="Trading workflow triggered in background.",
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
