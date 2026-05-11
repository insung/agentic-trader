from datetime import datetime, timezone

from backend.features.trading.risk_controls import (
    apply_live_trigger_cooldown,
    derive_live_risk_state,
    has_open_tracked_position,
)


def test_derive_live_risk_state_counts_equity_gap_and_entry_deals():
    account_info = {"balance": 10000.0, "equity": 9700.0}
    now = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)
    deals_history = [
        {"time": int(now.timestamp()), "symbol": "BTCUSD", "position_id": 101, "entry": "IN"},
        {"time": int(now.timestamp()), "symbol": "BTCUSD", "position_id": 101, "entry": "OUT"},
        {"time": int(now.timestamp()), "symbol": "BTCUSD", "position_id": 202, "entry": "IN"},
        {"time": int(now.timestamp()), "symbol": "ETHUSD", "position_id": 303, "entry": "IN"},
    ]

    current_loss_pct, today_trade_count = derive_live_risk_state(
        account_info=account_info,
        symbol="BTCUSD",
        deals_history=deals_history,
        now=now,
    )

    assert current_loss_pct == 3.0
    assert today_trade_count == 2


def test_has_open_tracked_position_detects_matching_live_symbol():
    tracked_positions = [
        {"symbol": "BTCUSD", "mode": "live", "trade_id": "a"},
        {"symbol": "ETHUSD", "mode": "paper", "trade_id": "b"},
    ]

    assert has_open_tracked_position(tracked_positions, symbol="BTCUSD", mode="live") is True
    assert has_open_tracked_position(tracked_positions, symbol="BTCUSD", mode="paper") is False
    assert has_open_tracked_position(tracked_positions, symbol="XAUUSD", mode="live") is False


def test_apply_live_trigger_cooldown_enforces_minimum_gap_for_live_mode():
    now = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)
    base_next = datetime(2026, 5, 11, 12, 5, tzinfo=timezone.utc)

    next_live = apply_live_trigger_cooldown(base_next, now=now, mode="live", cooldown_seconds=1800)
    next_paper = apply_live_trigger_cooldown(base_next, now=now, mode="paper", cooldown_seconds=1800)

    assert next_live == datetime(2026, 5, 11, 12, 30, tzinfo=timezone.utc)
    assert next_paper == base_next
