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
from backend.features.trading.strategy_validators import validate_strategy_setup
from backend.features.trading.persistence.backtest_store import DEFAULT_BACKTEST_DB_PATH, upsert_candles
from backend.features.trading.persistence.trading_log_store import DEFAULT_TRADING_LOG_DB_PATH, store_trade_review

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
        print(f"⚠️ Runtime candle persistence failed for {symbol} {timeframe}: {exc}")

def fetch_data_node(state: AgentState) -> Dict[str, Any]:
    """Node 1: Fetch OHLCV Data and calculate indicators."""
    print("[Node 1] fetch_data_node executed")
    symbol = getattr(state, "symbol", "EURUSD")
    timeframes = getattr(state, "timeframes", ["M5"])
    
    # 시장 휴장 체크
    if not is_market_open(symbol=symbol):
        msg = get_market_status_message(symbol=symbol)
        print(f"🚫 {msg}")
        return {"raw_data": "", "error_flag": True, "error_message": msg}
    
    # MT5 사용 가능 여부 체크
    if not is_mt5_available():
        print("❌ MT5 not available. Cannot fetch live data.")
        return {"raw_data": "", "error_flag": True, "error_message": "MT5 not available. Run server with Wine Python."}
    
    account_info = get_account_summary()
    if not account_info:
        print("❌ Failed to get account info from MT5.")
        return {"raw_data": "", "error_flag": True, "error_message": "MT5 account info unavailable."}
    
    # 현재가 조회
    current_price = get_current_price(symbol)
    
    raw_data = f"Account Info: {json.dumps(account_info)}\n"
    raw_data += f"Current Price: {json.dumps(current_price)}\n"
    
    indicator_data: Dict[str, Any] = {}
    for tf in timeframes:
        df = fetch_ohlcv(symbol, tf, 100)
        if df.empty:
            print(f"❌ No OHLCV data for {symbol} on {tf}.")
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
    print("[Node 2] tech_analyst_node executed")
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    structured_llm = llm.with_structured_output(TechSummary)
    
    system_prompt = _read_prompt("tech_analyst")
    human_content = f"Here is the raw data:\n{getattr(state, 'raw_data', '')}"
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_content)]
    
    try:
        response = _invoke_llm_with_retry(structured_llm, messages)
        return {"tech_summary": response.model_dump(), "error_flag": False}
    except Exception as e:
        print(f"LLM API completely failed after retries: {e}")
        return {"error_flag": True}

def strategist_node(state: AgentState) -> Dict[str, Any]:
    """Node 3: Strategist reviews technical summary and returns a hypothesis."""
    print("[Node 3] strategist_node executed")
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    structured_llm = llm.with_structured_output(StrategyHypothesis)
    
    system_prompt = _read_prompt("strategist")
    tech_summary_data = getattr(state, 'tech_summary', {})
    market_regime = tech_summary_data.get('market_regime', 'Ranging')
    timeframes = getattr(state, "timeframes", ["M5"])
    strategies_kb = _read_strategies(market_regime, timeframes)
    
    human_content = f"Here is the Tech Summary:\n{getattr(state, 'tech_summary', {})}\n\n"
    human_content += f"Available Trading Strategies (Knowledge Base):\n{strategies_kb}"
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_content)]
    
    try:
        response = _invoke_llm_with_retry(structured_llm, messages)
        return {"strategy_hypothesis": response.model_dump(), "error_flag": False}
    except Exception as e:
        print(f"LLM API completely failed after retries: {e}")
        return {"error_flag": True}

def chief_trader_node(state: AgentState) -> Dict[str, Any]:
    """Node 4: Chief Trader reviews hypothesis and returns final order."""
    print("[Node 4] chief_trader_node executed")
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
        print(f"LLM API completely failed after retries: {e}")
        return {"error_flag": True}

def execute_order_node(state: AgentState) -> Dict[str, Any]:
    """Node 4.5: Executes the order based on Chief Trader's decision."""
    print("[Node 4.5] execute_order_node executed")
    final_order = getattr(state, "final_order", None)
    
    if not final_order:
        return {"order_result": {"success": False, "error_message": "No final_order", "timestamp": datetime.now().isoformat()}}
        
    if isinstance(final_order, dict):
        action = final_order.get("action", "HOLD")
        sl = final_order.get("sl_price", final_order.get("sl", 0.0))
        tp = final_order.get("tp_price", final_order.get("tp", 0.0))
    else:
        action = final_order.action.value if hasattr(final_order.action, 'value') else final_order.action
        sl = final_order.sl_price
        tp = final_order.tp_price
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
    if not validate_order_prices(action, entry_price, sl, tp):
        return {"order_result": {"success": False, "error_message": "Guardrail: invalid SL/TP direction or risk/reward", "timestamp": datetime.now().isoformat()}}
    setup_ok, setup_reason = validate_strategy_setup(
        action,
        entry_price,
        sl,
        getattr(state, "strategy_hypothesis", {}),
        getattr(state, "indicator_data", {}),
    )
    if not setup_ok:
        return {"order_result": {"success": False, "error_message": f"Guardrail: {setup_reason}", "timestamp": datetime.now().isoformat()}}
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
    return {"order_result": order_result_dict}

def risk_reviewer_node(state: AgentState) -> Dict[str, Any]:
    """Node 5: Risk Reviewer reviews a closed trade and logs the result."""
    print("[Node 5] risk_reviewer_node executed")
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
        review_log = response.model_dump()
        
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        docs_dir = os.path.join(base_dir, "trading_logs")
        os.makedirs(docs_dir, exist_ok=True)
        
        safe_filename = review_log.get("save_path", f"review_{datetime.now().strftime('%Y%m%d_%H%M')}.md")
        safe_filename = safe_filename.replace("/", "_").replace("\\", "_")
        if not safe_filename.endswith(".md"):
            safe_filename += ".md"
            
        file_path = os.path.join(docs_dir, safe_filename)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# Trade Review Log\n\n")
            f.write(f"**Date**: {datetime.now().isoformat()}\n\n")
            f.write(f"## Summary\n{review_log.get('trade_summary', '')}\n\n")
            f.write(f"## Risk Assessment\n{review_log.get('risk_assessment', '')}\n\n")
            f.write(f"## Lessons Learned\n{review_log.get('lessons_learned', '')}\n")

        markdown_body = (
            f"# Trade Review Log\n\n"
            f"**Date**: {datetime.now().isoformat()}\n\n"
            f"## Summary\n{review_log.get('trade_summary', '')}\n\n"
            f"## Risk Assessment\n{review_log.get('risk_assessment', '')}\n\n"
            f"## Lessons Learned\n{review_log.get('lessons_learned', '')}\n"
        )
        store_trade_review(
            DEFAULT_TRADING_LOG_DB_PATH,
            review_id=os.path.splitext(safe_filename)[0],
            trade_id=str(closed_trade.get("trade_id")) if closed_trade.get("trade_id") else None,
            symbol=closed_trade.get("symbol"),
            reviewed_at=datetime.now().isoformat(),
            source_path=file_path,
            summary=review_log.get("trade_summary", ""),
            risk_assessment=review_log.get("risk_assessment", ""),
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
            },
        )

        print(f"[Node 5] Review log saved to {file_path}")
        return {"review_log": review_log, "error_flag": False}
    except Exception as e:
        print(f"LLM API completely failed after retries: {e}")
        return {"error_flag": True}
