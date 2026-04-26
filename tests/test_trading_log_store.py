import sqlite3

from backend.features.trading import trading_log_store


def test_trading_log_store_persists_positions_reviewed_ids_and_reviews(tmp_path):
    db_path = tmp_path / "trading_logs.sqlite"

    trading_log_store.replace_tracked_positions(
        str(db_path),
        [
            {
                "trade_id": "T1",
                "ticket": 123,
                "mode": "paper",
                "symbol": "BTCUSD",
                "action": "BUY",
                "entry_time": "2026-04-26T00:00:00",
                "entry_price": 100.0,
                "sl": 90.0,
                "tp": 120.0,
                "lot_size": 0.1,
                "order_result": {"success": True},
                "decision_context": {"strategy_hypothesis": {"selected_strategy": "test"}},
            }
        ],
    )
    positions = trading_log_store.load_tracked_positions(str(db_path))
    assert len(positions) == 1
    assert positions[0]["trade_id"] == "T1"
    assert positions[0]["order_result"]["success"] is True

    trading_log_store.mark_trade_reviewed(str(db_path), "T1")
    assert trading_log_store.load_reviewed_trade_ids(str(db_path)) == ["T1"]

    trading_log_store.store_trade_review(
        str(db_path),
        review_id="review_T1",
        trade_id="T1",
        symbol="BTCUSD",
        reviewed_at="2026-04-26T00:01:00",
        source_path="trading_logs/review_T1.md",
        summary="summary",
        risk_assessment="risk",
        lessons_learned="lesson",
        markdown_body="# Trade Review Log",
        raw_payload={"closed_trade": {"trade_id": "T1"}},
    )

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM tracked_positions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM reviewed_trade_ids").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM trade_reviews").fetchone()[0] == 1
