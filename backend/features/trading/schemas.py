from typing import List, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    message: str
    python_version: str
    system: str
    mt5_available: bool


class SymbolInfo(BaseModel):
    symbol: str
    description: str


class StrategyInfo(BaseModel):
    name: str
    description: str
    allowed_regimes: List[str]


class TriggerRequest(BaseModel):
    symbol: str = "EURUSD"
    timeframes: List[str] = Field(default_factory=lambda: ["M5"])
    strategy_override: Optional[str] = None
    mode: str = "paper"


class TriggerResponse(BaseModel):
    status: str
    message: str
    symbol: str
    mode: str


class ReconcileResponse(BaseModel):
    status: str
    reviewed_count: int
    reviewed_trade_ids: List[str]


class ScheduleRuleRequest(BaseModel):
    name: str
    symbol: str
    timeframes: List[str]
    mode: str = "paper"
    interval_seconds: int = 900
    strategy_override: Optional[str] = None
    enabled: bool = True
