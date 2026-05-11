"""Shared live-risk helpers for guardrails and scheduling."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional, Tuple


LIVE_TRIGGER_COOLDOWN_SECONDS = 30 * 60


def _coerce_datetime(value: Any, default: Optional[datetime] = None) -> Optional[datetime]:
    if value is None:
        return default
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            except (TypeError, ValueError):
                return default
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return default


def _is_same_utc_day(moment: datetime, reference: datetime) -> bool:
    return moment.astimezone(timezone.utc).date() == reference.astimezone(timezone.utc).date()


def _deal_entry_value(deal: Dict[str, Any]) -> Any:
    return deal.get("entry", deal.get("deal_entry"))


def _is_entry_deal(deal: Dict[str, Any]) -> bool:
    entry = _deal_entry_value(deal)
    if entry is None:
        return False
    if isinstance(entry, str):
        return entry.upper() in {"IN", "DEAL_ENTRY_IN", "BUY", "SELL"}
    try:
        return int(entry) == 0
    except (TypeError, ValueError):
        return False


def _deal_unique_key(deal: Dict[str, Any]) -> Optional[str]:
    for key in ("position_id", "order", "ticket", "deal"):
        value = deal.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def derive_live_risk_state(
    *,
    account_info: Dict[str, Any],
    symbol: str,
    deals_history: Optional[Iterable[Dict[str, Any]]] = None,
    now: Optional[datetime] = None,
) -> Tuple[float, int]:
    """Return (current_loss_pct, today_trade_count) for live guardrails."""
    reference_now = _coerce_datetime(now, datetime.now(timezone.utc))
    balance = float(account_info.get("balance") or 0.0)
    equity = float(account_info.get("equity") or account_info.get("balance") or 0.0)

    if balance > 0:
        current_loss_pct = max(0.0, ((balance - equity) / balance) * 100.0)
    else:
        current_loss_pct = 0.0

    if not deals_history:
        return round(current_loss_pct, 4), 0

    today_trade_keys = set()
    for deal in deals_history:
        if str(deal.get("symbol", "")).upper() != str(symbol).upper():
            continue
        if not _is_entry_deal(deal):
            continue
        deal_time = _coerce_datetime(deal.get("time") or deal.get("timestamp") or deal.get("created_at"))
        if deal_time is None or not _is_same_utc_day(deal_time, reference_now):
            continue
        unique_key = _deal_unique_key(deal)
        if unique_key is not None:
            today_trade_keys.add(unique_key)

    return round(current_loss_pct, 4), len(today_trade_keys)


def has_open_tracked_position(
    tracked_positions: Iterable[Dict[str, Any]],
    *,
    symbol: str,
    mode: Optional[str] = None,
) -> bool:
    symbol_upper = str(symbol).upper()
    mode_lower = mode.lower() if isinstance(mode, str) else None

    for position in tracked_positions or []:
        if str(position.get("symbol", "")).upper() != symbol_upper:
            continue
        if mode_lower and str(position.get("mode", "")).lower() != mode_lower:
            continue
        if position.get("exit_time") or position.get("closed") or str(position.get("status", "")).lower() in {"closed", "reviewed", "finished"}:
            continue
        return True
    return False


def apply_live_trigger_cooldown(
    next_trigger_at: datetime,
    *,
    now: Optional[datetime] = None,
    mode: str = "paper",
    cooldown_seconds: int = LIVE_TRIGGER_COOLDOWN_SECONDS,
) -> datetime:
    if mode.lower() != "live" or cooldown_seconds <= 0:
        return next_trigger_at

    reference_now = _coerce_datetime(now, datetime.now(timezone.utc))
    cooldown_floor = reference_now + timedelta(seconds=cooldown_seconds)
    candidate = _coerce_datetime(next_trigger_at, reference_now)
    return max(candidate, cooldown_floor)