from types import SimpleNamespace

import backend.workflows.nodes as nodes


def test_execute_order_node_attaches_volatility_expansion_metadata(monkeypatch):
    monkeypatch.setattr(nodes, "get_account_summary", lambda: {"balance": 10000.0})
    monkeypatch.setattr(nodes, "get_current_price", lambda symbol: {"ask": 105.2, "bid": 104.8})
    monkeypatch.setattr(nodes, "validate_strategy_setup", lambda *args, **kwargs: (True, "ok", None, None))
    monkeypatch.setattr(nodes, "validate_order_prices", lambda *args, **kwargs: True)
    monkeypatch.setattr(nodes, "enforce_one_percent_rule", lambda *args, **kwargs: 1.0)
    monkeypatch.setattr(nodes, "execute_mock_order", lambda *args, **kwargs: {"retcode": 10009, "order": 7, "price": 105.2})

    state = SimpleNamespace(
        symbol="BTCUSD",
        strategy_hypothesis={"selected_strategy": "Volatility Expansion Breakout"},
        indicator_data={
            "M5": {
                "latest": {"high": 108.0, "low": 104.0, "close": 107.0, "atr14": 1.0, "bb_lower20": 80.0, "bb_upper20": 120.0},
                "recent_rows": [
                    {"high": 100.0, "low": 95.0, "close": 97.0, "open": 96.0, "atr14": 1.0, "bb_lower20": 90.0, "bb_upper20": 110.0}
                    for _ in range(23)
                ]
                + [
                    {"high": 100.0, "low": 89.0, "close": 92.0, "open": 91.0, "atr14": 1.0, "bb_lower20": 90.0, "bb_upper20": 110.0},
                    {"high": 105.0, "low": 94.0, "close": 104.0, "open": 103.0, "atr14": 1.0, "bb_lower20": 90.0, "bb_upper20": 110.0},
                    {"high": 102.0, "low": 91.0, "close": 95.0, "open": 96.0, "atr14": 1.0, "bb_lower20": 90.0, "bb_upper20": 110.0},
                    {"high": 103.0, "low": 96.0, "close": 100.0, "open": 99.0, "atr14": 1.0, "bb_lower20": 90.0, "bb_upper20": 110.0},
                    {"high": 104.0, "low": 97.0, "close": 101.0, "open": 100.0, "atr14": 1.0, "bb_lower20": 90.0, "bb_upper20": 110.0},
                    {"high": 105.0, "low": 98.0, "close": 102.0, "open": 101.0, "atr14": 1.0, "bb_lower20": 90.0, "bb_upper20": 110.0},
                    {"high": 108.0, "low": 104.0, "close": 107.0, "open": 104.0, "atr14": 1.0, "bb_lower20": 80.0, "bb_upper20": 120.0},
                ],
            },
            "M15": {
                "latest": {"adx14": 25.0, "close": 107.0, "ema20": 100.0, "ema50": 90.0, "atr14": 2.0},
                "recent_rows": [{"adx14": 24.0}, {"adx14": 25.0}],
            },
        },
        final_order={"action": "BUY", "sl_price": 90.0, "tp_price": 125.0},
    )

    result = nodes.execute_order_node(state)

    assert result["order_result"]["success"] is True
    assert result["final_order"]["strategy_metadata"]["strategy"] == "Volatility Expansion Breakout"
    assert result["final_order"]["strategy_metadata"]["neckline"] == 105.0
    assert result["final_order"]["strategy_metadata"]["invalidation_rule"] == "two_consecutive_neckline_breaks"
