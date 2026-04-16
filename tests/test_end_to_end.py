import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from backend.workflows.state import AgentState
from backend.workflows.graph import get_compiled_graph
from backend.workflows.nodes import TechSummary, StrategyHypothesis, FinalOrder, ReviewLog

@patch('backend.workflows.nodes.ChatGoogleGenerativeAI')
@patch('backend.workflows.nodes.get_account_summary')
@patch('backend.workflows.nodes.fetch_ohlcv')
@patch('backend.workflows.nodes.execute_mock_order')
def test_end_to_end_trading_pipeline(mock_execute_order, mock_fetch_ohlcv, mock_get_account, mock_llm):
    """
    Test the entire end-to-end trading pipeline including Data Fetching, Analysis, Strategy, Trading, Execution, and Review.
    """
    # 1. Setup Mock MT5 Data
    mock_get_account.return_value = {
        "balance": 10000.0,
        "equity": 10000.0,
        "margin": 0.0,
        "margin_free": 10000.0
    }
    
    mock_df = pd.DataFrame({
        'time': ['2023-10-26 10:00:00'],
        'open': [1.0500],
        'high': [1.0550],
        'low': [1.0450],
        'close': [1.0520],
        'tick_volume': [1000],
        'spread': [1],
        'real_volume': [0]
    })
    mock_fetch_ohlcv.return_value = mock_df
    
    # 2. Setup Mock LLM Responses
    mock_llm_instance = MagicMock()
    mock_llm.return_value = mock_llm_instance
    mock_structured_llm = MagicMock()
    mock_llm_instance.with_structured_output.return_value = mock_structured_llm
    
    # We have 4 LLM nodes. Let's mock their return values in sequence
    # Since they return different structured models, we need to handle the .invoke() call.
    # In the code, .invoke() returns a Pydantic model directly.
    # Actually, .invoke() returns the instantiated Pydantic object.
    
    tech_summary_mock = TechSummary(
        trend="bullish",
        key_observations=["Price is above SMA 200"],
        support_levels=[1.0450],
        resistance_levels=[1.0550],
        summary="Bullish trend detected."
    )
    
    strategy_hypothesis_mock = StrategyHypothesis(
        selected_strategy="Trend Following",
        market_condition="Trending Up",
        action="BUY",
        confidence=0.8,
        reasoning="Strong bullish momentum."
    )
    
    final_order_mock = FinalOrder(
        action="BUY",
        sl=1.0400,
        tp=1.0600,
        final_reasoning="Agree with strategy."
    )
    
    review_log_mock = ReviewLog(
        trade_summary="Executed a BUY order.",
        risk_assessment="Risk is within 1% limit.",
        lessons_learned="Good execution.",
        save_path="review_test.md"
    )
    
    # Using side_effect to return different models for different node calls
    mock_structured_llm.invoke.side_effect = [
        tech_summary_mock,
        strategy_hypothesis_mock,
        final_order_mock,
        review_log_mock
    ]
    
    # 3. Setup Mock Order Execution Return
    mock_execute_order.return_value = {
        "retcode": 10009,
        "volume": 0.1,
        "price": 1.0520,
        "comment": "Mock Paper Trading Order"
    }

    # 4. Execute the Graph
    graph = get_compiled_graph()
    initial_state = {"symbol": "EURUSD"}
    
    # stream returns dict mapping node names to state updates
    final_state = initial_state.copy()
    for s in graph.stream(initial_state):
        node_name = list(s.keys())[0]
        final_state.update(s[node_name])
    
    # 5. Assertions
    # Check that MT5 functions were called
    mock_get_account.assert_called()
    mock_fetch_ohlcv.assert_called_with("EURUSD", 16385, 100)
    
    # Check execution node
    # From guardrails: risk_amount = 10000 * 0.01 = 100
    # price_diff = abs(1.0 - 1.0400) = 0.04 (Note entry_price is mocked as 1.0 in node)
    # lot_size = 100 / 0.04 = 2500.0
    mock_execute_order.assert_called_once_with("EURUSD", "BUY", 2500.0, 1.0400, 1.0600, 1.0)
    
    # Verify final state
    assert "raw_data" in final_state
    assert "tech_summary" in final_state
    assert "strategy_hypothesis" in final_state
    assert "final_order" in final_state
    assert "order_result" in final_state
    assert "review_log" in final_state
    
    assert final_state["order_result"]["retcode"] == 10009
    assert final_state["review_log"]["trade_summary"] == "Executed a BUY order."
