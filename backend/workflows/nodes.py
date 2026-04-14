import os
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from backend.workflows.state import AgentState

# Pydantic Models for Structured Output
class TechSummary(BaseModel):
    trend: str = Field(description="bullish | bearish | neutral")
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
    final_reasoning: str = Field(description="Logical reasoning for final approval or rejection")

def _read_prompt(agent_name: str) -> str:
    """Read the system prompt from the markdown file."""
    # Compute base dir as the project root
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    file_path = os.path.join(base_dir, ".agents", "agents", f"{agent_name}.md")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"System prompt for {agent_name} not found."

def fetch_data_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 1: Fetch OHLCV Data and calculate indicators.
    Dummy implementation returning fixed raw_data.
    """
    print("[Node 1] fetch_data_node executed")
    return {"raw_data": "Dummy OHLCV Data with Indicators"}

def tech_analyst_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 2: Tech Analyst analyzes raw data and outputs a summary.
    """
    print("[Node 2] tech_analyst_node executed")
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    structured_llm = llm.with_structured_output(TechSummary)
    
    system_prompt = _read_prompt("tech_analyst")
    human_content = f"Here is the raw data:\n{state.get('raw_data', '')}"
    
    response = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_content)
    ])
    
    return {"tech_summary": response.model_dump()}

def strategist_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 3: Strategist reviews technical summary and returns a hypothesis.
    """
    print("[Node 3] strategist_node executed")
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    structured_llm = llm.with_structured_output(StrategyHypothesis)
    
    system_prompt = _read_prompt("strategist")
    human_content = f"Here is the Tech Summary:\n{state.get('tech_summary', {})}"
    
    response = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_content)
    ])
    
    return {"strategy_hypothesis": response.model_dump()}

def chief_trader_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 4: Chief Trader reviews hypothesis and returns final order.
    """
    print("[Node 4] chief_trader_node executed")
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    structured_llm = llm.with_structured_output(FinalOrder)
    
    system_prompt = _read_prompt("chief_trader")
    human_content = f"Here is the Strategy Hypothesis:\n{state.get('strategy_hypothesis', {})}"
    
    response = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_content)
    ])
    
    return {"final_order": response.model_dump()}
