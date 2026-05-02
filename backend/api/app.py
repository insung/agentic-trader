import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.api.v1.health import router as health_router
from backend.api.v1.strategies import router as strategies_router
from backend.api.v1.symbols import router as symbols_router
from backend.api.v1.trade import router as trade_router
from backend.api.v1.triggers import router as triggers_router
from backend.features.trading.adapters.mt5_connection import init_mt5_connection, shutdown_mt5_connection
from backend.features.trading.operations.position_tracker import reconcile_tracked_positions
from backend.features.trading.persistence.trigger_store import init_trigger_db
from backend.services.scheduler import scheduler

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
                print(f"Reviewed closed trades: {ids}")
        except Exception as e:
            print(f"Position reconcile loop failed: {e}")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up Agentic Trader Backend...")

    if init_mt5_connection():
        print("MT5 initialized successfully.")
    else:
        print("MT5 initialization failed. Server will run in limited mode.")

    app.state.position_reconcile_task = asyncio.create_task(_position_reconcile_loop())

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

    await scheduler.stop()

    print("Shutting down Agentic Trader Backend...")

    if shutdown_mt5_connection():
        print("MT5 shutdown successfully.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agentic Trader API",
        description="FastAPI Backend & LangGraph Orchestrator MVP",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(symbols_router)
    app.include_router(strategies_router)
    app.include_router(trade_router)
    app.include_router(triggers_router)
    return app
