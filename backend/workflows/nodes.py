from typing import Dict, Any
from backend.workflows.state import AgentState

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
    Dummy implementation parsing state and returning fixed summary.
    """
    print("[Node 2] tech_analyst_node executed")
    raw_data = state.get("raw_data", "")
    return {
        "tech_summary": {
            "trend": "bullish",
            "support": 50000,
            "resistance": 55000,
            "source_data_length": len(raw_data)
        }
    }

def strategist_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 3: Strategist reviews technical summary and returns a hypothesis.
    Dummy implementation.
    """
    print("[Node 3] strategist_node executed")
    tech_summary = state.get("tech_summary", {})
    return {
        "strategy_hypothesis": {
            "action": "buy",
            "confidence": 0.8,
            "based_on_trend": tech_summary.get("trend", "unknown")
        }
    }

def chief_trader_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 4: Chief Trader reviews hypothesis and returns final order.
    Dummy implementation.
    """
    print("[Node 4] chief_trader_node executed")
    hypothesis = state.get("strategy_hypothesis", {})
    return {
        "final_order": {
            "action": "BUY",
            "sl": 49000,
            "tp": 56000,
            "symbol": "BTCUSD",
            "reasoning_action": hypothesis.get("action", "none")
        }
    }
