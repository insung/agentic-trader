from langgraph.graph import StateGraph, START, END
from backend.workflows.state import AgentState
from backend.workflows.nodes import (
    fetch_data_node,
    tech_analyst_node,
    strategist_node,
    chief_trader_node,
)

def fetch_data_router(state: AgentState) -> str:
    """fetch_data 노드 후, 에러가 있으면 즉시 종료."""
    if getattr(state, "error_flag", False):
        error_msg = getattr(state, "error_message", "Unknown error")
        print(f"🛑 Workflow aborted after fetch_data: {error_msg}")
        return END
    return "tech_analyst"

def tech_analyst_router(state: AgentState) -> str:
    """Tech Analyst 결과에 따른 라우팅. trade_worthy=False면 즉시 종료."""
    if getattr(state, "error_flag", False):
        print("🛑 Workflow aborted: LLM error in tech_analyst.")
        return END
    tech_summary = getattr(state, "tech_summary", {})
    if not tech_summary.get("trade_worthy", True):
        print("📊 Market is choppy. Short-circuiting workflow.")
        return END
    return "strategist"

def create_workflow() -> StateGraph:
    """
    Creates and compiles the LangGraph StateGraph pipeline.
    Connects nodes in sequence:
    fetch_data -> tech_analyst -> strategist -> chief_trader

    Order execution and post-trade review are handled outside the decision graph.
    A review must only be written after the resulting position has actually closed.
    """
    workflow = StateGraph(AgentState)
    
    # Add nodes to the graph
    workflow.add_node("fetch_data", fetch_data_node)
    workflow.add_node("tech_analyst", tech_analyst_node)
    workflow.add_node("strategist", strategist_node)
    workflow.add_node("chief_trader", chief_trader_node)
    
    # Define edges (sequence of execution)
    workflow.add_edge(START, "fetch_data")
    
    # fetch_data 후 에러 체크 (시장 휴장, MT5 미연결 등)
    workflow.add_conditional_edges(
        "fetch_data",
        fetch_data_router,
        {"tech_analyst": "tech_analyst", END: END}
    )
    
    # tech_analyst 후 trade_worthy 체크
    workflow.add_conditional_edges(
        "tech_analyst",
        tech_analyst_router,
        {"strategist": "strategist", END: END}
    )
    
    workflow.add_edge("strategist", "chief_trader")
    workflow.add_edge("chief_trader", END)
    
    return workflow

def get_compiled_graph():
    """
    Returns the compiled graph ready for execution.
    """
    workflow = create_workflow()
    return workflow.compile()
