import pytest
from backend.workflows.graph import get_compiled_graph
from backend.workflows.state import AgentState

def test_dummy_pipeline_execution():
    """
    Test the sequential execution of the LangGraph pipeline with dummy nodes.
    Ensures that state is updated and passed correctly between nodes.
    """
    # 1. Initialize empty state and compiled graph
    app = get_compiled_graph()
    initial_state: AgentState = {}
    
    # 2. Invoke the pipeline
    final_state = app.invoke(initial_state)
    
    # 3. Assertions to verify data flow
    # Check fetch_data_node execution
    assert "raw_data" in final_state
    assert final_state["raw_data"] == "Dummy OHLCV Data with Indicators"
    
    # Check tech_analyst_node execution (it should use raw_data)
    assert "tech_summary" in final_state
    assert final_state["tech_summary"]["trend"] == "bullish"
    assert final_state["tech_summary"]["source_data_length"] == len("Dummy OHLCV Data with Indicators")
    
    # Check strategist_node execution (it should use tech_summary)
    assert "strategy_hypothesis" in final_state
    assert final_state["strategy_hypothesis"]["action"] == "buy"
    assert final_state["strategy_hypothesis"]["confidence"] == 0.8
    assert final_state["strategy_hypothesis"]["based_on_trend"] == "bullish"
    
    # Check chief_trader_node execution (it should use strategy_hypothesis)
    assert "final_order" in final_state
    assert final_state["final_order"]["action"] == "BUY"
    assert final_state["final_order"]["sl"] == 49000
    assert final_state["final_order"]["reasoning_action"] == "buy"
