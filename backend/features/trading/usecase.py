import datetime
import logging

from backend.core.state_models import Order, OrderResult
from backend.core.exceptions import GuardrailViolationError, OrderExecutionError
from backend.features.trading.guardrails import (
    validate_daily_drawdown_lock,
    validate_max_trades_per_day,
    validate_order_prices,
    enforce_one_percent_rule,
    validate_sl_tp_modification_limit
)
from backend.features.trading.adapters.mt5_execution import MT5Client

logger = logging.getLogger(__name__)

def is_mt5_success(result: dict) -> tuple[bool, str]:
    """
    Pure helper to determine if an MT5 execution was truly successful.
    
    Criteria:
    1. Result must not be empty.
    2. retcode must be 10009 (TRADE_RETCODE_DONE) or 10008 (TRADE_RETCODE_PLACED).
    3. ticket (or order) must be > 0.
    4. executed_price (or price) must be > 0.
    """
    if not result:
        return False, "Empty response from MT5 adapter"
    
    retcode = result.get("retcode")
    # 10009: Done, 10008: Placed (for some brokers/orders)
    if retcode not in [10008, 10009]:
        return False, f"MT5 error retcode: {retcode}, comment: {result.get('comment', 'No comment')}"
    
    ticket = result.get("order") or result.get("ticket") or 0
    if ticket <= 0:
        return False, f"Invalid ticket ID: {ticket}"
    
    price = result.get("price") or result.get("executed_price") or 0.0
    if price <= 0:
        return False, f"Invalid executed price: {price}"
    
    return True, ""

class TradeExecutionUseCase:
    """
    Application service (Use Case) for executing trades.
    Coordinates between Guardrails (Functional Core) and MT5 (Infrastructure).
    """
    def __init__(self, mt5_client: MT5Client):
        self.mt5 = mt5_client

    def execute_trade(
        self, 
        order: Order, 
        current_loss_pct: float, 
        today_trade_count: int, 
        account_balance: float,
        risk_per_trade_pct: float = 0.01,
        trigger_id: str | None = None,
        workflow_run_id: str | None = None,
        rule_id: str | None = None,
        mode: str = "live",
    ) -> OrderResult:
        """
        Executes a trade after passing all strict guardrails.
        """
        # 1. Rule 2: Daily Drawdown Lock
        if not validate_daily_drawdown_lock(current_loss_pct):
            raise GuardrailViolationError("Daily drawdown limit exceeded (>2.0%).")

        # 2. Rule 3: Max Trades Per Day
        if not validate_max_trades_per_day(today_trade_count):
            raise GuardrailViolationError("Maximum daily trades exceeded (>=3).")

        # 3. Rule 4: Risk/Reward Ratio
        if not validate_order_prices(order.action.value, order.entry_price, order.sl_price, order.tp_price):
            raise GuardrailViolationError("Invalid SL/TP direction or Risk/Reward ratio (must be >= 2.0).")

        # 4. Rule 1: Enforce configured risk-percent Rule for Lot Size
        safe_lot_size = enforce_one_percent_rule(
            account_balance,
            order.entry_price,
            order.sl_price,
            risk_pct=risk_per_trade_pct,
        )
        if safe_lot_size <= 0:
            raise GuardrailViolationError("Calculated lot size is 0 or negative.")
        
        order.lot_size = safe_lot_size # Override AI's lot size
        log_base = {
            "trigger_id": trigger_id,
            "workflow_run_id": workflow_run_id,
            "rule_id": rule_id,
            "symbol": order.symbol,
            "mode": mode,
            "final_action": order.action.value,
            "lot_size": order.lot_size,
        }
        logger.info(
            "📐 Trade execution risk lot calculated for %s. lot=%.2f",
            order.symbol,
            order.lot_size,
            extra={**log_base, "event": "trigger.risk_lot.calculated"},
        )

        # 5. Execute via MT5 Adapter
        try:
            # result is guaranteed to be a dict by the adapter (Step 4)
            logger.info(
                "📤 MT5 execution requested for %s.",
                order.symbol,
                extra={
                    **log_base,
                    "event": "trigger.execution.requested",
                    "requested_entry_price": order.entry_price,
                    "requested_sl": order.sl_price,
                    "requested_tp": order.tp_price,
                },
            )
            result = self.mt5.send_order(
                symbol=order.symbol,
                order_type=order.action.value,
                volume=order.lot_size,
                price=order.entry_price,
                sl=order.sl_price,
                tp=order.tp_price
            )
            
            if not isinstance(result, dict):
                # Defensive check for safety
                result = {"retcode": -99, "comment": f"Unexpected result type: {type(result)}", "raw": str(result)}

            logger.info(
                "📥 MT5 execution response for %s. retcode=%s order=%s price=%s",
                order.symbol,
                result.get("retcode"),
                result.get("order") or result.get("ticket"),
                result.get("price") or result.get("executed_price"),
                extra={
                    **log_base,
                    "event": "trigger.execution.mt5_response",
                    "mt5_retcode": result.get("retcode"),
                    "mt5_order": result.get("order") or result.get("ticket"),
                    "mt5_price": result.get("price") or result.get("executed_price"),
                },
            )

            # Step 3: Use helper to determine actual success
            is_success, failure_reason = is_mt5_success(result)
            logger.info(
                "🧾 MT5 success predicate for %s. success=%s reason=%s",
                order.symbol,
                is_success,
                failure_reason or "",
                extra={
                    **log_base,
                    "event": "trigger.execution.success_predicate",
                    "success": is_success,
                    "failure_reason": failure_reason or None,
                },
            )
            
            # Step 2 & 3 & 4: Enriched OrderResult with preserved raw response
            return OrderResult(
                success=is_success,
                ticket=result.get("order"),
                executed_price=result.get("price"),
                timestamp=datetime.datetime.now().isoformat(),
                
                # Context & Request
                mode=mode,
                symbol=order.symbol,
                action=order.action.value,
                requested_lot=order.lot_size,
                requested_entry_price=order.entry_price,
                requested_sl=order.sl_price,
                requested_tp=order.tp_price,
                risk_pct=risk_per_trade_pct,
                safe_lot=order.lot_size,
                
                # MT5 Response mapping
                mt5_retcode=result.get("retcode"),
                mt5_comment=result.get("comment"),
                mt5_order=result.get("order"),
                mt5_deal=result.get("deal"),
                mt5_price=result.get("price"),
                mt5_request_id=result.get("request_id"),
                
                # Full record (JSON serializable dict)
                raw_response=result,
                failure_reason=failure_reason if not is_success else None
            )
        except Exception as e:
            # For unexpected infrastructure exceptions
            logger.exception(
                "💥 MT5 execution raised infrastructure error for %s.",
                order.symbol,
                extra={
                    **log_base,
                    "event": "trigger.execution.failed",
                    "failure_reason": str(e),
                },
            )
            return OrderResult(
                success=False,
                error_message=str(e),
                failure_reason=f"Infrastructure error: {str(e)}",
                timestamp=datetime.datetime.now().isoformat(),
                mode=mode,
                symbol=order.symbol,
                action=order.action.value,
                raw_response={"exception": str(e)}
            )
