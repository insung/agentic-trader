from backend.workflows.nodes import _load_strategy_contract, _project_tp_from_rr


def test_load_strategy_contract_returns_ma_crossover_rr_floor():
    contract = _load_strategy_contract("Moving Average Crossover")

    assert contract["name"] == "Moving Average Crossover"
    assert contract["minimum_risk_reward"] == 2.0


def test_project_tp_from_rr_is_direction_aware():
    assert _project_tp_from_rr("BUY", 100.0, 95.0, 2.0) == 110.0
    assert _project_tp_from_rr("SELL", 100.0, 105.0, 2.0) == 90.0
