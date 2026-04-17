from backend.workflows.nodes import tech_analyst_node
from unittest.mock import patch, MagicMock

@patch('backend.workflows.nodes.ChatGoogleGenerativeAI')
def test_llm_retry_on_failure(mock_llm_class):
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    
    mock_structured.invoke.side_effect = [
        Exception("API Error 1"),
        Exception("API Error 2"),
        MagicMock(model_dump=lambda: {"trend": "bullish", "trade_worthy": True, "key_observations": [], "support_levels": [], "resistance_levels": [], "summary": ""})
    ]
    mock_llm.with_structured_output.return_value = mock_structured
    mock_llm_class.return_value = mock_llm
    
    state = {"raw_data": "data"}
    result = tech_analyst_node(state)
    
    assert result["tech_summary"]["trend"] == "bullish"
    assert mock_structured.invoke.call_count == 3
