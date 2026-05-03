import asyncio
import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from zoneinfo import ZoneInfo

from croniter import croniter

from backend.features.trading.persistence.trigger_store import (
    get_active_schedule_rules,
    update_rule_last_triggered,
    create_trigger_run,
    add_trigger_event
)
from backend.services.trading_service import run_trading_workflow_async
from backend.features.trading.market_hours import is_market_open

logger = logging.getLogger(__name__)

def get_next_interval_time(last_triggered_at_iso: Optional[str], interval_seconds: int) -> datetime:
    """Calculates next trigger time for interval rules."""
    if not last_triggered_at_iso:
        return datetime.now(timezone.utc)
    
    last_dt = datetime.fromisoformat(last_triggered_at_iso)
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
        
    return last_dt + timedelta(seconds=interval_seconds)

def get_next_cron_time(cron_expression: str, tz_name: str = "UTC", now: Optional[datetime] = None) -> Optional[datetime]:
    """Calculates next trigger time for cron rules."""
    try:
        tz = ZoneInfo(tz_name)
        if now is None:
            now = datetime.now(tz)
        else:
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            now = now.astimezone(tz)
            
        iter = croniter(cron_expression, now)
        next_dt = iter.get_next(datetime)
        # Convert to UTC for storage
        return next_dt.astimezone(timezone.utc)
    except Exception as e:
        logger.error(f"Error calculating next cron time: {e}")
        return None

class TriggerScheduler:
    def __init__(self, check_interval: int = 10):
        self.check_interval = check_interval
        self.running = False
        self.task = None
        self._rule_locks = {} # To prevent overlapping execution of the same rule

    async def start(self):
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._loop())
        logger.info("⏰ Trigger Scheduler started.")

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("⏰ Trigger Scheduler stopped.")

    async def _loop(self):
        while self.running:
            try:
                await self._check_and_trigger()
            except Exception as e:
                logger.error(f"❌ Error in scheduler loop: {e}")
            await asyncio.sleep(self.check_interval)

    async def _check_and_trigger(self):
        rules = get_active_schedule_rules()
        now = datetime.now(timezone.utc)

        for rule in rules:
            rule_id = rule["rule_id"]
            log_base = {
                "rule_id": rule_id,
                "symbol": rule.get("symbol"),
                "mode": rule.get("mode"),
                "strategy_override": rule.get("strategy_override"),
            }
            
            # 1. Check if it's time to trigger
            should_trigger = False
            next_trigger_at = rule.get("next_trigger_at")
            
            if not next_trigger_at:
                should_trigger = True
            else:
                next_dt = datetime.fromisoformat(next_trigger_at)
                if next_dt.tzinfo is None:
                    next_dt = next_dt.replace(tzinfo=timezone.utc)
                if now >= next_dt:
                    should_trigger = True

            if not should_trigger:
                logger.debug(
                    "⏰ Scheduler: Skipping rule %s (%s). Reason: not_due. Next: %s",
                    rule_id,
                    rule.get("symbol"),
                    next_trigger_at,
                    extra={
                        **log_base,
                        "event": "trigger.scheduler.rule_skipped",
                        "skip_reason": "not_due",
                        "next_trigger_at": next_trigger_at,
                    },
                )
                continue

            # 2. Calculate next trigger time for all cases where it was 'due'
            schedule_type = rule.get("schedule_type", "interval")
            if schedule_type == "cron":
                cron_expr = rule.get("cron_expression")
                if not cron_expr:
                    logger.warning(f"Rule {rule_id} is cron but has no expression. Skipping.")
                    continue
                new_next_dt = get_next_cron_time(cron_expr, rule.get("timezone", "UTC"))
            else: # interval
                interval = rule.get("interval_seconds") or 900
                new_next_dt = now + timedelta(seconds=interval)
            
            if not new_next_dt:
                logger.error(f"Failed to calculate next trigger for rule {rule_id}. Skipping.")
                continue
            
            new_next_iso = new_next_dt.replace(microsecond=0).isoformat()
            now_iso = now.replace(microsecond=0).isoformat()

            # 3. Check market hours
            if rule.get("market_hours_only") and not is_market_open(now, symbol=rule.get("symbol")):
                # Update next trigger to avoid hot-looping during closed market
                update_rule_last_triggered(None, rule_id, now_iso, new_next_iso)
                logger.info(
                    "⏰ Scheduler: Skipping rule %s (%s). Reason: market_hours_skip. Next: %s",
                    rule_id, rule.get("symbol"), new_next_iso,
                    extra={
                        **log_base,
                        "event": "trigger.scheduler.rule_skipped",
                        "skip_reason": "market_hours_skip",
                        "next_trigger_at": new_next_iso,
                    },
                )
                continue

            # 4. Check lock
            if self._rule_locks.get(rule_id):
                # Log a 'skipped' run record for lock
                update_rule_last_triggered(None, rule_id, now_iso, new_next_iso)
                trigger_id = create_trigger_run(None, {
                    "rule_id": rule_id,
                    "symbol": rule["symbol"],
                    "timeframes": json.loads(rule["timeframes_json"]),
                    "mode": rule["mode"],
                    "status": "skipped",
                    "error_message": "Previous run still in progress (lock active)",
                    "scheduled_at": now_iso
                })
                add_trigger_event(None, trigger_id, "skipped", message="Skipped due to active lock")
                logger.warning(
                    "⏰ Scheduler: Skipping rule %s (%s). Reason: lock_skip (Previous run in progress). Next: %s",
                    rule_id, rule.get("symbol"), new_next_iso,
                    extra={
                        **log_base,
                        "event": "trigger.scheduler.rule_skipped",
                        "skip_reason": "lock_skip",
                        "trigger_id": trigger_id,
                        "next_trigger_at": new_next_iso,
                    },
                )
                continue
            
            # 5. Update rule and execute
            update_rule_last_triggered(None, rule_id, now_iso, new_next_iso)
            logger.info(
                "⏰ Scheduler: Triggering rule %s (%s). Next: %s",
                rule_id,
                rule.get("symbol"),
                new_next_iso,
                extra={**log_base, "event": "trigger.scheduler.rule_due", "next_trigger_at": new_next_iso},
            )
            asyncio.create_task(self._execute_rule(rule))

    async def _execute_rule(self, rule: Dict[str, Any]):
        rule_id = rule["rule_id"]
        self._rule_locks[rule_id] = True
        
        trigger_id = None
        try:
            symbol = rule["symbol"]
            timeframes = json.loads(rule["timeframes_json"])
            mode = rule["mode"]
            strategy_override = rule.get("strategy_override")
            
            # 1. Create run record
            trigger_id = create_trigger_run(None, {
                "rule_id": rule_id,
                "symbol": symbol,
                "timeframes": timeframes,
                "mode": mode,
                "strategy_override": strategy_override,
                "status": "scheduled",
                "scheduled_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            })
            
            add_trigger_event(None, trigger_id, "scheduled", message=f"Triggered by rule: {rule['name']}")
            
            # 2. Run workflow
            await run_trading_workflow_async(
                symbol=symbol,
                timeframes=timeframes,
                mode=mode,
                strategy_override=strategy_override,
                trigger_id=trigger_id,
                rule_id=rule_id
            )
            
        except Exception as e:
            logger.error(f"❌ Error executing rule {rule_id}: {e}")
            if trigger_id:
                add_trigger_event(None, trigger_id, "failed", message=str(e))
        finally:
            self._rule_locks[rule_id] = False

# Global instance
scheduler = TriggerScheduler()
