from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


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
    schedule_type: str = "interval"
    cron_expression: Optional[str] = None
    interval_seconds: Optional[int] = 900
    timezone: str = "UTC"
    market_hours_only: bool = True
    strategy_override: Optional[str] = None
    enabled: bool = True

    @field_validator("schedule_type")
    @classmethod
    def validate_schedule_type(cls, v):
        if v not in ["interval", "cron"]:
            raise ValueError("schedule_type must be 'interval' or 'cron'")
        return v

    @field_validator("interval_seconds")
    @classmethod
    def validate_interval(cls, v, info):
        if info.data.get("schedule_type") == "interval" and (v is None or v <= 0):
            raise ValueError("interval_seconds must be > 0 for interval type")
        return v

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v, info):
        if info.data.get("schedule_type") == "cron" and not v:
            raise ValueError("cron_expression is required for cron type")
        return v
