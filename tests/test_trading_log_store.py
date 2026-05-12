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
        process_quality="mixed",
        outcome_quality="neutral",
        trade_quality_label="mixed_trade",
        rule_adherence=True,
        lessons_learned="lesson",
        markdown_body="# Trade Review Log",
        raw_payload={"closed_trade": {"trade_id": "T1"}},
    )

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM tracked_positions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM reviewed_trade_ids").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM trade_reviews").fetchone()[0] == 1
        row = conn.execute(
            "SELECT process_quality, outcome_quality, trade_quality_label, rule_adherence FROM trade_reviews WHERE review_id = ?",
            ("review_T1",),
        ).fetchone()
        assert row == ("mixed", "neutral", "mixed_trade", 1)


def test_trade_journal_tracks_open_close_and_review(tmp_path):
    db_path = tmp_path / "trading_logs.sqlite"

    from backend.features.trading.persistence import trading_log_store

    trading_log_store.upsert_trade_journal(
        str(db_path),
        {
            "trade_id": "T1",
            "trigger_id": "trig_1",
            "workflow_run_id": "run_1",
            "rule_id": "rule_1",
            "mode": "paper",
            "symbol": "BTCUSD",
            "action": "BUY",
            "status": "open",
            "opened_at": "2026-04-26T00:00:00",
            "entry_price": 100.0,
            "sl": 90.0,
            "tp": 120.0,
            "lot_size": 0.1,
            "decision_context": {"trigger_id": "trig_1", "strategy_hypothesis": {"selected_strategy": "test"}},
            "order_result": {"success": True},
        },
    )
    trading_log_store.upsert_trade_journal(
        str(db_path),
        {
            "trade_id": "T1",
            "status": "reviewed",
            "closed_trade": {
                "trade_id": "T1",
                "exit_time": "2026-04-26T01:00:00",
                "exit_reason": "Take Profit",
                "pnl": 20.0,
            },
            "review_id": "review_T1",
            "review_log": {
                "trade_summary": "summary",
                "risk_assessment": "risk",
                "process_quality": "mixed",
                "outcome_quality": "neutral",
                "trade_quality_label": "mixed_trade",
                "rule_adherence": True,
                "lessons_learned": "lesson",
            },
        },
    )

    journals = trading_log_store.get_trade_journals_by_trigger(str(db_path), "trig_1")
    assert len(journals) == 1
    assert journals[0]["trade_id"] == "T1"
    assert journals[0]["status"] == "reviewed"
    assert journals[0]["closed_trade"]["exit_reason"] == "Take Profit"
    assert journals[0]["review_log"]["lessons_learned"] == "lesson"
    assert journals[0]["review_log"]["trade_quality_label"] == "mixed_trade"
