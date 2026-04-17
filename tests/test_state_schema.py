from backend.workflows.state import AgentState

def test_agent_state_fields():
    state: AgentState = {
        "symbol": "EURUSD",
        "timeframe": "M15",
        "account_info": {"balance": 10000.0, "free_margin": 5000.0},
        "open_positions": [{"symbol": "EURUSD", "volume": 0.1}],
        "error_flag": False
    }
    assert state["symbol"] == "EURUSD"
    assert "account_info" in state
