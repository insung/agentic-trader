from backend.features.trading import position_tracker


def test_paper_position_review_runs_only_after_close(tmp_path, monkeypatch):
    tracked_path = tmp_path / "tracked_positions.json"
    reviewed_path = tmp_path / "reviewed_trades.json"
    trading_log_db = tmp_path / "trading_logs.sqlite"
    monkeypatch.setattr(position_tracker, "TRACKED_POSITIONS_PATH", str(tracked_path))
    monkeypatch.setattr(position_tracker, "REVIEWED_TRADES_PATH", str(reviewed_path))
    monkeypatch.setattr(position_tracker, "TRADING_LOG_DB_PATH", str(trading_log_db))

    review_calls = []

    def fake_review(state):
        review_calls.append(state.closed_trade)
        return {
            "review_log": {
                "trade_summary": "closed",
                "risk_assessment": "ok",
                "lessons_learned": "based on close",
                "save_path": "review_test.md",
            }
        }

    monkeypatch.setattr(position_tracker, "risk_reviewer_node", fake_review)

    decision_context = {
        "final_order": {
            "action": "BUY",
            "symbol": "EURUSD",
            "entry_price": 1.0,
            "sl_price": 0.9,
            "tp_price": 1.2,
            "lot_size": 1.0,
            "reasoning": "test",
        },
        "order_result": {
            "success": True,
            "ticket": "P1",
            "executed_price": 1.0,
            "timestamp": "2026-04-26T00:00:00",
        },
    }
    position_tracker.track_open_position(
        mode="paper",
        symbol="EURUSD",
        action="BUY",
        entry_price=1.0,
        sl=0.9,
        tp=1.2,
        lot_size=1.0,
        order_result=decision_context["order_result"],
        decision_context=decision_context,
    )

    monkeypatch.setattr(position_tracker, "get_current_price", lambda symbol: {"bid": 1.1, "ask": 1.1})
    assert position_tracker.reconcile_tracked_positions() == []
    assert review_calls == []

    monkeypatch.setattr(position_tracker, "get_current_price", lambda symbol: {"bid": 1.2, "ask": 1.2})
    reviewed = position_tracker.reconcile_tracked_positions()
    assert len(reviewed) == 1
    assert reviewed[0]["closed_trade"]["result"] == "TP_HIT"
    assert position_tracker.load_tracked_positions() == []

    assert position_tracker.reconcile_tracked_positions() == []
    assert len(review_calls) == 1
