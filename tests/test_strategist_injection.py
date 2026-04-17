import os
from backend.workflows.nodes import strategist_node
from unittest.mock import patch, MagicMock

@patch('backend.workflows.nodes.ChatGoogleGenerativeAI')
def test_strategist_node_injects_knowledge(mock_llm_class):
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.invoke.return_value = MagicMock(model_dump=lambda: {"selected_strategy": "Test", "market_condition": "A", "action": "BUY", "confidence": 0.9, "reasoning": "B"})
    mock_llm.with_structured_output.return_value = mock_structured
    mock_llm_class.return_value = mock_llm
    
    os.makedirs("docs/trading-strategies", exist_ok=True)
    with open("docs/trading-strategies/test_strat.md", "w") as f:
        f.write("TEST_STRATEGY_CONTENT")
        
    state = {"tech_summary": {}}
    strategist_node(state)
    
    call_args = mock_structured.invoke.call_args[0][0]
    human_msg = call_args[1].content
    
    assert "TEST_STRATEGY_CONTENT" in human_msg