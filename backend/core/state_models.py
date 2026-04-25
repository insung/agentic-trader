from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from enum import Enum

class OrderAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class Order(BaseModel):
    action: OrderAction = Field(description="The action to take: BUY, SELL, or HOLD")
    symbol: str = Field(description="The trading symbol, e.g., BTCUSD")
    entry_price: float = Field(0.0, description="The intended entry price, or 0 for market execution")
    sl_price: float = Field(description="Stop loss price")
    tp_price: float = Field(description="Take profit price")
    lot_size: float = Field(0.0, description="Lot size, will be overwritten by guardrails")
    reasoning: str = Field("", description="AI's reasoning for this order")

class Position(BaseModel):
    ticket: int
    symbol: str
    type: str # 0 for BUY, 1 for SELL in MT5 usually
    volume: float
    price_open: float
    sl: float
    tp: float
    profit: float

class OrderResult(BaseModel):
    success: bool
    ticket: Optional[int] = None
    executed_price: Optional[float] = None
    error_message: Optional[str] = None
    timestamp: str

class AgentStateSchema(BaseModel):
    """
    Pydantic schema representing the complete State for LangGraph.
    By using a Pydantic BaseModel, we ensure type safety and easy OpenAPI generation.
    """
    # Meta Context
    symbol: str = ""
    timeframes: List[str] = Field(default_factory=lambda: ["M5"])
    error_flag: bool = False
    error_message: str = ""
    
    # Node 1: Fetch Data
    raw_data: str = ""
    account_info: Dict[str, Any] = Field(default_factory=dict)
    open_positions: List[Position] = Field(default_factory=list)
    
    # Node 2: Tech Analyst
    tech_summary: Dict[str, Any] = Field(default_factory=dict)
    
    # Node 3: Strategist
    strategy_hypothesis: Dict[str, Any] = Field(default_factory=dict)
    
    # Node 4: Chief Trader
    final_order: Optional[Order] = None
    
    # Node 4.5: Execute Order
    order_result: Optional[OrderResult] = None
    
    # Node 5: Risk Reviewer
    review_log: Dict[str, Any] = Field(default_factory=dict)
