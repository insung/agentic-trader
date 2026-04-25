import os
import json
from datetime import datetime
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.workflows.state import AgentState
from backend.features.trading.mt5_adapter import fetch_ohlcv, get_account_summary, execute_mock_order, get_current_price, is_mt5_available
from backend.features.trading.guardrails import enforce_one_percent_rule
from backend.features.trading.market_hours import is_market_open, get_market_status_message

# Pydantic Models for Structured Output
class TechSummary(BaseModel):
    trend: str = Field(description="bullish | bearish | neutral")
    market_regime: str = Field(description="One of: Bullish, Bearish, Ranging, High Volatility")
    trade_worthy: bool = Field(description="True if the market has clear direction and is worth trading, False if choppy/flat.")
    key_observations: List[str] = Field(description="List of key observations")
    support_levels: List[float] = Field(description="Support levels")
    resistance_levels: List[float] = Field(description="Resistance levels")
    summary: str = Field(description="Comprehensive technical analysis briefing (max 3 sentences)")

class StrategyHypothesis(BaseModel):
    selected_strategy: str = Field(description="Selected strategy name")
    market_condition: str = Field(description="Current market condition assessment")
    action: str = Field(description="BUY | SELL | WAIT")
    confidence: float = Field(description="Confidence level between 0 and 1")
    reasoning: str = Field(description="Detailed explanation of the hypothesis")

class FinalOrder(BaseModel):
    action: str = Field(description="BUY | SELL | HOLD")
    sl: float = Field(description="Stop Loss price")
    tp: float = Field(description="Take Profit price")
    final_reasoning: str = Field(description="Logical reasoning for final approval or rejection")

class ReviewLog(BaseModel):
    trade_summary: str = Field(description="Overall summary of the trade")
    risk_assessment: str = Field(description="Assessment of chosen risk parameters")
    lessons_learned: str = Field(description="Key takeaways or improvements")
    save_path: str = Field(description="Suggested filename for saving the log, e.g., review_YYYYMMDD_HHMM.md")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _invoke_llm_with_retry(structured_llm, messages):
    """Invokes LLM with exponential backoff retry logic."""
    return structured_llm.invoke(messages)

def _read_prompt(agent_name: str) -> str:
    """Read the system prompt from the markdown file."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    file_path = os.path.join(base_dir, ".agents", "agents", f"{agent_name}.md")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"System prompt for {agent_name} not found."

def _read_strategies(market_regime: str = "Ranging", current_timeframes: List[str] = None) -> str:
    if current_timeframes is None:
        current_timeframes = ["M5"]
        
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    strategies_dir = os.path.join(base_dir, "docs", "trading-strategies")
    config_path = os.path.join(base_dir, "backend", "config", "strategies_config.json")
    
    strategies_text = ""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        for strat in config.get("strategies", []):
            regime_match = market_regime in strat.get("allowed_regimes", [])
            req_tfs = strat.get("required_timeframes", current_timeframes) # Default to matching if not specified
            tf_match = set(req_tfs).issubset(set(current_timeframes))
            
            if regime_match and tf_match:
                filename = strat.get("file")
                filepath = os.path.join(strategies_dir, filename)
                if os.path.exists(filepath):
                    with open(filepath, "r", encoding="utf-8") as sf:
                        strategies_text += f"\n--- {strat.get('name')} ---\n"
                        strategies_text += sf.read()
    except Exception as e:
        print(f"Error reading strategies config: {e}")
        # Fallback to returning all .md files if config fails
        if os.path.exists(strategies_dir):
            for filename in os.listdir(strategies_dir):
                if filename.endswith(".md"):
                    filepath = os.path.join(strategies_dir, filename)
                    with open(filepath, "r", encoding="utf-8") as f:
                        strategies_text += f"\n--- {filename} ---\n"
                        strategies_text += f.read()

    if not strategies_text.strip():
        strategies_text = "No matching strategies found for current market regime."
        
    return strategies_text

def fetch_data_node(state: AgentState) -> Dict[str, Any]:
    """Node 1: Fetch OHLCV Data and calculate indicators."""
    print("[Node 1] fetch_data_node executed")
    symbol = getattr(state, "symbol", "EURUSD")
    timeframes = getattr(state, "timeframes", ["M5"])
    
    # 시장 휴장 체크
    if not is_market_open():
        msg = get_market_status_message()
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
    
    for tf in timeframes:
        df = fetch_ohlcv(symbol, tf, 100)
        if df.empty:
            print(f"❌ No OHLCV data for {symbol} on {tf}.")
            continue
        recent_data = df.tail(10).to_json(orient='records')
        raw_data += f"\n[{tf} Timeframe Market Data (last 10 candles)]:\n{recent_data}\n"
        
    return {"raw_data": raw_data, "account_info": account_info, "error_flag": False}

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
    human_content = f"Here is the Strategy Hypothesis:\n{getattr(state, 'strategy_hypothesis', {})}\n\n"
    human_content += f"Account Info: {json.dumps(account_info)}"
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_content)]
    
    try:
        response = _invoke_llm_with_retry(structured_llm, messages)
        
        # 실시간 가격 조회
        symbol = getattr(state, "symbol", "EURUSD")
        current_price = get_current_price(symbol)
        entry_price = current_price.get("ask", 0.0) if response.action.upper() == "BUY" else current_price.get("bid", 0.0)
        
        final_order_dict = {
            "action": response.action,
            "symbol": symbol,
            "entry_price": entry_price,
            "sl_price": response.sl,
            "tp_price": response.tp,
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
        
    action = final_order.action.value if hasattr(final_order.action, 'value') else final_order.action
    if action.upper() not in ["BUY", "SELL"]:
        return {"order_result": {"success": False, "error_message": f"Action was {action}", "timestamp": datetime.now().isoformat()}}
        
    symbol = getattr(state, "symbol", "EURUSD")
    sl = final_order.sl_price
    tp = final_order.tp_price
    
    account_info = get_account_summary()
    balance = account_info.get("balance", 10000.0)
    
    # 실시간 가격 조회
    current_price = get_current_price(symbol)
    entry_price = current_price.get("ask", 0.0) if action.upper() == "BUY" else current_price.get("bid", 0.0)
    if entry_price <= 0:
        return {"order_result": {"success": False, "error_message": "Could not get current price", "timestamp": datetime.now().isoformat()}}
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
    """Node 5: Risk Reviewer reviews the entire process and logs the result."""
    print("[Node 5] risk_reviewer_node executed")
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    structured_llm = llm.with_structured_output(ReviewLog)
    
    system_prompt = _read_prompt("risk_reviewer")
    final_order = getattr(state, "final_order", None)
    order_result = getattr(state, "order_result", None)
    
    human_content = json.dumps({
        "raw_data": getattr(state, "raw_data", ""),
        "tech_summary": getattr(state, "tech_summary", {}),
        "strategy_hypothesis": getattr(state, "strategy_hypothesis", {}),
        "final_order": final_order.model_dump() if hasattr(final_order, "model_dump") else (final_order or {}),
        "order_result": order_result.model_dump() if hasattr(order_result, "model_dump") else (order_result or {})
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
        
        print(f"[Node 5] Review log saved to {file_path}")
        return {"review_log": review_log, "error_flag": False}
    except Exception as e:
        print(f"LLM API completely failed after retries: {e}")
        return {"error_flag": True}