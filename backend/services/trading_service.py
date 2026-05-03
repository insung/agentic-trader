import os
import json
import asyncio
import traceback
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

from backend.workflows.graph import get_compiled_graph
from backend.features.trading.adapters.mt5_execution import MT5Client
from backend.features.trading.adapters.paper_execution import execute_mock_order
from backend.core.state_models import Order, OrderAction, OrderResult
from backend.features.trading.guardrails import validate_order_prices, enforce_one_percent_rule
from backend.features.trading.strategy_validators import validate_strategy_setup
from backend.features.trading.operations.position_tracker import build_decision_context, track_open_position
from backend.features.trading.usecase import TradeExecutionUseCase
from backend.features.trading.persistence.trigger_store import (
    create_trigger_run,
    update_trigger_run,
    add_trigger_event,
    save_trigger_snapshot
)

def _model_to_dict(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_model_to_dict(v) for v in value]
    if isinstance(value, dict):
        return {k: _model_to_dict(v) for k, v in value.items()}
    return value

def _pick_agent_fields(data: Dict[str, Any], allowed_fields: List[str]) -> Dict[str, Any]:
    source = _model_to_dict(data) or {}
    return {field: source.get(field) for field in allowed_fields if field in source}

async def run_trading_workflow_async(
    symbol: str, 
    timeframes: List[str] = None, 
    mode: str = "paper", 
    strategy_override: str = None,
    trigger_id: str = None,
    rule_id: str = None
):
    """
    Asynchronous version of the trading workflow with trigger logging.
    """
    mode = mode.lower()
    if timeframes is None:
        timeframes = ["M5"]
    
    # Generate a unique workflow_run_id for this execution
    workflow_run_id = f"run_{uuid.uuid4().hex[:12]}"
    request_payload = {
        "symbol": symbol,
        "timeframes": timeframes,
        "mode": mode,
        "strategy_override": strategy_override,
        "trigger_id": trigger_id,
        "rule_id": rule_id,
        "workflow_run_id": workflow_run_id,
    }
    
    # 1. Initialize Trigger Run in DB if not provided
    if not trigger_id:
        trigger_id = create_trigger_run(None, {
            "rule_id": rule_id,
            "workflow_run_id": workflow_run_id,
            "symbol": symbol,
            "timeframes": timeframes,
            "mode": mode,
            "strategy_override": strategy_override,
            "status": "running",
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "started_at": datetime.now(timezone.utc).isoformat()
        })
    else:
        update_trigger_run(None, trigger_id, {
            "status": "running",
            "workflow_run_id": workflow_run_id,
            "started_at": datetime.now(timezone.utc).isoformat()
        })

    def log_extra(event: str, **values):
        base = {
            "event": event,
            "trigger_id": trigger_id,
            "workflow_run_id": workflow_run_id,
            "rule_id": rule_id,
            "symbol": symbol,
            "mode": mode,
            "strategy_override": strategy_override,
        }
        base.update(values)
        return base

    logger.info(
        "🚀 Trading Service: Starting workflow for %s (%s)",
        symbol, mode,
        extra=log_extra("trigger.workflow.started")
    )
    add_trigger_event(None, trigger_id, "started", message=f"Starting workflow for {symbol}")
    
    start_time = datetime.now()
    final_state = {}
    
    def finalize_run(status: str, workflow_status: str = "completed", final_action: str = None, error_message: str = None, guardrail_result: Any = None):
        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        
        logger.info(
            "🏁 Trading Service: Finalizing run for %s (%s). status=%s, action=%s",
            symbol, mode, status, final_action,
            extra=log_extra(
                "trigger.workflow.completed",
                run_status=status,
                final_action=final_action,
                duration_ms=duration_ms,
            )
        )
        if error_message:
            logger.error(
                "❌ Trading Service: Error during run for %s (%s) - %s",
                symbol, mode, error_message,
                extra=log_extra("trigger.workflow.failed", failure_reason=error_message)
            )

        update_trigger_run(None, trigger_id, {
            "status": status,
            "workflow_status": workflow_status,
            "final_action": final_action,
            "error_message": error_message,
            "duration_ms": duration_ms,
            "finished_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Save comprehensive snapshot
        save_trigger_snapshot(None, trigger_id, {
            "request": request_payload,
            "initial_state": _model_to_dict({
                "symbol": symbol, 
                "timeframes": timeframes,
                "mode": mode,
                "strategy_override": strategy_override
            }),
            "final_state": _model_to_dict(final_state),
            "final_order": _model_to_dict(final_state.get("final_order")),
            "decision_context": _model_to_dict(final_state.get("decision_context")),
            "guardrail_result": guardrail_result,
            "strategy_snapshot": _model_to_dict(final_state.get("strategy_hypothesis"))
        })
        logger.info(
            "📸 Trading Service: Snapshot saved for %s.",
            symbol,
            extra=log_extra("trigger.snapshot.saved", final_action=final_action, run_status=status),
        )

    try:
        # 2. Run LangGraph
        graph = get_compiled_graph()
        initial_state = {
            "symbol": symbol, 
            "timeframes": timeframes,
            "trigger_id": trigger_id,
            "mode": mode,
            "strategy_override": strategy_override
        }
        
        add_trigger_event(None, trigger_id, "workflow_started")
        final_state = initial_state.copy()
        for s in graph.stream(initial_state):
            node_name = list(s.keys())[0]
            node_data = list(s.values())[0]
            final_state.update(node_data)

            # Step 9: Agent Visibility - Record structured data events
            if node_name == "tech_analyst":
                summary = node_data.get("tech_summary", {})
                payload = _pick_agent_fields(summary, [
                    "trend",
                    "market_regime",
                    "trade_worthy",
                    "key_observations",
                    "support_levels",
                    "resistance_levels",
                    "summary",
                ])
                add_trigger_event(None, trigger_id, "agent_tech", 
                                message=f"Regime: {payload.get('market_regime')}, Worthy: {payload.get('trade_worthy')}",
                                payload=payload)
            elif node_name == "strategist":
                hypo = node_data.get("strategy_hypothesis", {})
                payload = _pick_agent_fields(hypo, [
                    "selected_strategy",
                    "action",
                    "confidence",
                    "reasoning",
                ])
                add_trigger_event(None, trigger_id, "agent_strat", 
                                message=f"Strategy: {payload.get('selected_strategy')}, Action: {payload.get('action')}",
                                payload=payload)
            elif node_name == "chief_trader":
                order = node_data.get("final_order", {})
                order_payload = _model_to_dict(order) or {}
                payload = {
                    "action": order_payload.get("action"),
                    "entry": order_payload.get("entry_price"),
                    "sl": order_payload.get("sl_price", order_payload.get("sl")),
                    "tp": order_payload.get("tp_price", order_payload.get("tp")),
                    "target_rr": order_payload.get("target_rr"),
                    "reasoning": order_payload.get("reasoning", order_payload.get("final_reasoning")),
                }
                payload = {key: value for key, value in payload.items() if value is not None}
                add_trigger_event(None, trigger_id, "agent_chief", 
                                message=f"Decision: {payload.get('action')}",
                                payload=payload)

            add_trigger_event(None, trigger_id, "node_completed", node_name=node_name)
            logger.info(
                "Workflow node completed: %s",
                node_name,
                extra=log_extra("trigger.workflow.node_completed", node_name=node_name),
            )

        add_trigger_event(None, trigger_id, "workflow_completed")

        # 3. Intercept Results
        if final_state.get("error_flag"):
            error_msg = final_state.get("error_message", "Unknown error")
            add_trigger_event(None, trigger_id, "failed", message=error_msg)
            finalize_run(status="failed", workflow_status="error", error_message=error_msg)
            return

        final_order_obj = final_state.get("final_order")
        final_order = _model_to_dict(final_order_obj)

        if final_order:
            action = final_order.get("action", "HOLD")
        else:
            action = "NONE"

        if not final_order:
            logger.info(
                "ℹ️ Trading Service: No order generated by strategy.",
                extra=log_extra("trigger.decision.hold", final_action="NONE")
            )
            add_trigger_event(None, trigger_id, "finished", message="No order generated")
            finalize_run(status="success", final_action="NONE")
            return
            
        if action.upper() in ["HOLD", "WAIT"]:
            logger.info(
                "ℹ️ Trading Service: Strategy decided to %s.",
                action,
                extra=log_extra("trigger.decision.hold", final_action=action)
            )
            add_trigger_event(None, trigger_id, "finished", message=f"Decision: {action}")
            finalize_run(status="success", final_action=action)
            return
            
        # 4. Guardrails & Validators
        sl = final_order.get("sl_price", final_order.get("sl", 0.0))
        tp = final_order.get("tp_price", final_order.get("tp", 0.0))
        entry_price = final_order.get("entry_price", 0.0)
        
        account_balance = final_state.get("account_info", {}).get("balance", 10000.0)
        risk_per_trade_pct = float(os.environ.get("RISK_PER_TRADE_PCT", "0.005"))
        
        # Price Direction & R/R Guardrail
        price_ok = validate_order_prices(action, entry_price, sl, tp)
        if not price_ok:
            reject_reason = f"Invalid SL/TP or Risk/Reward (entry={entry_price}, sl={sl}, tp={tp})"
            logger.warning(
                "🛡️ Trading Service: Price Guardrail REJECTED. %s",
                reject_reason,
                extra=log_extra(
                    "trigger.guardrail.rejected",
                    blocked_stage="price_guardrail",
                    failure_reason=reject_reason,
                    final_action=action,
                )
            )
            add_trigger_event(None, trigger_id, "guardrail_rejected", message=reject_reason)
            finalize_run(status="blocked", final_action=action, error_message=reject_reason, guardrail_result={
                "type": "price_guardrail",
                "success": False,
                "message": reject_reason,
                "data": {"entry": entry_price, "sl": sl, "tp": tp}
            })
            return

        # Strategy Specific Validator
        setup_ok, setup_reason = validate_strategy_setup(
            action,
            entry_price,
            sl,
            final_state.get("strategy_hypothesis", {}),
            final_state.get("indicator_data", {}),
        )
        if not setup_ok:
            logger.warning(
                "🛡️ Trading Service: Strategy Validator REJECTED. %s",
                setup_reason,
                extra=log_extra(
                    "trigger.strategy_validator.rejected",
                    blocked_stage="strategy_validator",
                    failure_reason=setup_reason,
                    final_action=action,
                )
            )
            add_trigger_event(None, trigger_id, "guardrail_rejected", message=setup_reason)
            finalize_run(status="blocked", final_action=action, error_message=setup_reason, guardrail_result={
                "type": "strategy_validator",
                "success": False,
                "message": setup_reason
            })
            return

        # 5. Execution
        order = Order(
            action=OrderAction(action.upper()),
            symbol=symbol,
            entry_price=entry_price,
            sl_price=sl,
            tp_price=tp,
            reasoning=final_order.get("reasoning", "")
        )
        
        order_result_data = {}
        safe_lot = 0.0
        if mode == "live":
            # In live mode, usecase does the risk calculation internally
            safe_lot = enforce_one_percent_rule(account_balance, entry_price, sl, risk_pct=risk_per_trade_pct)
            logger.info(
                "📐 Trading Service: LIVE risk lot calculated for %s. lot=%.2f",
                symbol,
                safe_lot,
                extra=log_extra("trigger.risk_lot.calculated", lot_size=safe_lot, final_action=action)
            )
            if safe_lot <= 0:
                reject_reason = f"Risk management blocked LIVE order: safe lot calculated to {safe_lot}"
                logger.warning(
                    "🛡️ Trading Service: Risk Guardrail REJECTED. %s",
                    reject_reason,
                    extra=log_extra(
                        "trigger.guardrail.rejected",
                        blocked_stage="risk_guardrail",
                        failure_reason=reject_reason,
                        final_action=action,
                    )
                )
                add_trigger_event(None, trigger_id, "guardrail_rejected", message=reject_reason)
                finalize_run(status="blocked", final_action=action, error_message=reject_reason, guardrail_result={
                    "type": "risk_guardrail",
                    "success": False,
                    "message": reject_reason
                })
                return

            logger.info(
                "📤 Trading Service: Submitting LIVE order for %s. lot=%.2f",
                symbol,
                safe_lot,
                extra=log_extra("trigger.execution.requested", lot_size=safe_lot, final_action=action)
            )
            add_trigger_event(None, trigger_id, "order_submitted", message="Submitting LIVE order")
            usecase = TradeExecutionUseCase(MT5Client())
            result = usecase.execute_trade(
                order=order,
                current_loss_pct=0.0, 
                today_trade_count=0,
                account_balance=account_balance,
                risk_per_trade_pct=risk_per_trade_pct,
                trigger_id=trigger_id,
                workflow_run_id=workflow_run_id,
                rule_id=rule_id,
                mode=mode,
            )
            order_result_data = result.model_dump()
            
            # Step 5: Live Success/Failure Branching
            if not result.success:
                err = result.failure_reason or result.error_message or "Unknown execution error"
                logger.error(
                    "❌ Trading Service: LIVE Order FAILED for %s. %s",
                    symbol,
                    err,
                    extra=log_extra("trigger.execution.failed", failure_reason=err, final_action=action)
                )
                add_trigger_event(None, trigger_id, "order_failed", message=err, payload=order_result_data)
                finalize_run(
                    status="failed", 
                    final_action=action, 
                    error_message=err,
                    guardrail_result={
                        "type": "execution_error",
                        "success": False,
                        "message": err,
                        "execution_details": order_result_data,
                        "raw_response": order_result_data.get("raw_response")
                    }
                )
                return
            
            # Success path for LIVE
            logger.info(
                "✅ Trading Service: LIVE Order SUCCESS for %s. ticket=%s",
                symbol,
                order_result_data.get('ticket'),
                extra=log_extra(
                    "trigger.execution.acked",
                    ticket=order_result_data.get('ticket'),
                    final_action=action,
                )
            )
            add_trigger_event(None, trigger_id, "order_acked", message=f"Order success: ticket {order_result_data.get('ticket')}", payload=order_result_data)
            decision_context = build_decision_context(final_state, order_result_data)
            track_open_position(
                mode=mode,
                symbol=symbol,
                action=action,
                entry_price=order_result_data.get("executed_price") or entry_price,
                sl=sl,
                tp=tp,
                lot_size=order.lot_size,
                order_result=order_result_data,
                decision_context=decision_context,
            )
            final_state["decision_context"] = decision_context
            finalize_run(
                status="success", 
                final_action=action, 
                guardrail_result={
                    "type": "all_pass",
                    "success": True,
                    "details": {
                        "price_guardrail": {"success": True, "entry": entry_price, "sl": sl, "tp": tp},
                        "strategy_validator": {"success": True, "reason": setup_reason},
                        "risk_guardrail": {"success": True, "lot": safe_lot}
                    }
                }
            )
            return

        else:
            # Paper mode
            logger.info(
                "📤 Trading Service: Executing PAPER order for %s.",
                symbol,
                extra=log_extra("trigger.execution.requested", final_action=action)
            )
            add_trigger_event(None, trigger_id, "order_submitted", message="Executing PAPER order")
            safe_lot = enforce_one_percent_rule(account_balance, entry_price, sl, risk_pct=risk_per_trade_pct)
            logger.info(
                "📐 Trading Service: PAPER risk lot calculated for %s. lot=%.2f",
                symbol,
                safe_lot,
                extra=log_extra("trigger.risk_lot.calculated", lot_size=safe_lot, final_action=action)
            )
            if safe_lot <= 0:
                reject_reason = f"Risk management blocked order: safe lot calculated to {safe_lot}"
                logger.warning(
                    "🛡️ Trading Service: Risk Guardrail REJECTED. %s",
                    reject_reason,
                    extra=log_extra(
                        "trigger.guardrail.rejected",
                        blocked_stage="risk_guardrail",
                        failure_reason=reject_reason,
                        final_action=action,
                    )
                )
                add_trigger_event(None, trigger_id, "guardrail_rejected", message=reject_reason)
                finalize_run(status="blocked", final_action=action, error_message=reject_reason, guardrail_result={
                    "type": "risk_guardrail",
                    "success": False,
                    "message": reject_reason
                })
                return
            
            result = execute_mock_order(symbol, action, safe_lot, sl, tp, entry_price)
            success = result.get("success")
            if success is None:
                success = result.get("retcode") == 10009
            order_result_data = {
                "success": success,
                "mode": "paper",
                "symbol": symbol,
                "action": action,
                "requested_entry_price": entry_price,
                "requested_lot": safe_lot,
                "requested_sl": sl,
                "requested_tp": tp,
                "safe_lot": safe_lot,
                "failure_reason": None if success else "Mock execution failed",
                "ticket": result.get("ticket") or result.get("order"),
                "executed_price": result.get("executed_price") or result.get("price"),
                "timestamp": result.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                "raw_response": result.get("raw_response") or result
            }
            order.lot_size = safe_lot

            if success:
                logger.info(
                    "✅ Trading Service: PAPER Order SUCCESS for %s. ticket=%s",
                    symbol,
                    order_result_data.get('ticket'),
                    extra=log_extra(
                        "trigger.execution.acked",
                        ticket=order_result_data.get('ticket'),
                        final_action=action,
                    )
                )
                add_trigger_event(None, trigger_id, "order_acked", message=f"Order success: ticket {order_result_data.get('ticket')}", payload=order_result_data)
                decision_context = build_decision_context(final_state, order_result_data)
                track_open_position(
                    mode=mode,
                    symbol=symbol,
                    action=action,
                    entry_price=order_result_data.get("executed_price") or entry_price,
                    sl=sl,
                    tp=tp,
                    lot_size=order.lot_size,
                    order_result=order_result_data,
                    decision_context=decision_context,
                )
                final_state["decision_context"] = decision_context
                finalize_run(
                    status="success", 
                    final_action=action, 
                    guardrail_result={
                        "type": "all_pass",
                        "success": True,
                        "details": {
                            "price_guardrail": {"success": True, "entry": entry_price, "sl": sl, "tp": tp},
                            "strategy_validator": {"success": True, "reason": setup_reason},
                            "risk_guardrail": {"success": True, "lot": safe_lot}
                        }
                    }
                )
            else:
                err = "Mock execution failed"
                logger.error(
                    "❌ Trading Service: PAPER Order FAILED for %s.",
                    symbol,
                    extra=log_extra("trigger.execution.failed", failure_reason=err, final_action=action)
                )
                add_trigger_event(None, trigger_id, "order_failed", message=err, payload=order_result_data)
                finalize_run(
                    status="failed", 
                    final_action=action, 
                    error_message=err,
                    guardrail_result={
                        "type": "execution_error",
                        "success": False,
                        "message": err,
                        "execution_details": order_result_data
                    }
                )

    except Exception as e:
        err_msg = str(e)
        tb_str = traceback.format_exc()
        full_error = f"{err_msg}\n\nTraceback:\n{tb_str}"
        logger.error(
            "💥 Trading Service: Critical Error for %s - %s",
            symbol,
            err_msg,
            extra=log_extra("trigger.workflow.failed", failure_reason=err_msg)
        )
        add_trigger_event(None, trigger_id, "failed", message=err_msg)
        finalize_run(status="failed", workflow_status="error", error_message=full_error)

def run_trading_workflow(
    symbol: str, 
    timeframes: List[str] = None, 
    mode: str = "paper", 
    strategy_override: str = None,
    trigger_id: str = None,
    rule_id: str = None
):
    """
    Synchronous wrapper for compatibility.
    """
    return asyncio.run(run_trading_workflow_async(
        symbol=symbol,
        timeframes=timeframes,
        mode=mode,
        strategy_override=strategy_override,
        trigger_id=trigger_id,
        rule_id=rule_id
    ))
