from typing import TypedDict, Any, Dict, List, Optional

class AgentState(TypedDict, total=False):
    """
    State shared across all nodes in the LangGraph pipeline.
    total=False allows missing keys during initialization.
    """
    # Meta Context
    symbol: str
    timeframe: str
    error_flag: bool
    
    # Node 1: Fetch Data
    raw_data: str 
    account_info: Dict[str, Any]
    open_positions: List[Dict[str, Any]]
    
    # Node 2: Tech Analyst
    tech_summary: Dict[str, Any]
    
    # Node 3: Strategist
    strategy_hypothesis: Dict[str, Any]
    
    # Node 4: Chief Trader
    final_order: Dict[str, Any]
