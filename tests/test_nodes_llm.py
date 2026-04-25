import os
import pytest
from unittest.mock import patch, MagicMock
from backend.workflows.nodes import (
    tech_analyst_node, 
    strategist_node, 
    chief_trader_node,
    TechSummary,
    StrategyHypothesis,
    FinalOrder
)
from backend.workflows.state import AgentState

@pytest.fixture
def mock_state() -> AgentState:
    return {
        "raw_data": '{"close": 50000, "rsi": 30}',
        "tech_summary": {},
        "strategy_hypothesis": {},
        "final_order": {}
    }

@patch('backend.workflows.nodes.ChatGoogleGenerativeAI')
def test_tech_analyst_node(mock_llm, mock_state):
    # Mocking with_structured_output
    mock_llm_instance = MagicMock()
    mock_llm.return_value = mock_llm_instance
    mock_structured_llm = MagicMock()
    mock_llm_instance.with_structured_output.return_value = mock_structured_llm
    
    # Mock return value of the chain using actual Pydantic object
    mock_structured_llm.invoke.return_value = TechSummary(
        trend="bullish",
        market_regime="Bullish",
        trade_worthy=True,
        key_observations=["rsi is low"],
        support_levels=[49000.0],
        resistance_levels=[51000.0],
        summary="A bullish trend with low RSI."
    )
    
    result = tech_analyst_node(mock_state)
    
    assert "tech_summary" in result
    assert result["tech_summary"]["trend"] == "bullish"
    assert "rsi is low" in result["tech_summary"]["key_observations"]
    
@patch('backend.workflows.nodes.ChatGoogleGenerativeAI')
def test_strategist_node(mock_llm, mock_state):
    mock_llm_instance = MagicMock()
    mock_llm.return_value = mock_llm_instance
    mock_structured_llm = MagicMock()
    mock_llm_instance.with_structured_output.return_value = mock_structured_llm
    
    mock_structured_llm.invoke.return_value = StrategyHypothesis(
        selected_strategy="RSI Reversal",
        market_condition="Oversold",
        action="BUY",
        confidence=0.8,
        reasoning="Because RSI is 30."
    )
    
    mock_state["tech_summary"] = {
        "trend": "bullish",
        "market_regime": "Bullish",
        "trade_worthy": True,
        "key_observations": ["rsi is low"],
        "support_levels": [49000.0],
        "resistance_levels": [51000.0],
        "summary": "A bullish trend with low RSI."
    }
    
    result = strategist_node(mock_state)
    
    assert "strategy_hypothesis" in result
    assert result["strategy_hypothesis"]["action"] == "BUY"
    assert result["strategy_hypothesis"]["confidence"] == 0.8
    
@patch('backend.workflows.nodes.ChatGoogleGenerativeAI')
def test_chief_trader_node(mock_llm, mock_state):
    mock_llm_instance = MagicMock()
    mock_llm.return_value = mock_llm_instance
    mock_structured_llm = MagicMock()
    mock_llm_instance.with_structured_output.return_value = mock_structured_llm
    
    mock_structured_llm.invoke.return_value = FinalOrder(
        action="BUY",
        sl=49000.0,
        tp=52000.0,
        final_reasoning="Confirmed strategy."
    )
    
    mock_state["strategy_hypothesis"] = {
        "selected_strategy": "RSI Reversal",
        "market_condition": "Oversold",
        "action": "BUY",
        "confidence": 0.8,
        "reasoning": "Because RSI is 30."
    }
    
    result = chief_trader_node(mock_state)
    
    assert "final_order" in result
    assert result["final_order"]["action"] == "BUY"
    assert result["final_order"]["sl"] == 49000.0
