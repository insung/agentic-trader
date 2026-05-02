"""Structured output schemas for LangGraph LLM nodes."""
from typing import List

from pydantic import BaseModel, Field


class TechSummary(BaseModel):
    trend: str = Field(description="bullish | bearish | neutral")
    market_regime: str = Field(description="One of: Bullish, Bearish, Ranging, High Volatility")
    trade_worthy: bool = Field(description="True if the market has clear direction and is worth trading, False if choppy/flat.")
    key_observations: List[str] = Field(description="List of key observations")
    support_levels: List[float] = Field(description="Support levels")
    resistance_levels: List[float] = Field(description="Resistance levels")
    summary: str = Field(description="Comprehensive technical analysis briefing (max 3 sentences)")


class StrategyHypothesis(BaseModel):
    selected_strategy: str = Field(description="Selected strategy name")
    market_condition: str = Field(description="Current market condition assessment")
    action: str = Field(description="BUY | SELL | WAIT")
    confidence: float = Field(description="Confidence level between 0 and 1")
    reasoning: str = Field(description="Detailed explanation of the hypothesis")


class FinalOrder(BaseModel):
    action: str = Field(description="BUY | SELL | HOLD")
    sl: float = Field(description="Stop Loss price")
    tp: float = Field(description="Take Profit price")
    target_rr: float = Field(2.0, description="Risk/reward multiple used to derive TP for execution")
    exit_plan: str = Field("primary_target", description="Execution exit profile, e.g. primary_target | runner | full_exit")
    final_reasoning: str = Field(description="Logical reasoning for final approval or rejection")


class ReviewLog(BaseModel):
    trade_summary: str = Field(description="Overall summary of the trade")
    risk_assessment: str = Field(description="Assessment of chosen risk parameters")
    lessons_learned: str = Field(description="Key takeaways or improvements")
    save_path: str = Field(description="Suggested filename for saving the log, e.g., review_YYYYMMDD_HHMM.md")
