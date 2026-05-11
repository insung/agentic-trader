import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.scheduler import TriggerScheduler


@pytest.mark.asyncio
async def test_scheduler_blocks_live_rule_when_open_tracked_position_exists():
    scheduler = TriggerScheduler(check_interval=1)
    rule = {
        "rule_id": "rule-1",
        "name": "btc-veb-live-cron",
        "symbol": "BTCUSD",
        "timeframes_json": '["M5", "M15"]',
        "mode": "live",
        "schedule_type": "cron",
        "cron_expression": "*/5 * * * *",
        "timezone": "UTC",
        "market_hours_only": 0,
        "next_trigger_at": None,
        "strategy_override": "Volatility Expansion Breakout",
    }

    with patch("backend.services.scheduler.get_active_schedule_rules", return_value=[rule]), \
         patch("backend.services.scheduler.load_tracked_positions", return_value=[{"symbol": "BTCUSD", "mode": "live", "trade_id": "abc"}]), \
         patch("backend.services.scheduler.is_market_open", return_value=True), \
         patch("backend.services.scheduler.update_rule_last_triggered") as mock_update, \
         patch("backend.services.scheduler.create_trigger_run") as mock_create_run, \
         patch("backend.services.scheduler.add_trigger_event") as mock_add_event, \
         patch("backend.services.scheduler.asyncio.create_task") as mock_create_task:
        await scheduler._check_and_trigger()

    assert mock_create_task.call_count == 0
    mock_create_run.assert_called_once()
    assert mock_create_run.call_args.kwargs == {}
    assert mock_add_event.call_count >= 1
    mock_update.assert_called_once()
