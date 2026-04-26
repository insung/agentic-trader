"""
Closed-trade review coordination.

The decision graph creates trade intent. This module persists opened positions
and triggers the Risk Reviewer only after a position is actually closed.
"""
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.core.state_models import AgentStateSchema
from backend.workflows.nodes import risk_reviewer_node
from backend.features.trading.trading_log_store import (
    DEFAULT_TRADING_LOG_DB_PATH,
    load_reviewed_trade_ids as load_reviewed_trade_ids_sqlite,
    load_tracked_positions as load_tracked_positions_sqlite,
    mark_trade_reviewed as mark_trade_reviewed_sqlite,
    replace_reviewed_trade_ids,
    replace_tracked_positions,
)
from backend.features.trading.mt5_adapter import (
    get_current_price,
    get_deals_history,
    get_open_positions,
)


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TRADING_LOGS_DIR = os.path.join(PROJECT_ROOT, "trading_logs")
TRACKED_POSITIONS_PATH = os.path.join(TRADING_LOGS_DIR, "tracked_positions.json")
REVIEWED_TRADES_PATH = os.path.join(TRADING_LOGS_DIR, "reviewed_trades.json")
TRADING_LOG_DB_PATH = DEFAULT_TRADING_LOG_DB_PATH


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def load_tracked_positions() -> List[Dict[str, Any]]:
    positions = _read_json(TRACKED_POSITIONS_PATH, None)
    if positions is not None:
        return positions
    return load_tracked_positions_sqlite(TRADING_LOG_DB_PATH)


def save_tracked_positions(positions: List[Dict[str, Any]]) -> None:
    _write_json(TRACKED_POSITIONS_PATH, positions)
    replace_tracked_positions(TRADING_LOG_DB_PATH, positions)


def load_reviewed_trade_ids() -> List[str]:
    reviewed = _read_json(REVIEWED_TRADES_PATH, None)
    if reviewed is not None:
        return reviewed
    return load_reviewed_trade_ids_sqlite(TRADING_LOG_DB_PATH)


def mark_trade_reviewed(trade_id: str) -> None:
    reviewed = load_reviewed_trade_ids()
    if trade_id not in reviewed:
        reviewed.append(trade_id)
        _write_json(REVIEWED_TRADES_PATH, reviewed)
        mark_trade_reviewed_sqlite(TRADING_LOG_DB_PATH, trade_id)


def _dump_if_model(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def build_decision_context(final_state: Dict[str, Any], order_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "raw_data": final_state.get("raw_data", ""),
        "account_info": _dump_if_model(final_state.get("account_info", {})),
        "tech_summary": _dump_if_model(final_state.get("tech_summary", {})),
        "strategy_hypothesis": _dump_if_model(final_state.get("strategy_hypothesis", {})),
        "final_order": _dump_if_model(final_state.get("final_order", {})),
        "order_result": _dump_if_model(order_result or final_state.get("order_result", {})),
    }


def track_open_position(
    *,
    mode: str,
    symbol: str,
    action: str,
    entry_price: float,
    sl: float,
    tp: float,
    lot_size: float,
    order_result: Dict[str, Any],
    decision_context: Dict[str, Any],
) -> Dict[str, Any]:
    ticket = order_result.get("ticket") or order_result.get("order") or order_result.get("deal")
    trade_id = str(ticket or f"{symbol}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    tracked = {
        "trade_id": trade_id,
        "ticket": ticket,
        "mode": mode,
        "symbol": symbol,
        "action": action.upper(),
        "entry_time": datetime.now().isoformat(),
        "entry_price": entry_price,
        "sl": sl,
        "tp": tp,
        "lot_size": lot_size,
        "order_result": order_result,
        "decision_context": decision_context,
    }

    positions = [p for p in load_tracked_positions() if str(p.get("trade_id")) != trade_id]
    positions.append(tracked)
    save_tracked_positions(positions)
    return tracked


def _normalize_final_order(order: Dict[str, Any], symbol: str) -> Optional[Dict[str, Any]]:
    if not order:
        return None
    normalized = dict(order)
    normalized.setdefault("symbol", symbol)
    normalized.setdefault("entry_price", 0.0)
    normalized.setdefault("sl_price", normalized.get("sl", 0.0))
    normalized.setdefault("tp_price", normalized.get("tp", 0.0))
    normalized.setdefault("lot_size", 0.0)
    normalized.setdefault("reasoning", normalized.get("final_reasoning", ""))
    return normalized


def _normalize_order_result(order_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not order_result:
        return None
    normalized = dict(order_result)
    normalized.setdefault("success", True)
    normalized.setdefault("timestamp", datetime.now().isoformat())
    ticket = normalized.get("ticket")
    if ticket is not None:
        try:
            normalized["ticket"] = int(ticket)
        except (TypeError, ValueError):
            normalized["ticket_ref"] = str(ticket)
            normalized["ticket"] = None
    return normalized


def review_closed_trade(decision_context: Dict[str, Any], closed_trade: Dict[str, Any]) -> Dict[str, Any]:
    symbol = closed_trade.get("symbol", "")
    state = AgentStateSchema(
        symbol=symbol,
        raw_data=decision_context.get("raw_data", ""),
        account_info=decision_context.get("account_info", {}),
        tech_summary=decision_context.get("tech_summary", {}),
        strategy_hypothesis=decision_context.get("strategy_hypothesis", {}),
        final_order=_normalize_final_order(decision_context.get("final_order", {}), symbol),
        order_result=_normalize_order_result(decision_context.get("order_result", {})),
        decision_context=decision_context,
        closed_trade=closed_trade,
    )
    return risk_reviewer_node(state)


def _calculate_pnl(position: Dict[str, Any], exit_price: float) -> float:
    entry_price = float(position.get("entry_price", 0.0))
    lot_size = float(position.get("lot_size", 0.0))
    if position.get("action", "").upper() == "BUY":
        return round((exit_price - entry_price) * lot_size, 2)
    return round((entry_price - exit_price) * lot_size, 2)


def _build_closed_trade(position: Dict[str, Any], result: str, exit_reason: str, exit_price: float, pnl: float) -> Dict[str, Any]:
    return {
        "trade_id": str(position.get("trade_id")),
        "ticket": position.get("ticket"),
        "mode": position.get("mode"),
        "symbol": position.get("symbol"),
        "action": position.get("action"),
        "entry_time": position.get("entry_time"),
        "exit_time": datetime.now().isoformat(),
        "entry_price": position.get("entry_price"),
        "exit_price": exit_price,
        "sl": position.get("sl"),
        "tp": position.get("tp"),
        "lot_size": position.get("lot_size"),
        "result": result,
        "exit_reason": exit_reason,
        "pnl": pnl,
    }


def _close_paper_position(position: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    price = get_current_price(position.get("symbol", ""))
    if not price:
        return None

    action = position.get("action", "").upper()
    sl = float(position.get("sl", 0.0))
    tp = float(position.get("tp", 0.0))
    bid = float(price.get("bid") or price.get("last") or 0.0)
    ask = float(price.get("ask") or price.get("last") or 0.0)

    if action == "BUY":
        if bid <= sl:
            return _build_closed_trade(position, "SL_HIT", "Stop Loss", sl, _calculate_pnl(position, sl))
        if bid >= tp:
            return _build_closed_trade(position, "TP_HIT", "Take Profit", tp, _calculate_pnl(position, tp))
    elif action == "SELL":
        if ask >= sl:
            return _build_closed_trade(position, "SL_HIT", "Stop Loss", sl, _calculate_pnl(position, sl))
        if ask <= tp:
            return _build_closed_trade(position, "TP_HIT", "Take Profit", tp, _calculate_pnl(position, tp))

    return None


def _find_live_closed_trade(position: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ticket = position.get("ticket")
    if ticket is None:
        return None

    open_ticket_ids = {
        str(p.get("ticket"))
        for p in get_open_positions(position.get("symbol"))
        if p.get("ticket") is not None
    }
    if str(ticket) in open_ticket_ids:
        return None

    matching_deals = []
    for deal in get_deals_history():
        identifiers = {str(deal.get("position_id")), str(deal.get("order")), str(deal.get("ticket"))}
        if str(ticket) in identifiers:
            matching_deals.append(deal)

    if not matching_deals:
        return None

    close_deal = matching_deals[-1]
    exit_price = float(close_deal.get("price") or position.get("entry_price") or 0.0)
    pnl = round(float(close_deal.get("profit") or _calculate_pnl(position, exit_price)), 2)
    action = position.get("action", "").upper()
    sl = float(position.get("sl", 0.0))
    tp = float(position.get("tp", 0.0))

    result = "CLOSED"
    exit_reason = "Closed"
    if (action == "BUY" and exit_price <= sl) or (action == "SELL" and exit_price >= sl):
        result = "SL_HIT"
        exit_reason = "Stop Loss"
    elif (action == "BUY" and exit_price >= tp) or (action == "SELL" and exit_price <= tp):
        result = "TP_HIT"
        exit_reason = "Take Profit"

    return _build_closed_trade(position, result, exit_reason, exit_price, pnl)


def reconcile_tracked_positions() -> List[Dict[str, Any]]:
    """Review closed tracked positions and keep still-open positions persisted."""
    reviewed_ids = set(load_reviewed_trade_ids())
    remaining = []
    reviewed = []

    for position in load_tracked_positions():
        trade_id = str(position.get("trade_id"))
        if trade_id in reviewed_ids:
            continue

        if position.get("mode") == "paper":
            closed_trade = _close_paper_position(position)
        else:
            closed_trade = _find_live_closed_trade(position)

        if not closed_trade:
            remaining.append(position)
            continue

        review_result = review_closed_trade(position.get("decision_context", {}), closed_trade)
        if review_result.get("error_flag"):
            remaining.append(position)
            continue

        mark_trade_reviewed(trade_id)
        reviewed.append({
            "trade_id": trade_id,
            "closed_trade": closed_trade,
            "review_log": review_result.get("review_log", {}),
        })

    save_tracked_positions(remaining)
    return reviewed
