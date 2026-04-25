from backend.core.state_models import Order, OrderResult
from backend.core.exceptions import GuardrailViolationError, OrderExecutionError
from backend.features.trading.guardrails import (
    validate_daily_drawdown_lock,
    validate_max_trades_per_day,
    validate_risk_reward_ratio,
    enforce_one_percent_rule,
    validate_sl_tp_modification_limit
)
from backend.features.trading.mt5_adapter import MT5Client
import datetime

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
        account_balance: float
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
        if not validate_risk_reward_ratio(order.entry_price, order.sl_price, order.tp_price):
            raise GuardrailViolationError("Invalid Risk/Reward ratio (must be >= 2.0).")

        # 4. Rule 1: Enforce 1% Rule for Lot Size
        safe_lot_size = enforce_one_percent_rule(account_balance, order.entry_price, order.sl_price)
        if safe_lot_size <= 0:
            raise GuardrailViolationError("Calculated lot size is 0 or negative.")
        
        order.lot_size = safe_lot_size # Override AI's lot size

        # 5. Execute via MT5 Adapter
        try:
            # Assuming mt5.send_order returns a ticket ID or dict. We adapt it.
            # In a real scenario we need to match the signature of mt5.send_order
            # For now, we simulate success or pass to actual adapter if it exists.
            result = self.mt5.send_order(
                symbol=order.symbol,
                order_type=order.action.value,
                volume=order.lot_size,
                price=order.entry_price,
                sl=order.sl_price,
                tp=order.tp_price
            )
            return OrderResult(
                success=True,
                ticket=result.get("order"),
                executed_price=result.get("price"),
                timestamp=datetime.datetime.now().isoformat()
            )
        except Exception as e:
            raise OrderExecutionError(f"MT5 execution failed: {str(e)}")
