import copy

from backend.features.trading.operations import position_tracker as pt


def _base_decision_context():
    return {
        "strategy_hypothesis": {
            "selected_strategy": "Volatility Expansion Breakout",
            "action": "BUY",
        },
        "final_order": {
            "strategy_metadata": {
                "strategy": "Volatility Expansion Breakout",
                "primary_timeframe": "M5",
                "confirmation_timeframes": ["M15"],
                "neckline": 100.0,
                "invalidation_rule": "two_consecutive_neckline_breaks",
            },
            "entry_price": 105.0,
            "sl_price": 95.0,
            "tp_price": 125.0,
        },
    }


def test_track_open_position_persists_strategy_metadata(monkeypatch):
    captured = {}

    monkeypatch.setattr(pt, "load_tracked_positions", lambda: [])
    monkeypatch.setattr(pt, "save_tracked_positions", lambda positions: captured.setdefault("positions", copy.deepcopy(positions)))

    tracked = pt.track_open_position(
        mode="paper",
        symbol="BTCUSD",
        action="BUY",
        entry_price=105.0,
        sl=95.0,
        tp=125.0,
        lot_size=1.0,
        order_result={"ticket": 101, "order": 101},
        decision_context=_base_decision_context(),
    )

    assert tracked["strategy_metadata"]["strategy"] == "Volatility Expansion Breakout"
    assert tracked["strategy_metadata"]["neckline"] == 100.0
    assert tracked["strategy_metadata"]["invalidation_rule"] == "two_consecutive_neckline_breaks"
    assert tracked["invalidation_state"]["consecutive_breaches"] == 0
    assert captured["positions"][0]["strategy_metadata"]["neckline"] == 100.0


def test_reconcile_tracked_positions_closes_after_two_consecutive_neckline_breaches(monkeypatch):
    store = []
    reviewed = []

    position = {
        "trade_id": "trade-1",
        "ticket": 101,
        "mode": "paper",
        "symbol": "BTCUSD",
        "action": "BUY",
        "entry_time": "2026-05-11T20:00:00",
        "entry_price": 105.0,
        "sl": 95.0,
        "tp": 125.0,
        "lot_size": 1.0,
        "strategy_metadata": {
            "strategy": "Volatility Expansion Breakout",
            "primary_timeframe": "M5",
            "confirmation_timeframes": ["M15"],
            "neckline": 100.0,
            "invalidation_rule": "two_consecutive_neckline_breaks",
        },
        "invalidation_state": {"consecutive_breaches": 0, "last_checked_price": None},
        "decision_context": _base_decision_context(),
    }
    store.append(position)

    def load_tracked_positions():
        return copy.deepcopy(store)

    def save_tracked_positions(positions):
        store[:] = copy.deepcopy(positions)

    monkeypatch.setattr(pt, "load_tracked_positions", load_tracked_positions)
    monkeypatch.setattr(pt, "save_tracked_positions", save_tracked_positions)
    monkeypatch.setattr(pt, "load_reviewed_trade_ids", lambda: [])
    monkeypatch.setattr(pt, "mark_trade_reviewed", lambda trade_id: reviewed.append(trade_id))
    monkeypatch.setattr(pt, "get_current_price", lambda symbol: {"bid": 99.0, "ask": 99.2, "last": 99.1})
    monkeypatch.setattr(pt, "review_closed_trade", lambda decision_context, closed_trade: {"error_flag": False, "review_log": {"trade_summary": "ok"}})

    first = pt.reconcile_tracked_positions()
    assert first == []
    assert store[0]["invalidation_state"]["consecutive_breaches"] == 1
    assert store[0]["invalidation_state"]["last_checked_price"] == 99.0

    second = pt.reconcile_tracked_positions()
    assert len(second) == 1
    assert second[0]["closed_trade"]["result"] == "INVALIDATED"
    assert second[0]["closed_trade"]["exit_reason"] == "Neckline invalidation"
    assert reviewed == ["trade-1"]
    assert store == []
