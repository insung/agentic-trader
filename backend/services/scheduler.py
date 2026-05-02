import asyncio
import os
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

from backend.features.trading.persistence.trigger_store import (
    get_active_schedule_rules,
    update_rule_last_triggered,
    create_trigger_run,
    add_trigger_event
)
from backend.services.trading_service import run_trading_workflow_async
from backend.features.trading.market_hours import is_market_open

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
        print("⏰ Trigger Scheduler started.")

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        print("⏰ Trigger Scheduler stopped.")

    async def _loop(self):
        while self.running:
            try:
                await self._check_and_trigger()
            except Exception as e:
                print(f"❌ Error in scheduler loop: {e}")
            await asyncio.sleep(self.check_interval)

    async def _check_and_trigger(self):
        rules = get_active_schedule_rules()
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        for rule in rules:
            rule_id = rule["rule_id"]
            
            # Check if market hours rule applies
            if rule.get("market_hours_only") and not is_market_open(now):
                continue

            # Check if it's time to trigger
            should_trigger = False
            next_trigger_at = rule.get("next_trigger_at")
            
            if not next_trigger_at:
                # First time: trigger now or set next
                should_trigger = True
            else:
                next_dt = datetime.fromisoformat(next_trigger_at)
                if now >= next_dt:
                    should_trigger = True

            if should_trigger:
                if self._rule_locks.get(rule_id):
                    # Still running, skip
                    continue
                
                # Calculate next trigger time
                interval = rule.get("interval_seconds") or 900 # Default 15m
                # Align to interval if possible (e.g. every 15m of the hour)
                # For now just simple add
                new_next_dt = now + timedelta(seconds=interval)
                new_next_iso = new_next_dt.isoformat()
                
                # Update rule in DB
                update_rule_last_triggered(None, rule_id, now_iso, new_next_iso)
                
                # Run in background
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
                "scheduled_at": datetime.now(timezone.utc).isoformat()
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
            print(f"❌ Error executing rule {rule_id}: {e}")
            if trigger_id:
                add_trigger_event(None, trigger_id, "failed", message=str(e))
        finally:
            self._rule_locks[rule_id] = False

# Global instance
scheduler = TriggerScheduler()
