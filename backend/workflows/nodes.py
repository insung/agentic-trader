import os
import json
from datetime import datetime
from typing import Dict, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from backend.workflows.state import AgentState
from backend.workflows.llm_client import invoke_llm_with_retry
from backend.workflows.order_helpers import project_tp_from_rr
from backend.workflows.prompts import read_prompt
from backend.workflows.schemas import FinalOrder, ReviewLog, StrategyHypothesis, TechSummary
from backend.workflows.strategy_registry import load_strategy_contract, read_strategies
from backend.features.trading.adapters.mt5_account import get_account_summary
from backend.features.trading.adapters.mt5_connection import is_mt5_available
from backend.features.trading.adapters.mt5_market_data import fetch_ohlcv, get_current_price
from backend.features.trading.adapters.paper_execution import execute_mock_order
from backend.features.trading.guardrails import enforce_one_percent_rule, validate_order_prices
from backend.features.trading.indicators import add_technical_indicators, build_indicator_snapshot
from backend.features.trading.market_hours import is_market_open, get_market_status_message
from backend.features.trading.strategy_validators import build_volatility_expansion_breakout_metadata, validate_strategy_setup
from backend.features.trading.persistence.backtest_store import DEFAULT_BACKTEST_DB_PATH, upsert_candles
from backend.features.trading.persistence.trading_log_store import DEFAULT_TRADING_LOG_DB_PATH, store_trade_review

import logging

logger = logging.getLogger(__name__)

# Backward-compatible aliases for existing tests and callers.
_invoke_llm_with_retry = invoke_llm_with_retry
_load_strategy_contract = load_strategy_contract
_project_tp_from_rr = project_tp_from_rr
_read_prompt = read_prompt
_read_strategies = read_strategies

def _persist_runtime_candles(symbol: str, timeframe: str, df) -> None:
    """Optionally archive live/paper OHLCV snapshots for replayable trade reviews."""
    if os.getenv("PERSIST_MARKET_CANDLES", "0").lower() not in {"1", "true", "yes", "on"}:
        return
    db_path = os.getenv("MARKET_DATA_DB_PATH", DEFAULT_BACKTEST_DB_PATH)
    try:
        upsert_candles(db_path, symbol, timeframe, df)
    except Exception as exc:
        logger.warning("Runtime candle persistence failed for %s %s: %s", symbol, timeframe, exc)

def fetch_data_node(state: AgentState) -> Dict[str, Any]:
    """Node 1: Fetch OHLCV Data and calculate indicators."""
    trigger_id = getattr(state, "trigger_id", "N/A")
    symbol = getattr(state, "symbol", "EURUSD")
    logger.info("[Node 1] fetch_data_node executed for %s", symbol, extra={"trigger_id": trigger_id, "symbol": symbol})
    timeframes = getattr(state, "timeframes", ["M5"])
    
    # 시장 휴장 체크
    if not is_market_open(symbol=symbol):
        msg = get_market_status_message(symbol=symbol)
        logger.warning("🚫 %s", msg, extra={"trigger_id": trigger_id, "symbol": symbol})
        return {"raw_data": "", "error_flag": True, "error_message": msg}
    
    # MT5 사용 가능 여부 체크
    if not is_mt5_available():
        logger.error("❌ MT5 not available. Cannot fetch live data.", extra={"trigger_id": trigger_id, "symbol": symbol})
        return {"raw_data": "", "error_flag": True, "error_message": "MT5 not available. Run server with Wine Python."}
    
    account_info = get_account_summary()
    if not account_info:
        logger.error("❌ Failed to get account info from MT5.", extra={"trigger_id": trigger_id, "symbol": symbol})
        return {"raw_data": "", "error_flag": True, "error_message": "MT5 account info unavailable."}
    
    # 현재가 조회
    current_price = get_current_price(symbol)
    
    raw_data = f"Account Info: {json.dumps(account_info)}\n"
    raw_data += f"Current Price: {json.dumps(current_price)}\n"
    
    indicator_data: Dict[str, Any] = {}
    for tf in timeframes:
        df = fetch_ohlcv(symbol, tf, 100)
        if df.empty:
            logger.warning("❌ No OHLCV data for %s on %s.", symbol, tf, extra={"trigger_id": trigger_id, "symbol": symbol, "timeframe": tf})
            continue
        _persist_runtime_candles(symbol, tf, df)
        enriched = add_technical_indicators(df)
        snapshot = build_indicator_snapshot(df)
        indicator_data[tf] = snapshot
        recent_columns = [
            "time", "open", "high", "low", "close", "tick_volume",
            "ema20", "ema50", "atr14", "adx14",
            "bb_mid20", "bb_upper20", "bb_lower20", "bb_width20", "rsi14",
        ]
        recent_columns = [col for col in recent_columns if col in enriched.columns]
        recent_df = enriched.tail(10)[recent_columns].copy()
        numeric_columns = recent_df.select_dtypes(include="number").columns
        recent_df[numeric_columns] = recent_df[numeric_columns].round(6)
        recent_data = recent_df.to_json(orient='records', date_format='iso')
        raw_data += f"\n[{tf} Timeframe Market Data (last 10 candles)]:\n{recent_data}\n"
        raw_data += f"\n[{tf} Deterministic Indicator Snapshot]:\n{json.dumps(snapshot, ensure_ascii=False)}\n"
        
    return {"raw_data": raw_data, "account_info": account_info, "indicator_data": indicator_data, "error_flag": False}

def tech_analyst_node(state: AgentState) -> Dict[str, Any]:
    """Node 2: Tech Analyst analyzes raw data and outputs a summary."""
    trigger_id = getattr(state, "trigger_id", "N/A")
    symbol = getattr(state, "symbol", "N/A")
    logger.info("[Node 2] tech_analyst_node executed", extra={"trigger_id": trigger_id, "symbol": symbol})
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    structured_llm = llm.with_structured_output(TechSummary)
    
    system_prompt = _read_prompt("tech_analyst")
    human_content = f"Here is the raw data:\n{getattr(state, 'raw_data', '')}"
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_content)]
    
    try:
        response = _invoke_llm_with_retry(structured_llm, messages)
        return {"tech_summary": response.model_dump(), "error_flag": False}
    except Exception as e:
        logger.error("LLM API completely failed in tech_analyst: %s", e, extra={"trigger_id": trigger_id, "symbol": symbol})
        return {"error_flag": True}

def strategist_node(state: AgentState) -> Dict[str, Any]:
    """Node 3: Strategist reviews technical summary and returns a hypothesis."""
    trigger_id = getattr(state, "trigger_id", "N/A")
    symbol = getattr(state, "symbol", "N/A")
    logger.info("[Node 3] strategist_node executed", extra={"trigger_id": trigger_id, "symbol": symbol})
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    structured_llm = llm.with_structured_output(StrategyHypothesis)
    
    system_prompt = _read_prompt("strategist")
    tech_summary_data = getattr(state, 'tech_summary', {})
    market_regime = tech_summary_data.get('market_regime', 'Ranging')
    timeframes = getattr(state, "timeframes", ["M5"])
    strategies_kb = _read_strategies(market_regime, timeframes, symbol)
    
    human_content = f"Here is the Tech Summary:\n{getattr(state, 'tech_summary', {})}\n\n"
    human_content += f"Available Trading Strategies (Knowledge Base):\n{strategies_kb}"
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_content)]
    
    try:
        response = _invoke_llm_with_retry(structured_llm, messages)
        return {"strategy_hypothesis": response.model_dump(), "error_flag": False}
    except Exception as e:
        logger.error("LLM API completely failed in strategist: %s", e, extra={"trigger_id": trigger_id, "symbol": symbol})
        return {"error_flag": True}

def chief_trader_node(state: AgentState) -> Dict[str, Any]:
    """Node 4: Chief Trader reviews hypothesis and returns final order."""
    trigger_id = getattr(state, "trigger_id", "N/A")
    symbol = getattr(state, "symbol", "N/A")
    logger.info("[Node 4] chief_trader_node executed", extra={"trigger_id": trigger_id, "symbol": symbol})
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    structured_llm = llm.with_structured_output(FinalOrder)
    
    system_prompt = _read_prompt("chief_trader")
    
    # 전략 가설 + 계좌 정보를 함께 전달
    account_info = getattr(state, 'account_info', {})
    strategy_hypothesis = getattr(state, 'strategy_hypothesis', {}) or {}
    selected_strategy = str(strategy_hypothesis.get("selected_strategy", ""))
    strategy_contract = _load_strategy_contract(selected_strategy)
    human_content = f"Here is the Strategy Hypothesis:\n{getattr(state, 'strategy_hypothesis', {})}\n\n"
    human_content += f"Deterministic Indicator Data:\n{json.dumps(getattr(state, 'indicator_data', {}), ensure_ascii=False)}\n\n"
    human_content += f"Strategy Contract:\n{json.dumps(strategy_contract, ensure_ascii=False)}\n\n"
    human_content += f"Account Info: {json.dumps(account_info)}"
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_content)]
    
    try:
        response = _invoke_llm_with_retry(structured_llm, messages)
        
        # 실시간 가격 조회
        symbol = getattr(state, "symbol", "EURUSD")
        current_price = get_current_price(symbol)
        entry_price = current_price.get("ask", 0.0) if response.action.upper() == "BUY" else current_price.get("bid", 0.0)
        try:
            min_rr = float(strategy_contract.get("minimum_risk_reward", 2.0) or 2.0)
        except (TypeError, ValueError):
            min_rr = 2.0
        try:
            target_rr = float(getattr(response, "target_rr", None) or min_rr)
        except (TypeError, ValueError):
            target_rr = min_rr
        target_rr = max(target_rr, min_rr, 2.0)
        tp_price = _project_tp_from_rr(response.action, entry_price, response.sl, target_rr)
        if tp_price <= 0:
            tp_price = response.tp
        
        final_order_dict = {
            "action": response.action,
            "symbol": symbol,
            "entry_price": entry_price,
            "sl_price": response.sl,
            "tp_price": tp_price,
            "target_rr": target_rr,
            "exit_plan": getattr(response, "exit_plan", "primary_target"),
            "lot_size": 0.0,
            "reasoning": response.final_reasoning
        }
        return {"final_order": final_order_dict, "error_flag": False}
    except Exception as e:
        logger.error("LLM API completely failed in chief_trader: %s", e, extra={"trigger_id": trigger_id, "symbol": symbol})
        return {"error_flag": True}

def execute_order_node(state: AgentState) -> Dict[str, Any]:
    """Node 4.5: Executes the order based on Chief Trader's decision."""
    trigger_id = getattr(state, "trigger_id", "N/A")
    symbol = getattr(state, "symbol", "EURUSD")
    logger.info("[Node 4.5] execute_order_node executed", extra={"trigger_id": trigger_id, "symbol": symbol})
    final_order = getattr(state, "final_order", None)
    
    if not final_order:
        return {"order_result": {"success": False, "error_message": "No final_order", "timestamp": datetime.now().isoformat()}}
        
    if isinstance(final_order, dict):
        final_order_payload = dict(final_order)
        action = final_order_payload.get("action", "HOLD")
        sl = final_order_payload.get("sl_price", final_order_payload.get("sl", 0.0))
        tp = final_order_payload.get("tp_price", final_order_payload.get("tp", 0.0))
    else:
        action = final_order.action.value if hasattr(final_order.action, 'value') else final_order.action
        sl = final_order.sl_price
        tp = final_order.tp_price
        final_order_payload = final_order.model_dump() if hasattr(final_order, "model_dump") else dict(final_order)
    if action.upper() not in ["BUY", "SELL"]:
        return {"order_result": {"success": False, "error_message": f"Action was {action}", "timestamp": datetime.now().isoformat()}}
        
    symbol = getattr(state, "symbol", "EURUSD")
    
    account_info = get_account_summary()
    balance = account_info.get("balance", 10000.0)
    
    # 실시간 가격 조회
    current_price = get_current_price(symbol)
    entry_price = current_price.get("ask", 0.0) if action.upper() == "BUY" else current_price.get("bid", 0.0)
    if entry_price <= 0:
        return {"order_result": {"success": False, "error_message": "Could not get current price", "timestamp": datetime.now().isoformat()}}

    strategy_hypothesis = getattr(state, "strategy_hypothesis", {}) or {}
    selected_strategy = str(strategy_hypothesis.get("selected_strategy", ""))
    if "volatility expansion breakout" in selected_strategy.lower():
        strategy_metadata = build_volatility_expansion_breakout_metadata(
            action,
            getattr(state, "indicator_data", {}),
            primary_timeframe="M5",
            confirmation_timeframes=["M15"],
        )
        if strategy_metadata:
            final_order_payload["strategy_metadata"] = strategy_metadata
    
    # 1. Strategy Specific Validator & Override
    setup_ok, setup_reason, overridden_sl, overridden_tp = validate_strategy_setup(
        action,
        entry_price,
        sl,
        getattr(state, "strategy_hypothesis", {}),
        getattr(state, "indicator_data", {}),
    )
    if not setup_ok:
        return {"order_result": {"success": False, "error_message": f"Guardrail: {setup_reason}", "timestamp": datetime.now().isoformat()}}
        
    if overridden_sl is not None:
        sl = overridden_sl
    if overridden_tp is not None:
        tp = overridden_tp

    final_order_payload["action"] = action
    final_order_payload["sl_price"] = sl
    final_order_payload["tp_price"] = tp
    final_order_payload["entry_price"] = entry_price
    final_order_payload["symbol"] = symbol

    # 2. Price Direction & R/R Guardrail
    if not validate_order_prices(action, entry_price, sl, tp):
        return {"order_result": {"success": False, "error_message": "Guardrail: invalid SL/TP direction or risk/reward", "timestamp": datetime.now().isoformat()}}

    lot_size = enforce_one_percent_rule(balance, entry_price, sl)
    
    if lot_size <= 0:
         return {"order_result": {"success": False, "error_message": "Guardrail: lot size calculated to <= 0", "timestamp": datetime.now().isoformat()}}
         
    result = execute_mock_order(symbol, action, lot_size, sl, tp, entry_price)
    order_result_dict = {
        "success": result.get("retcode") == 10009,
        "ticket": result.get("order"),
        "executed_price": result.get("price"),
        "timestamp": datetime.now().isoformat()
    }
    return {"order_result": order_result_dict, "final_order": final_order_payload}


def _normalize_lesson_evidence(review_log: Dict[str, Any], closed_trade: Dict[str, Any], decision_context: Dict[str, Any]) -> list[str]:
    evidence = review_log.get("lesson_evidence", [])
    if isinstance(evidence, str):
        evidence = [evidence]
    if not isinstance(evidence, list):
        evidence = []

    normalized = [str(item).strip() for item in evidence if str(item).strip()]
    if normalized:
        return normalized

    strategy_hypothesis = decision_context.get("strategy_hypothesis", {}) or {}
    tech_summary = decision_context.get("tech_summary", {}) or {}
    final_order = decision_context.get("final_order", {}) or {}
    selected_strategy = str(
        strategy_hypothesis.get("selected_strategy")
        or final_order.get("strategy")
        or review_log.get("strategy")
        or ""
    )
    market_regime = str(tech_summary.get("market_regime") or "")
    result = str(closed_trade.get("result") or "UNKNOWN")
    exit_reason = str(closed_trade.get("exit_reason") or "unknown")
    pnl = closed_trade.get("pnl")

    fallback = [
        f"closed_trade.result={result}",
        f"closed_trade.exit_reason={exit_reason}",
    ]
    if pnl is not None:
        fallback.append(f"closed_trade.pnl={pnl}")
    if selected_strategy:
        fallback.append(f"strategy={selected_strategy}")
    if market_regime:
        fallback.append(f"market_regime={market_regime}")
    if final_order.get("action"):
        fallback.append(f"final_order.action={final_order.get('action')}")
    return fallback


def _fallback_lesson_root_cause(closed_trade: Dict[str, Any], decision_context: Dict[str, Any]) -> str:
    result = str(closed_trade.get("result") or "").upper()
    exit_reason = str(closed_trade.get("exit_reason") or "").strip()
    strategy_hypothesis = decision_context.get("strategy_hypothesis", {}) or {}
    selected_strategy = str(strategy_hypothesis.get("selected_strategy") or "").strip()

    if result == "TP_HIT":
        return "The setup followed through after entry and reached the planned target."
    if result == "SL_HIT":
        return "The setup failed after entry and price moved against the position until the stop loss was hit."
    if result == "CLOSED":
        return f"The position was closed without resolving the thesis; exit reason was {exit_reason or 'Closed'}."
    if result == "INVALIDATED":
        return "The post-entry invalidation rule triggered before the trade could complete its thesis."
    if selected_strategy:
        return f"The {selected_strategy} setup did not receive enough follow-through to confirm the entry thesis."
    return "The trade outcome did not provide a clear validation of the entry thesis."


def _fallback_next_trade_rule(review_log: Dict[str, Any], closed_trade: Dict[str, Any], decision_context: Dict[str, Any]) -> str:
    strategy_hypothesis = decision_context.get("strategy_hypothesis", {}) or {}
    final_order = decision_context.get("final_order", {}) or {}
    tech_summary = decision_context.get("tech_summary", {}) or {}
    selected_strategy = str(
        strategy_hypothesis.get("selected_strategy")
        or final_order.get("strategy")
        or review_log.get("strategy")
        or "the setup"
    ).strip()
    market_regime = str(tech_summary.get("market_regime") or "").strip()
    result = str(closed_trade.get("result") or "").upper()

    if result == "TP_HIT":
        return f"Require the same {selected_strategy} setup to preserve the existing entry and exit rules before scaling size."
    if result == "SL_HIT":
        return f"Wait for stronger confirmation in {selected_strategy} before entering again, especially if the market is still {market_regime or 'unclear'}."
    if result == "CLOSED":
        return f"Do not treat a flat closure as confirmation; demand clearer post-entry momentum before reusing {selected_strategy}."
    return f"Use the same {selected_strategy} only when the post-entry context is consistent with the validated thesis."


def _normalize_quality_fields(review_log: Dict[str, Any], closed_trade: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(review_log)
    result = str(closed_trade.get("result") or "").upper()
    pnl = closed_trade.get("pnl")

    process_quality = str(normalized.get("process_quality") or "").strip()
    outcome_quality = str(normalized.get("outcome_quality") or "").strip()
    trade_quality_label = str(normalized.get("trade_quality_label") or "").strip()
    rule_adherence = normalized.get("rule_adherence")

    if not process_quality:
        process_quality = "unknown"
    if not outcome_quality:
        if result == "TP_HIT":
            outcome_quality = "favorable"
        elif result == "SL_HIT":
            outcome_quality = "unfavorable"
        elif result == "INVALIDATED":
            outcome_quality = "protective"
        elif result == "CLOSED" and pnl == 0:
            outcome_quality = "neutral"
        elif result == "CLOSED":
            outcome_quality = "mixed"
        else:
            outcome_quality = "unknown"
    if rule_adherence is False:
        trade_quality_label = "bad_trade"
        if not process_quality or process_quality == "unknown":
            process_quality = "poor"
    elif rule_adherence is True:
        if result == "TP_HIT" and outcome_quality == "favorable":
            trade_quality_label = "good_trade"
            if not process_quality or process_quality == "unknown":
                process_quality = "good"
        else:
            trade_quality_label = "mixed_trade"
    elif not trade_quality_label:
        trade_quality_label = "mixed_trade"

    normalized["process_quality"] = process_quality
    normalized["outcome_quality"] = outcome_quality
    normalized["trade_quality_label"] = trade_quality_label
    normalized["rule_adherence"] = rule_adherence
    return normalized


def _normalize_review_log(review_log: Dict[str, Any], closed_trade: Dict[str, Any], decision_context: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(review_log)
    normalized = _normalize_quality_fields(normalized, closed_trade)
    normalized["lesson_evidence"] = _normalize_lesson_evidence(normalized, closed_trade, decision_context)
    normalized["lesson_root_cause"] = str(normalized.get("lesson_root_cause") or "").strip() or _fallback_lesson_root_cause(closed_trade, decision_context)
    normalized["next_trade_rule"] = str(normalized.get("next_trade_rule") or "").strip() or _fallback_next_trade_rule(normalized, closed_trade, decision_context)
    if not str(normalized.get("trade_quality_label") or "").strip():
        normalized["trade_quality_label"] = "mixed_trade"

    confidence_value = normalized.get("confidence", 0.5)
    try:
        confidence = float(confidence_value)
    except (TypeError, ValueError):
        confidence = 0.5
    normalized["confidence"] = max(0.0, min(confidence, 1.0))

    result = str(closed_trade.get("result") or "UNKNOWN")
    pnl = closed_trade.get("pnl")
    exit_reason = str(closed_trade.get("exit_reason") or "unknown")
    evidence_text = "; ".join(normalized["lesson_evidence"][:4])
    normalized["lessons_learned"] = (
        f"Process quality: {normalized['process_quality']}. "
        f"Outcome quality: {normalized['outcome_quality']}. "
        f"Trade label: {normalized['trade_quality_label']}. "
        f"Rule adherence: {normalized['rule_adherence']}. "
        f"Outcome: {result} with pnl {pnl if pnl is not None else 'n/a'} and exit reason {exit_reason}. "
        f"Root cause: {normalized['lesson_root_cause']}. "
        f"Evidence: {evidence_text}. "
        f"Next trade rule: {normalized['next_trade_rule']}."
    )
    return normalized


def _render_review_markdown(review_log: Dict[str, Any]) -> str:
    lesson_evidence = review_log.get("lesson_evidence", [])
    evidence_block = "\n".join(f"- {item}" for item in lesson_evidence) if lesson_evidence else "- No evidence recorded"
    return (
        f"# Trade Review Log\n\n"
        f"## Summary\n{review_log.get('trade_summary', '')}\n\n"
        f"## Risk Assessment\n{review_log.get('risk_assessment', '')}\n\n"
        f"## Process Quality\n{review_log.get('process_quality', '')}\n\n"
        f"## Outcome Quality\n{review_log.get('outcome_quality', '')}\n\n"
        f"## Trade Classification\n{review_log.get('trade_quality_label', '')} / rule_adherence={review_log.get('rule_adherence', '')}\n\n"
        f"## Root Cause\n{review_log.get('lesson_root_cause', '')}\n\n"
        f"## Evidence\n{evidence_block}\n\n"
        f"## Next Trade Rule\n{review_log.get('next_trade_rule', '')}\n\n"
        f"## Lessons Learned\n{review_log.get('lessons_learned', '')}\n"
    )


def risk_reviewer_node(state: AgentState) -> Dict[str, Any]:
    """Node 5: Risk Reviewer reviews a closed trade and logs the result."""
    trigger_id = getattr(state, "trigger_id", "N/A")
    symbol = getattr(state, "symbol", "N/A")
    logger.info("[Node 5] risk_reviewer_node executed", extra={"trigger_id": trigger_id, "symbol": symbol})
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    structured_llm = llm.with_structured_output(ReviewLog)
    
    system_prompt = _read_prompt("risk_reviewer")
    final_order = getattr(state, "final_order", None)
    order_result = getattr(state, "order_result", None)
    decision_context = getattr(state, "decision_context", {}) or {}
    closed_trade = getattr(state, "closed_trade", {}) or {}
    if not closed_trade:
        return {
            "error_flag": True,
            "error_message": "Risk Reviewer requires a closed_trade payload.",
        }
    
    human_content = json.dumps({
        "raw_data": getattr(state, "raw_data", ""),
        "tech_summary": getattr(state, "tech_summary", {}),
        "strategy_hypothesis": getattr(state, "strategy_hypothesis", {}),
        "final_order": final_order.model_dump() if hasattr(final_order, "model_dump") else (final_order or {}),
        "order_result": order_result.model_dump() if hasattr(order_result, "model_dump") else (order_result or {}),
        "decision_context": decision_context,
        "closed_trade": closed_trade,
    }, indent=2)
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_content)]
    
    try:
        response = _invoke_llm_with_retry(structured_llm, messages)
        review_log = _normalize_review_log(response.model_dump(), closed_trade, decision_context)
        
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        docs_dir = os.path.join(base_dir, "trading_logs")
        os.makedirs(docs_dir, exist_ok=True)
        
        safe_filename = review_log.get("save_path", f"review_{datetime.now().strftime('%Y%m%d_%H%M')}.md")
        safe_filename = safe_filename.replace("/", "_").replace("\\", "_")
        if not safe_filename.endswith(".md"):
            safe_filename += ".md"
            
        file_path = os.path.join(docs_dir, safe_filename)
        markdown_body = _render_review_markdown(review_log)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(markdown_body)
        store_trade_review(
            DEFAULT_TRADING_LOG_DB_PATH,
            review_id=os.path.splitext(safe_filename)[0],
            trade_id=str(closed_trade.get("trade_id")) if closed_trade.get("trade_id") else None,
            symbol=closed_trade.get("symbol"),
            reviewed_at=datetime.now().isoformat(),
            source_path=file_path,
            summary=review_log.get("trade_summary", ""),
            risk_assessment=review_log.get("risk_assessment", ""),
            process_quality=review_log.get("process_quality", ""),
            outcome_quality=review_log.get("outcome_quality", ""),
            trade_quality_label=review_log.get("trade_quality_label", ""),
            rule_adherence=review_log.get("rule_adherence"),
            lessons_learned=review_log.get("lessons_learned", ""),
            markdown_body=markdown_body,
            raw_payload={
                "raw_data": getattr(state, "raw_data", ""),
                "tech_summary": getattr(state, "tech_summary", {}),
                "strategy_hypothesis": getattr(state, "strategy_hypothesis", {}),
                "final_order": final_order.model_dump() if hasattr(final_order, "model_dump") else (final_order or {}),
                "order_result": order_result.model_dump() if hasattr(order_result, "model_dump") else (order_result or {}),
                "decision_context": decision_context,
                "closed_trade": closed_trade,
                "review_log": review_log,
                "review_quality": {
                    "process_quality": review_log.get("process_quality"),
                    "outcome_quality": review_log.get("outcome_quality"),
                    "trade_quality_label": review_log.get("trade_quality_label"),
                    "rule_adherence": review_log.get("rule_adherence"),
                    "confidence": review_log.get("confidence"),
                    "lesson_evidence_count": len(review_log.get("lesson_evidence", [])),
                },
            },
        )

        review_id = os.path.splitext(safe_filename)[0]
        logger.info("[Node 5] Review log saved to %s", file_path, extra={"trigger_id": trigger_id, "symbol": symbol})
        return {
            "review_log": review_log,
            "review_id": review_id,
            "review_markdown_path": file_path,
            "error_flag": False,
        }
    except Exception as e:
        logger.error("LLM API completely failed in risk_reviewer: %s", e, extra={"trigger_id": trigger_id, "symbol": symbol})
        return {"error_flag": True}
