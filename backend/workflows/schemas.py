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
    process_quality: str = Field("", description="Process/rule adherence quality, e.g. good | mixed | poor | unknown")
    outcome_quality: str = Field("", description="Outcome quality, e.g. favorable | neutral | unfavorable | unknown")
    trade_quality_label: str = Field("", description="Final label such as good_trade | bad_trade | mixed_trade")
    rule_adherence: bool | None = Field(default=None, description="Whether the trade followed the intended rules")
    lesson_root_cause: str = Field("", description="Primary cause of the outcome, stated concretely")
    lesson_evidence: List[str] = Field(default_factory=list, description="Concrete evidence bullets that support the lesson")
    next_trade_rule: str = Field("", description="One specific rule to apply in the next similar setup")
    lessons_learned: str = Field("", description="Structured synthesis tying outcome, root cause, evidence, and next rule together")
    confidence: float = Field(0.5, description="Confidence in the review quality, between 0 and 1")
    save_path: str = Field(description="Suggested filename for saving the log, e.g., review_YYYYMMDD_HHMM.md")
