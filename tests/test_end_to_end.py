import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from backend.workflows.state import AgentState
from backend.workflows.graph import get_compiled_graph
from backend.workflows.nodes import TechSummary, StrategyHypothesis, FinalOrder

@patch('backend.workflows.nodes.is_market_open', return_value=True)
@patch('backend.workflows.nodes.is_mt5_available', return_value=True)
@patch('backend.workflows.nodes.get_current_price', return_value={"bid": 1.0520, "ask": 1.0525})
@patch('backend.workflows.nodes.ChatGoogleGenerativeAI')
@patch('backend.workflows.nodes.get_account_summary')
@patch('backend.workflows.nodes.fetch_ohlcv')
def test_end_to_end_trading_pipeline(
    mock_fetch_ohlcv, mock_get_account, mock_llm,
    mock_current_price, mock_mt5_avail, mock_market_open
):
    """
    Test the decision pipeline through Chief Trader.
    Order execution and review are handled after the graph.
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
    
    tech_summary_mock = TechSummary(
        trend="bullish",
        market_regime="Bullish",
        trade_worthy=True,
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
    
    # Using side_effect to return different models for different node calls
    mock_structured_llm.invoke.side_effect = [
        tech_summary_mock,
        strategy_hypothesis_mock,
        final_order_mock,
    ]

    # 4. Execute the Graph
    graph = get_compiled_graph()
    initial_state = {"symbol": "EURUSD"}
    
    # stream returns dict mapping node names to state updates
    final_state = initial_state.copy()
    for s in graph.stream(initial_state):
        node_name = list(s.keys())[0]
        if s[node_name]:
            final_state.update(s[node_name])
    
    # 5. Assertions
    # Check that MT5 functions were called
    mock_get_account.assert_called()
    mock_fetch_ohlcv.assert_called_with("EURUSD", "M5", 100)
    
    # Verify final state
    assert "raw_data" in final_state
    assert "tech_summary" in final_state
    assert "strategy_hypothesis" in final_state
    assert "final_order" in final_state
    assert "order_result" not in final_state
    assert "review_log" not in final_state
    
    assert final_state["final_order"]["action"] == "BUY"
