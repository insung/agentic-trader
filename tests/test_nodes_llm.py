import os
import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock, mock_open
from backend.workflows.nodes import (
    tech_analyst_node, 
    strategist_node, 
    chief_trader_node,
    risk_reviewer_node,
    TechSummary,
    StrategyHypothesis,
    FinalOrder
)
import backend.workflows.nodes as nodes_module
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
    assert result["final_order"]["sl_price"] == 49000.0
    assert result["final_order"]["tp_price"] == 52000.0


@patch("backend.workflows.nodes.ChatGoogleGenerativeAI")
@patch("builtins.open", new_callable=mock_open)
def test_risk_reviewer_node_writes_structured_lessons(mock_file, mock_llm, monkeypatch):
    mock_llm_instance = MagicMock()
    mock_llm.return_value = mock_llm_instance
    mock_llm_instance.with_structured_output.return_value = MagicMock()

    fake_response = MagicMock()
    fake_response.model_dump.return_value = {
        "trade_summary": "BTCUSD BUY closed flat after entry.",
        "risk_assessment": "Risk stayed within plan.",
        "process_quality": "mixed",
        "outcome_quality": "neutral",
        "trade_quality_label": "mixed_trade",
        "rule_adherence": True,
        "lesson_root_cause": "The setup did not receive follow-through after entry.",
        "lesson_evidence": [
            "closed_trade.result=CLOSED",
            "closed_trade.pnl=0.0",
            "closed_trade.exit_reason=Closed",
            "strategy=Moving Average Crossover",
        ],
        "next_trade_rule": "Require stronger post-entry momentum before re-entering the same setup.",
        "lessons_learned": "Placeholder",
        "confidence": 0.87,
        "save_path": "review_20260511_2220.md",
    }
    monkeypatch.setattr(nodes_module, "_invoke_llm_with_retry", lambda structured_llm, messages: fake_response)
    monkeypatch.setattr(nodes_module, "store_trade_review", lambda *args, **kwargs: kwargs)
    monkeypatch.setattr(nodes_module.os, "makedirs", lambda *args, **kwargs: None)

    state = SimpleNamespace(
        raw_data="raw",
        tech_summary={"market_regime": "Ranging"},
        strategy_hypothesis={"selected_strategy": "Moving Average Crossover"},
        final_order={"action": "BUY"},
        order_result={"success": True},
        decision_context={
            "tech_summary": {"market_regime": "Ranging"},
            "strategy_hypothesis": {"selected_strategy": "Moving Average Crossover"},
            "final_order": {"action": "BUY"},
        },
        closed_trade={
            "trade_id": "trade-1",
            "symbol": "BTCUSD",
            "action": "BUY",
            "entry_time": "2026-05-11T20:00:00",
            "exit_time": "2026-05-11T21:00:00",
            "entry_price": 105.0,
            "exit_price": 105.0,
            "sl": 95.0,
            "tp": 125.0,
            "lot_size": 1.0,
            "result": "CLOSED",
            "exit_reason": "Closed",
            "pnl": 0.0,
        },
    )

    result = risk_reviewer_node(state)

    assert result["review_id"] == "review_20260511_2220"
    assert result["review_markdown_path"].endswith("review_20260511_2220.md")
    assert mock_file.call_count == 1

    written_markdown = mock_file().write.call_args[0][0]
    assert "## Root Cause" in written_markdown
    assert "## Evidence" in written_markdown
    assert "## Next Trade Rule" in written_markdown
    assert "## Process Quality" in written_markdown
    assert "## Outcome Quality" in written_markdown
    assert "## Trade Classification" in written_markdown
    assert "The setup did not receive follow-through after entry." in written_markdown


@patch("backend.workflows.nodes.ChatGoogleGenerativeAI")
@patch("builtins.open", new_callable=mock_open)
def test_risk_reviewer_node_marks_bad_trade_when_rules_broken(mock_file, mock_llm, monkeypatch):
    mock_llm_instance = MagicMock()
    mock_llm.return_value = mock_llm_instance
    mock_llm_instance.with_structured_output.return_value = MagicMock()

    fake_response = MagicMock()
    fake_response.model_dump.return_value = {
        "trade_summary": "BTCUSD BUY hit take profit.",
        "risk_assessment": "Risk appeared acceptable.",
        "process_quality": "poor",
        "outcome_quality": "favorable",
        "rule_adherence": False,
        "lesson_root_cause": "The entry violated the strategy gate despite the eventual profit.",
        "lesson_evidence": [
            "closed_trade.result=TP_HIT",
            "closed_trade.pnl=12.5",
            "closed_trade.exit_reason=Take Profit",
            "rule_adherence=False",
        ],
        "next_trade_rule": "Do not override the strategy gate even when the market looks favorable.",
        "lessons_learned": "Placeholder",
        "confidence": 0.92,
        "save_path": "review_20260511_2230.md",
    }
    monkeypatch.setattr(nodes_module, "_invoke_llm_with_retry", lambda structured_llm, messages: fake_response)
    monkeypatch.setattr(nodes_module, "store_trade_review", lambda *args, **kwargs: kwargs)
    monkeypatch.setattr(nodes_module.os, "makedirs", lambda *args, **kwargs: None)

    state = SimpleNamespace(
        raw_data="raw",
        tech_summary={"market_regime": "Bullish"},
        strategy_hypothesis={"selected_strategy": "Moving Average Crossover"},
        final_order={"action": "BUY"},
        order_result={"success": True},
        decision_context={
            "tech_summary": {"market_regime": "Bullish"},
            "strategy_hypothesis": {"selected_strategy": "Moving Average Crossover"},
            "final_order": {"action": "BUY"},
        },
        closed_trade={
            "trade_id": "trade-2",
            "symbol": "BTCUSD",
            "action": "BUY",
            "entry_time": "2026-05-11T20:00:00",
            "exit_time": "2026-05-11T21:30:00",
            "entry_price": 100.0,
            "exit_price": 112.5,
            "sl": 95.0,
            "tp": 112.5,
            "lot_size": 1.0,
            "result": "TP_HIT",
            "exit_reason": "Take Profit",
            "pnl": 12.5,
        },
    )

    result = risk_reviewer_node(state)

    assert result["review_log"]["trade_quality_label"] == "bad_trade"
    assert result["review_log"]["process_quality"] == "poor"
    assert result["review_log"]["outcome_quality"] == "favorable"
    assert "bad_trade" in mock_file().write.call_args[0][0]
