import os
import json
from datetime import datetime
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from backend.workflows.state import AgentState
from backend.services.mt5_client import fetch_ohlcv, get_account_summary, execute_mock_order
from backend.core.guardrails import enforce_one_percent_rule

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

class ReviewLog(BaseModel):
    trade_summary: str = Field(description="Overall summary of the trade")
    risk_assessment: str = Field(description="Assessment of chosen risk parameters")
    lessons_learned: str = Field(description="Key takeaways or improvements")
    save_path: str = Field(description="Suggested filename for saving the log, e.g., review_YYYYMMDD_HHMM.md")

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
    Now actually tries to fetch from MT5 Client.
    """
    print("[Node 1] fetch_data_node executed")
    symbol = state.get("symbol", "EURUSD") # Defaulting to EURUSD if not provided
    
    # Get account info
    account_info = get_account_summary()
    
    # Try fetching real data, fallback to dummy if it fails (e.g. not connected)
    df = fetch_ohlcv(symbol, 16385, 100) # 16385 = mt5.TIMEFRAME_H1
    if not df.empty:
        # Just returning the last few rows as json string for the LLM
        recent_data = df.tail(5).to_json(orient='records')
        raw_data = f"Account Info: {account_info}\nRecent Market Data (H1): {recent_data}"
    else:
        raw_data = f"Account Info: {account_info}\nDummy OHLCV Data with Indicators"
        
    return {"raw_data": raw_data}

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

def execute_order_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 4.5: Executes the order based on Chief Trader's decision.
    Applies guardrails before execution.
    """
    print("[Node 4.5] execute_order_node executed")
    final_order = state.get("final_order", {})
    action = final_order.get("action", "HOLD")
    
    if action.upper() not in ["BUY", "SELL"]:
        return {"order_result": {"status": "skipped", "reason": f"Action was {action}"}}
        
    symbol = state.get("symbol", "EURUSD")
    sl = final_order.get("sl", 0.0)
    tp = final_order.get("tp", 0.0)
    
    # 1. Apply Guardrails
    account_info = get_account_summary()
    balance = account_info.get("balance", 10000.0) # dummy balance if not connected
    
    # Needs a mock entry price for the 1% rule calculation
    entry_price = 1.0 # placeholder
    lot_size = enforce_one_percent_rule(balance, entry_price, sl)
    
    if lot_size <= 0:
         return {"order_result": {"status": "rejected", "reason": "Guardrail: lot size calculated to <= 0"}}
         
    # 2. Execute Mock Order (Paper Trading)
    # Using mock order function as specified
    result = execute_mock_order(symbol, action, lot_size, sl, tp, entry_price)
    
    return {"order_result": result}

def risk_reviewer_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 5: Risk Reviewer reviews the entire process and logs the result.
    """
    print("[Node 5] risk_reviewer_node executed")
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    structured_llm = llm.with_structured_output(ReviewLog)
    
    system_prompt = _read_prompt("risk_reviewer")
    human_content = json.dumps({
        "raw_data": state.get("raw_data", ""),
        "tech_summary": state.get("tech_summary", {}),
        "strategy_hypothesis": state.get("strategy_hypothesis", {}),
        "final_order": state.get("final_order", {}),
        "order_result": state.get("order_result", {})
    }, indent=2)
    
    response = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_content)
    ])
    
    review_log = response.model_dump()
    
    # Save to file
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    docs_dir = os.path.join(base_dir, "docs", "trading_logs")
    os.makedirs(docs_dir, exist_ok=True)
    
    # Ensure safe filename
    safe_filename = review_log.get("save_path", f"review_{datetime.now().strftime('%Y%m%d_%H%M')}.md")
    safe_filename = safe_filename.replace("/", "_").replace("\\", "_")
    if not safe_filename.endswith(".md"):
        safe_filename += ".md"
        
    file_path = os.path.join(docs_dir, safe_filename)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"# Trade Review Log\n\n")
        f.write(f"**Date**: {datetime.now().isoformat()}\n\n")
        f.write(f"## Summary\n{review_log.get('trade_summary', '')}\n\n")
        f.write(f"## Risk Assessment\n{review_log.get('risk_assessment', '')}\n\n")
        f.write(f"## Lessons Learned\n{review_log.get('lessons_learned', '')}\n")
    
    print(f"[Node 5] Review log saved to {file_path}")
    
    return {"review_log": review_log}

