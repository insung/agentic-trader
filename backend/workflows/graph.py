from langgraph.graph import StateGraph, START, END
from backend.workflows.state import AgentState
from backend.workflows.nodes import (
    fetch_data_node,
    tech_analyst_node,
    strategist_node,
    chief_trader_node
)

def create_workflow() -> StateGraph:
    """
    Creates and compiles the LangGraph StateGraph pipeline.
    Connects nodes in sequence:
    fetch_data -> tech_analyst -> strategist -> chief_trader
    """
    workflow = StateGraph(AgentState)
    
    # Add nodes to the graph
    workflow.add_node("fetch_data", fetch_data_node)
    workflow.add_node("tech_analyst", tech_analyst_node)
    workflow.add_node("strategist", strategist_node)
    workflow.add_node("chief_trader", chief_trader_node)
    
    # Define edges (sequence of execution)
    workflow.add_edge(START, "fetch_data")
    workflow.add_edge("fetch_data", "tech_analyst")
    workflow.add_edge("tech_analyst", "strategist")
    workflow.add_edge("strategist", "chief_trader")
    workflow.add_edge("chief_trader", END)
    
    return workflow

def get_compiled_graph():
    """
    Returns the compiled graph ready for execution.
    """
    workflow = create_workflow()
    return workflow.compile()
