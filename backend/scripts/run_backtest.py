"""
Agentic Backtest Runner
========================
저장된 과거 데이터(SQLite 기본, CSV 호환)를 캔들 단위로 순회하면서
LangGraph 에이전트 파이프라인(app.invoke)을 반복 호출하여
AI의 실제 매매 판단을 과거 데이터 위에서 시뮬레이션합니다.

사용법:
    python -m backend.scripts.run_backtest --symbol BTCUSD --timeframes M15,M30 --from 2025-01-01 --to 2025-01-31
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch, MagicMock

import pandas as pd

from backend.features.trading.backtest_store import (
    DEFAULT_BACKTEST_DB_PATH,
    calculate_candle_quality,
    finish_backtest_run,
    load_candles,
    mark_backtest_run_status,
    record_backtest_decision,
    record_backtest_trade,
    start_backtest_run,
    store_backtest_report,
)
from backend.features.trading.guardrails import validate_order_prices
from backend.features.trading.position_tracker import build_decision_context, review_closed_trade
from backend.features.trading.strategy_validators import validate_strategy_setup

# 프로젝트 루트를 기준으로 경로 설정
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 기본 설정
DEFAULT_INITIAL_BALANCE = 10_000.0
DEFAULT_RISK_PER_TRADE_PCT = 0.005
LOOKBACK_CANDLES = 100  # 각 시점에서 에이전트에게 보여줄 과거 캔들 수
STEP_INTERVAL = 5       # 몇 캔들마다 파이프라인을 호출할지 (비용 절감)

LOG_LEVEL_ORDER = {
    "TRACE": 10,
    "DEBUG": 20,
    "INFO": 30,
    "WARNING": 40,
    "ERROR": 50,
}


class BacktestEventLogger:
    """Write compact JSONL events that can be replayed by humans or AI agents."""

    def __init__(
        self,
        path: Optional[str] = None,
        base_context: Optional[Dict[str, Any]] = None,
        min_level: str = "TRACE",
    ):
        self.path = path
        self.base_context = base_context or {}
        self.min_level = min_level.upper()
        self.min_level_value = LOG_LEVEL_ORDER.get(self.min_level, LOG_LEVEL_ORDER["TRACE"])
        self._fh = None
        if path:
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            self._fh = open(path, "a", encoding="utf-8")

    def emit(self, event: str, level: str = "INFO", **fields: Any) -> None:
        if not self._fh:
            return
        normalized_level = level.upper()
        if LOG_LEVEL_ORDER.get(normalized_level, LOG_LEVEL_ORDER["INFO"]) < self.min_level_value:
            return
        payload = {
            "ts": datetime.now().isoformat(),
            "level": normalized_level,
            "event": event,
            **self.base_context,
            **fields,
        }
        self._fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None


def _model_to_dict(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def load_backtest_data_from_sqlite(
    db_path: str,
    symbol: str,
    timeframes: List[str],
    from_date: str,
    to_date: str,
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, Dict[str, Any]]]:
    """Load timeframe DataFrames from the SQLite candle store."""
    dfs: Dict[str, pd.DataFrame] = {}
    metadata: Dict[str, Dict[str, Any]] = {}
    for tf in timeframes:
        tf = tf.strip().upper()
        df = load_candles(db_path, symbol, tf, from_date, to_date)
        if df.empty:
            raise ValueError(f"No candle data for {symbol} {tf} between {from_date} and {to_date}")
        dfs[tf] = df
        metadata[tf] = calculate_candle_quality(df)
    return dfs, metadata


def _calculate_run_statistics(trades: List[Dict[str, Any]], initial_balance: float, final_balance: float) -> Dict[str, Any]:
    pnls = [float(t.get("pnl", 0.0) or 0.0) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_loss = abs(sum(losses))
    profit_factor = (sum(wins) / gross_loss) if gross_loss > 0 else None

    cumulative = initial_balance
    peak = initial_balance
    max_dd = 0.0
    for pnl in pnls:
        cumulative += pnl
        peak = max(peak, cumulative)
        if peak > 0:
            max_dd = max(max_dd, (peak - cumulative) / peak * 100)

    return {
        "net_pnl": round(final_balance - initial_balance, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "max_drawdown_pct": round(max_dd, 2),
    }


class BacktestEngine:
    """
    과거 데이터를 LangGraph 파이프라인에 밀어 넣는 시뮬레이터.
    MT5 API 호출을 모킹(Mocking)하여 과거 데이터를 반환하도록 합니다.
    """

    def __init__(
        self,
        data_paths: Optional[List[str]] = None,
        symbol: str = "EURUSD",
        timeframes: List[str] = None,
        dfs: Optional[Dict[str, pd.DataFrame]] = None,
        data_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
        initial_balance: float = DEFAULT_INITIAL_BALANCE,
        risk_per_trade_pct: float = DEFAULT_RISK_PER_TRADE_PCT,
        step_interval: int = STEP_INTERVAL,
        start_step: int = 0,
        max_steps: Optional[int] = None,
        review_trades: bool = True,
        result_db_path: Optional[str] = None,
        run_id: Optional[str] = None,
        event_log_path: Optional[str] = None,
        event_log_level: str = "TRACE",
    ):
        self.data_paths = data_paths or []
        self.symbol = symbol
        self.timeframes = [tf.strip().upper() for tf in (timeframes if timeframes else ["M5"])]
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.risk_per_trade_pct = risk_per_trade_pct
        self.step_interval = step_interval
        self.start_step = max(start_step, 0)
        self.max_steps = max_steps
        self.review_trades = review_trades
        self.result_db_path = result_db_path
        self.run_id = run_id
        self.event_logger = BacktestEventLogger(
            event_log_path,
            {
                "run_id": run_id,
                "symbol": symbol,
                "timeframes": self.timeframes,
            },
            min_level=event_log_level,
        )

        # 전체 과거 데이터 로드
        self.dfs = dfs or {}
        if self.dfs:
            for tf in self.timeframes:
                df = self.dfs[tf]
                print(f"📂 데이터 로드 완료 ({tf}): {len(df)}개 캔들 ({df['time'].iloc[0]} ~ {df['time'].iloc[-1]})")
        else:
            for path, tf in zip(self.data_paths, self.timeframes):
                df = pd.read_csv(path.strip(), parse_dates=["time"])
                self.dfs[tf] = df
                print(f"📂 CSV 데이터 로드 완료 ({tf}): {len(df)}개 캔들 ({df['time'].iloc[0]} ~ {df['time'].iloc[-1]})")
            
        # 가장 작은 타임프레임을 루프 기준으로 설정 (보통 리스트의 첫 번째 값)
        self.base_tf = self.timeframes[0]
        if self.base_tf not in self.dfs:
            raise ValueError(f"Base timeframe data is missing: {self.base_tf}")
        self.df_base = self.dfs[self.base_tf]
        self.data_metadata = data_metadata or {
            tf: calculate_candle_quality(df) for tf, df in self.dfs.items()
        }

        # 결과 기록
        self.trades: List[Dict[str, Any]] = []
        self.decisions: List[Dict[str, Any]] = []
        self.equity_curve: List[Dict[str, Any]] = []
        self.open_position: Optional[Dict[str, Any]] = None

    def _emit_event(self, event: str, level: str = "INFO", **fields: Any) -> None:
        self.event_logger.emit(event, level=level, **fields)

    def _record_decision(
        self,
        current_time: Any,
        action: str,
        status: str,
        final_state: Optional[Dict[str, Any]] = None,
        rejection_reason: Optional[str] = None,
        final_order: Optional[Dict[str, Any]] = None,
    ) -> None:
        final_state = final_state or {}
        strategy_hypothesis = final_state.get("strategy_hypothesis", {}) or {}
        tech_summary = final_state.get("tech_summary", {}) or {}
        decision = {
            "decision_time": str(current_time),
            "action": str(action).upper(),
            "strategy": strategy_hypothesis.get("selected_strategy"),
            "market_regime": tech_summary.get("market_regime") or strategy_hypothesis.get("market_condition"),
            "status": status,
            "rejection_reason": rejection_reason,
            "indicator_snapshot": final_state.get("indicator_data", {}),
            "final_order": final_order or final_state.get("final_order", {}),
        }
        self.decisions.append(decision)
        self._emit_event(
            "decision_recorded",
            level="DEBUG",
            candle_time=str(current_time),
            action=decision["action"],
            status=status,
            strategy=decision["strategy"],
            market_regime=decision["market_regime"],
            rejection_reason=rejection_reason,
        )
        if self.result_db_path and self.run_id:
            record_backtest_decision(self.result_db_path, run_id=self.run_id, decision=decision)

    def _build_mock_ohlcv(self, window: pd.DataFrame) -> pd.DataFrame:
        """과거 데이터의 특정 윈도우를 fetch_ohlcv가 반환하는 형태로 가공합니다."""
        return window.copy().reset_index(drop=True)

    def _build_mock_price(self, row: pd.Series) -> dict:
        """현재 캔들의 종가를 기반으로 get_current_price 반환값을 모킹합니다."""
        return {
            "bid": row["close"],
            "ask": row["close"],
            "last": row["close"],
            "time": int(row["time"].timestamp()) if hasattr(row["time"], "timestamp") else 0,
        }

    def _build_mock_account(self) -> dict:
        """현재 잔고를 기반으로 계좌 정보를 반환합니다."""
        return {
            "login": 0,
            "server": "Backtest",
            "balance": self.balance,
            "equity": self.balance,
            "margin": 0.0,
            "margin_free": self.balance,
            "leverage": 100,
            "currency": "USD",
        }

    def _calculate_pnl(self, position: Dict[str, Any], exit_price: float) -> float:
        if position["action"] == "BUY":
            pnl = (exit_price - position["entry_price"]) * position["lot_size"]
        else:
            pnl = (position["entry_price"] - exit_price) * position["lot_size"]
        return float(round(pnl, 2))

    def _build_closed_trade(
        self,
        position: Dict[str, Any],
        candle: pd.Series,
        result: str,
        exit_reason: str,
        exit_price: float,
    ) -> Dict[str, Any]:
        pnl = self._calculate_pnl(position, exit_price)
        self.balance += pnl
        return {
            **position,
            "exit_step": int(candle.name) if candle.name is not None else None,
            "exit_time": str(candle["time"]),
            "exit_price": float(exit_price),
            "exit_reason": exit_reason,
            "result": result,
            "pnl": pnl,
        }

    def _evaluate_open_position(self, position: Dict[str, Any], candles: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Evaluate an already-open position against newly elapsed candles."""
        for _, candle in candles.iterrows():
            high = candle["high"]
            low = candle["low"]

            if position["action"] == "BUY":
                if low <= position["sl"]:
                    return self._build_closed_trade(position, candle, "SL_HIT", "Stop Loss", position["sl"])
                if high >= position["tp"]:
                    return self._build_closed_trade(position, candle, "TP_HIT", "Take Profit", position["tp"])
            elif position["action"] == "SELL":
                if high >= position["sl"]:
                    return self._build_closed_trade(position, candle, "SL_HIT", "Stop Loss", position["sl"])
                if low <= position["tp"]:
                    return self._build_closed_trade(position, candle, "TP_HIT", "Take Profit", position["tp"])

        return None

    def _review_closed_trade(self, closed_trade: Dict[str, Any]) -> None:
        review_closed_trade(closed_trade.get("decision_context", {}), closed_trade)

    def _record_closed_trade(self, closed_trade: Dict[str, Any]) -> None:
        self.trades.append(closed_trade)
        self._emit_event(
            "trade_closed",
            level="INFO",
            trade_id=closed_trade.get("trade_id"),
            action=closed_trade.get("action"),
            entry_time=closed_trade.get("entry_time"),
            exit_time=closed_trade.get("exit_time"),
            exit_reason=closed_trade.get("exit_reason"),
            pnl=closed_trade.get("pnl"),
            balance=self.balance,
        )
        if self.result_db_path and self.run_id:
            record_backtest_trade(
                self.result_db_path,
                run_id=self.run_id,
                symbol=self.symbol,
                trade=closed_trade,
            )
        if self.review_trades:
            review_started_at = time.perf_counter()
            self._review_closed_trade(closed_trade)
            self._emit_event(
                "trade_review_completed",
                level="DEBUG",
                trade_id=closed_trade.get("trade_id"),
                elapsed_ms=round((time.perf_counter() - review_started_at) * 1000, 2),
            )
        else:
            self._emit_event(
                "trade_review_skipped",
                level="DEBUG",
                trade_id=closed_trade.get("trade_id"),
                reason="--no-review",
            )

    def _close_open_position_at_end(self) -> None:
        if not self.open_position:
            return

        last_candle = self.df_base.iloc[-1]
        closed = self._build_closed_trade(
            self.open_position,
            last_candle,
            "BACKTEST_END",
            "Backtest End",
            float(last_candle["close"]),
        )
        self._record_closed_trade(closed)
        self.open_position = None
        print(
            f"   ⏹ {closed['action']} @ {closed['entry_price']:.5f} → "
            f"{closed['exit_reason']} @ {closed['exit_price']:.5f} | PnL: ${closed['pnl']:.2f}"
        )

    def run(self) -> List[Dict[str, Any]]:
        """
        백테스트를 실행합니다.
        과거 데이터를 step_interval 간격으로 슬라이싱하여
        각 시점에서 LangGraph 파이프라인을 호출합니다.
        """
        total_candles = len(self.df_base)
        if total_candles < LOOKBACK_CANDLES + 1:
            print(f"❌ 데이터 부족: {total_candles}개 캔들 (최소 {LOOKBACK_CANDLES + 1}개 필요)")
            return []

        # LangGraph 그래프 컴파일 (import를 여기서 수행하여 모킹 범위 밖에서 초기화)
        from backend.workflows.graph import get_compiled_graph
        graph = get_compiled_graph()

        start_idx = LOOKBACK_CANDLES
        step_positions = list(range(start_idx, total_candles, self.step_interval))
        if self.start_step:
            step_positions = step_positions[self.start_step :]
        if self.max_steps is not None:
            step_positions = step_positions[: max(self.max_steps, 0)]
        total_steps = len(step_positions)

        print(f"\n🚀 백테스트 시작: {self.symbol}")
        print(f"   총 {total_steps}개 시점에서 파이프라인 호출 예정")
        print(f"   초기 잔고: ${self.initial_balance:,.2f}")
        print(f"   Step Interval: {self.step_interval} 캔들")
        if self.start_step:
            print(f"   Start Step Offset: {self.start_step}")
        if self.max_steps is not None:
            print(f"   Max Steps: {self.max_steps}")
        if not self.review_trades:
            print("   Risk Reviewer: disabled (--no-review)")
        print("=" * 60)
        self._emit_event(
            "backtest_start",
            total_candles=total_candles,
            total_steps=total_steps,
            initial_balance=self.initial_balance,
            risk_per_trade_pct=self.risk_per_trade_pct,
            step_interval=self.step_interval,
            start_step=self.start_step,
            max_steps=self.max_steps,
            review_trades=self.review_trades,
        )

        for step_num, i in enumerate(step_positions, 1):
            step_started_at = time.perf_counter()
            current_time = self.df_base.iloc[i]["time"]
            current_candle = self.df_base.iloc[i]

            print(f"\n--- Step {step_num}/{total_steps} | {current_time} | Balance: ${self.balance:,.2f} ---")
            self._emit_event(
                "step_start",
                level="TRACE",
                step=step_num,
                step_index=i,
                candle_time=str(current_time),
                balance=self.balance,
                open_position=bool(self.open_position),
            )

            # 각 타임프레임별로 현재 시간 이하의 캔들만 잘라서 반환하도록 모킹
            def mock_fetch_ohlcv_func(sym, tf, count):
                if tf not in self.dfs:
                    return pd.DataFrame()
                df = self.dfs[tf]
                window = df[df["time"] <= current_time].tail(count)
                return self._build_mock_ohlcv(window)

            mock_price = self._build_mock_price(current_candle)
            mock_account = self._build_mock_account()

            # MT5 함수들을 모킹하여 과거 데이터를 반환하도록 패치
            with patch("backend.workflows.nodes.fetch_ohlcv", side_effect=mock_fetch_ohlcv_func), \
                 patch("backend.workflows.nodes.get_current_price", return_value=mock_price), \
                 patch("backend.workflows.nodes.get_account_summary", return_value=mock_account), \
                 patch("backend.workflows.nodes.is_mt5_available", return_value=True), \
                 patch("backend.workflows.nodes.is_market_open", return_value=True), \
                 patch("backend.workflows.nodes.execute_mock_order", side_effect=lambda *a, **kw: {
                     "retcode": 10009, "order": step_num, "price": mock_price["ask"],
                     "volume": a[2] if len(a) > 2 else 0.01
                 }):

                try:
                    if self.open_position:
                        start = int(self.open_position.get("last_checked_index", self.open_position["entry_index"])) + 1
                        elapsed_candles = self.df_base.iloc[start : i + 1]
                        closed_trade = self._evaluate_open_position(self.open_position, elapsed_candles)

                        if closed_trade:
                            self._record_closed_trade(closed_trade)
                            self.open_position = None
                            self.equity_curve.append({"time": str(current_time), "balance": self.balance, "action": "CLOSED"})
                            result_emoji = "✅" if closed_trade["pnl"] >= 0 else "❌"
                            print(
                                f"   {result_emoji} {closed_trade['action']} @ {closed_trade['entry_price']:.5f} → "
                                f"{closed_trade['exit_reason']} @ {closed_trade['exit_price']:.5f} | PnL: ${closed_trade['pnl']:.2f}"
                            )
                            self._emit_event(
                                "step_complete",
                                level="TRACE",
                                step=step_num,
                                candle_time=str(current_time),
                                status="CLOSED",
                                elapsed_ms=round((time.perf_counter() - step_started_at) * 1000, 2),
                            )
                            continue

                        self.open_position["last_checked_index"] = i
                        self.equity_curve.append({"time": str(current_time), "balance": self.balance, "action": "OPEN"})
                        print(f"   ⏳ 포지션 보유 중: {self.open_position['action']} from {self.open_position['entry_time']}")
                        self._emit_event(
                            "position_hold",
                            level="DEBUG",
                            step=step_num,
                            candle_time=str(current_time),
                            trade_id=self.open_position.get("trade_id"),
                            action=self.open_position.get("action"),
                        )
                        self._emit_event(
                            "step_complete",
                            level="TRACE",
                            step=step_num,
                            candle_time=str(current_time),
                            status="OPEN",
                            elapsed_ms=round((time.perf_counter() - step_started_at) * 1000, 2),
                        )
                        continue

                    initial_state = {"symbol": self.symbol, "timeframes": self.timeframes}
                    final_state = {}

                    graph_started_at = time.perf_counter()
                    stream_iter = iter(graph.stream(initial_state))
                    while True:
                        node_started_at = time.perf_counter()
                        try:
                            s = next(stream_iter)
                        except StopIteration:
                            break
                        node_elapsed_ms = round((time.perf_counter() - node_started_at) * 1000, 2)
                        node_name = list(s.keys())[0]
                        self._emit_event(
                            "node_complete",
                            level="TRACE",
                            step=step_num,
                            candle_time=str(current_time),
                            node=node_name,
                            elapsed_ms=node_elapsed_ms,
                        )
                        final_state.update(list(s.values())[0])
                    self._emit_event(
                        "graph_complete",
                        level="DEBUG",
                        step=step_num,
                        candle_time=str(current_time),
                        elapsed_ms=round((time.perf_counter() - graph_started_at) * 1000, 2),
                    )

                    # 결과 분석
                    if final_state.get("error_flag"):
                        print(f"   ⚠️ 에러 발생: {final_state.get('error_message', 'Unknown')}")
                        self._record_decision(current_time, "ERROR", "ERROR", final_state, final_state.get("error_message"))
                        self._emit_event(
                            "step_complete",
                            level="TRACE",
                            step=step_num,
                            candle_time=str(current_time),
                            status="ERROR",
                            elapsed_ms=round((time.perf_counter() - step_started_at) * 1000, 2),
                        )
                        continue

                    final_order = _model_to_dict(final_state.get("final_order"))
                    if not final_order:
                        print("   📊 매매 신호 없음 (Tech Analyst가 시장 비적합 판단)")
                        self._record_decision(current_time, "SKIP", "SKIP", final_state)
                        self.equity_curve.append({"time": str(current_time), "balance": self.balance, "action": "SKIP"})
                        self._emit_event(
                            "step_complete",
                            level="TRACE",
                            step=step_num,
                            candle_time=str(current_time),
                            status="SKIP",
                            elapsed_ms=round((time.perf_counter() - step_started_at) * 1000, 2),
                        )
                        continue

                    action = final_order.get("action", "HOLD")
                    if action.upper() in ("HOLD", "WAIT"):
                        print(f"   🛑 Chief Trader 판단: {action}")
                        self._record_decision(current_time, action, "HOLD", final_state, final_order=final_order)
                        self.equity_curve.append({"time": str(current_time), "balance": self.balance, "action": action})
                        self._emit_event(
                            "step_complete",
                            level="TRACE",
                            step=step_num,
                            candle_time=str(current_time),
                            status=action.upper(),
                            elapsed_ms=round((time.perf_counter() - step_started_at) * 1000, 2),
                        )
                        continue

                    # 유효한 매매 결정
                    sl = float(final_order.get("sl_price", final_order.get("sl", 0.0)))
                    tp = float(final_order.get("tp_price", final_order.get("tp", 0.0)))
                    entry_price = float(mock_price["ask"] if action.upper() == "BUY" else mock_price["bid"])
                    if not validate_order_prices(action, entry_price, sl, tp):
                        print(
                            f"   ⛔ 가드레일: SL/TP 방향 또는 손익비 오류 "
                            f"(action={action}, entry={entry_price:.5f}, sl={sl:.5f}, tp={tp:.5f})"
                        )
                        self._record_decision(
                            current_time,
                            action,
                            "REJECTED",
                            final_state,
                            "invalid SL/TP direction or risk/reward",
                            final_order,
                        )
                        self.equity_curve.append({"time": str(current_time), "balance": self.balance, "action": "REJECTED"})
                        self._emit_event(
                            "step_complete",
                            level="TRACE",
                            step=step_num,
                            candle_time=str(current_time),
                            status="REJECTED",
                            rejection_reason="invalid SL/TP direction or risk/reward",
                            elapsed_ms=round((time.perf_counter() - step_started_at) * 1000, 2),
                        )
                        continue
                    setup_ok, setup_reason = validate_strategy_setup(
                        action,
                        entry_price,
                        sl,
                        final_state.get("strategy_hypothesis", {}),
                        final_state.get("indicator_data", {}),
                    )
                    if not setup_ok:
                        print(f"   ⛔ 전략 검증 실패: {setup_reason}")
                        self._record_decision(current_time, action, "REJECTED", final_state, setup_reason, final_order)
                        self.equity_curve.append({"time": str(current_time), "balance": self.balance, "action": "REJECTED"})
                        self._emit_event(
                            "step_complete",
                            level="TRACE",
                            step=step_num,
                            candle_time=str(current_time),
                            status="REJECTED",
                            rejection_reason=setup_reason,
                            elapsed_ms=round((time.perf_counter() - step_started_at) * 1000, 2),
                        )
                        continue

                    # 리스크 퍼센트 룰로 랏 계산
                    from backend.features.trading.guardrails import enforce_one_percent_rule
                    lot_size = enforce_one_percent_rule(self.balance, entry_price, sl, risk_pct=self.risk_per_trade_pct)

                    if lot_size <= 0:
                        print(f"   ⛔ 가드레일: 랏 사이즈 0 (SL 거리 이상)")
                        self._record_decision(current_time, action, "REJECTED", final_state, "lot size calculated to <= 0", final_order)
                        self._emit_event(
                            "step_complete",
                            level="TRACE",
                            step=step_num,
                            candle_time=str(current_time),
                            status="REJECTED",
                            rejection_reason="lot size calculated to <= 0",
                            elapsed_ms=round((time.perf_counter() - step_started_at) * 1000, 2),
                        )
                        continue

                    trade_record = {
                        "trade_id": f"BT-{step_num}",
                        "step": step_num,
                        "entry_step": step_num,
                        "time": str(current_time),
                        "entry_time": str(current_time),
                        "entry_index": i,
                        "last_checked_index": i,
                        "action": action.upper(),
                        "entry_price": entry_price,
                        "sl": sl,
                        "tp": tp,
                        "lot_size": float(lot_size),
                        "reasoning": final_order.get("reasoning", final_order.get("final_reasoning", "")),
                    }
                    order_result = {
                        "success": True,
                        "ticket": step_num,
                        "executed_price": entry_price,
                        "timestamp": datetime.now().isoformat(),
                    }
                    trade_record["decision_context"] = build_decision_context(final_state, order_result)
                    strategy_hypothesis = final_state.get("strategy_hypothesis", {}) or {}
                    tech_summary = final_state.get("tech_summary", {}) or {}
                    trade_record["strategy"] = strategy_hypothesis.get("selected_strategy")
                    trade_record["market_regime"] = tech_summary.get("market_regime") or strategy_hypothesis.get("market_condition")
                    self.open_position = trade_record
                    self._record_decision(current_time, action, "OPENED", final_state, final_order=final_order)
                    self.equity_curve.append({"time": str(current_time), "balance": self.balance, "action": action})
                    print(f"   📌 {action} opened @ {entry_price:.5f} | SL: {sl:.5f} | TP: {tp:.5f}")
                    self._emit_event(
                        "trade_opened",
                        level="INFO",
                        step=step_num,
                        candle_time=str(current_time),
                        trade_id=trade_record["trade_id"],
                        action=action.upper(),
                        strategy=trade_record["strategy"],
                        market_regime=trade_record["market_regime"],
                        entry_price=entry_price,
                        sl=sl,
                        tp=tp,
                        lot_size=float(lot_size),
                    )
                    self._emit_event(
                        "step_complete",
                        level="TRACE",
                        step=step_num,
                        candle_time=str(current_time),
                        status="OPENED",
                        elapsed_ms=round((time.perf_counter() - step_started_at) * 1000, 2),
                    )

                except Exception as e:
                    print(f"   💥 파이프라인 에러: {e}")
                    self._emit_event(
                        "step_error",
                        level="ERROR",
                        step=step_num,
                        candle_time=str(current_time),
                        error=str(e),
                        elapsed_ms=round((time.perf_counter() - step_started_at) * 1000, 2),
                    )
                    import traceback
                    traceback.print_exc()
                    continue

        self._close_open_position_at_end()

        print("\n" + "=" * 60)
        print(f"🏁 백테스트 완료!")
        print(f"   최종 잔고: ${self.balance:,.2f} (변동: ${self.balance - self.initial_balance:+,.2f})")
        print(f"   총 매매 횟수: {len(self.trades)}")
        self._emit_event(
            "backtest_complete",
            final_balance=self.balance,
            net_pnl=round(self.balance - self.initial_balance, 2),
            total_trades=len(self.trades),
            total_decisions=len(self.decisions),
        )

        return self.trades


def main():
    parser = argparse.ArgumentParser(description="Agentic Backtest Runner")
    parser.add_argument("--data", type=str, help="Deprecated: 콤마로 구분된 CSV 데이터 파일 경로들")
    parser.add_argument("--data-db", type=str, default=DEFAULT_BACKTEST_DB_PATH, help="SQLite market data DB path")
    parser.add_argument("--from", dest="from_date", type=str, help="백테스트 시작일 (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", type=str, help="백테스트 종료일 (YYYY-MM-DD)")
    parser.add_argument("--symbol", type=str, default="EURUSD", help="종목 코드 (기본: EURUSD)")
    parser.add_argument("--timeframes", type=str, default="M5", help="콤마로 구분된 타임프레임 (예: M5,H1)")
    parser.add_argument("--balance", type=float, default=DEFAULT_INITIAL_BALANCE, help="초기 잔고 (기본: 10000)")
    parser.add_argument("--risk-pct", type=float, default=DEFAULT_RISK_PER_TRADE_PCT, help="거래당 계좌 리스크 비율 (기본: 0.005 = 0.5%)")
    parser.add_argument("--step", type=int, default=STEP_INTERVAL, help="파이프라인 호출 간격 (캔들 수, 기본: 5)")
    parser.add_argument("--start-step", type=int, default=0, help="디버그용으로 건너뛸 파이프라인 판단 횟수")
    parser.add_argument("--max-steps", type=int, help="디버그용 최대 파이프라인 호출 횟수")
    parser.add_argument("--no-review", action="store_true", help="청산 후 Risk Reviewer LLM 복기를 생략")
    parser.add_argument("--log-file", type=str, help="구조화 JSONL 백테스트 로그 경로")
    parser.add_argument(
        "--log-level",
        choices=["TRACE", "DEBUG", "INFO", "WARNING", "ERROR"],
        default="TRACE",
        help="JSONL 로그 최소 레벨 (기본: TRACE)",
    )
    parser.add_argument("--report", action="store_true", help="백테스트 완료 후 리포트 자동 생성")
    args = parser.parse_args()

    data_paths = [path.strip() for path in args.data.split(",")] if args.data else []
    timeframes = [tf.strip().upper() for tf in args.timeframes.split(",") if tf.strip()]
    dfs = None
    data_metadata = None
    data_from = args.from_date
    data_to = args.to_date

    if data_paths:
        print("⚠️ --data CSV input is deprecated. Prefer --data-db with --from/--to.")
        if len(data_paths) != len(timeframes):
            print(f"❌ 데이터 파일 수({len(data_paths)})와 타임프레임 수({len(timeframes)})가 일치해야 합니다.")
            sys.exit(1)
        for path in data_paths:
            if not os.path.exists(path.strip()):
                print(f"❌ 데이터 파일을 찾을 수 없습니다: {path.strip()}")
                sys.exit(1)
    else:
        if not args.from_date or not args.to_date:
            print("❌ SQLite 백테스트에는 --from YYYY-MM-DD 및 --to YYYY-MM-DD가 필요합니다.")
            sys.exit(1)
        try:
            dfs, data_metadata = load_backtest_data_from_sqlite(
                args.data_db,
                args.symbol,
                timeframes,
                args.from_date,
                args.to_date,
            )
        except ValueError as exc:
            print(f"❌ {exc}")
            sys.exit(1)

    run_id = f"{args.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    log_file = args.log_file
    if not log_file:
        logs_dir = os.path.join(PROJECT_ROOT, "backtests", "logs")
        log_file = os.path.join(logs_dir, f"backtest_{run_id}.jsonl")
    engine = BacktestEngine(
        data_paths=data_paths,
        symbol=args.symbol,
        timeframes=timeframes,
        dfs=dfs,
        data_metadata=data_metadata,
        initial_balance=args.balance,
        risk_per_trade_pct=args.risk_pct,
        step_interval=args.step,
        start_step=args.start_step,
        max_steps=args.max_steps,
        review_trades=not args.no_review,
        result_db_path=args.data_db,
        run_id=run_id,
        event_log_path=log_file,
        event_log_level=args.log_level,
    )
    if data_from is None:
        data_from = engine.df_base["time"].iloc[0].strftime("%Y-%m-%d %H:%M:%S")
    if data_to is None:
        data_to = engine.df_base["time"].iloc[-1].strftime("%Y-%m-%d %H:%M:%S")

    start_backtest_run(
        args.data_db,
        {
            "run_id": run_id,
            "symbol": args.symbol,
            "timeframes": timeframes,
            "base_timeframe": engine.base_tf,
            "data_from": data_from,
            "data_to": data_to,
            "initial_balance": args.balance,
            "final_balance": None,
            "risk_per_trade_pct": engine.risk_per_trade_pct,
            "step_interval": engine.step_interval,
            "total_trades": 0,
        },
    )
    print(f"💾 SQLite 백테스트 실행 row 생성: {args.data_db} (run_id={run_id})")
    print(f"🧾 구조화 로그: {log_file}")
    try:
        trades = engine.run()
    except KeyboardInterrupt:
        mark_backtest_run_status(
            args.data_db,
            run_id=run_id,
            status="interrupted",
            error_message="KeyboardInterrupt",
        )
        engine.event_logger.close()
        print(f"\n⚠️ 백테스트 중단됨: run_id={run_id}")
        sys.exit(130)
    except Exception as exc:
        mark_backtest_run_status(
            args.data_db,
            run_id=run_id,
            status="failed",
            error_message=str(exc),
        )
        engine.event_logger.close()
        raise
    report_archive: Optional[Dict[str, Any]] = None

    if args.report and trades:
        from backend.features.trading.reporting import generate_backtest_report, _summarize_decisions
        report_path = generate_backtest_report(
            trades=trades,
            equity_curve=engine.equity_curve,
            df=engine.df_base,
            symbol=args.symbol,
            initial_balance=args.balance,
            final_balance=engine.balance,
            chart_timeframe=engine.base_tf,
            decision_timeframes=engine.timeframes,
            step_interval=engine.step_interval,
            risk_per_trade_pct=engine.risk_per_trade_pct,
            data_quality=engine.data_metadata,
            decisions=engine.decisions,
        )
        print(f"\n📄 리포트 생성 완료: {report_path}")
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report_body = f.read()
            chart_path = None
            if "![Backtest Chart](./" in report_body:
                start = report_body.find("![Backtest Chart](./") + len("![Backtest Chart](./")
                end = report_body.find(")", start)
                if end != -1:
                    chart_rel = report_body[start:end]
                    chart_path = os.path.join(os.path.dirname(report_path), chart_rel)
            report_archive = {
                "report_id": os.path.splitext(os.path.basename(report_path))[0],
                "run_id": run_id,
                "symbol": args.symbol,
                "report_path": None,
                "markdown_body": report_body,
                "chart_path": None,
                "report_created_at": datetime.now().isoformat(),
                "summary_json": {
                    "chart_timeframe": engine.base_tf,
                    "decision_timeframes": engine.timeframes,
                    "step_interval": engine.step_interval,
                    "risk_per_trade_pct": engine.risk_per_trade_pct,
                    "event_log_path": log_file,
                    "event_log_level": args.log_level,
                    "start_step": args.start_step,
                    "max_steps": args.max_steps,
                    "review_trades": engine.review_trades,
                    "data_quality": engine.data_metadata,
                    "decision_summary": _summarize_decisions(engine.decisions),
                    "artifact_path_ignored": True,
                    "generated_report_filename": os.path.basename(report_path),
                    "generated_chart_filename": os.path.basename(chart_path) if chart_path else None,
                },
            }
        except OSError as exc:
            print(f"⚠️ SQLite report archive failed: {exc}")
    elif args.report and not trades:
        print("\n⚠️ 매매 기록이 없어 리포트를 생성하지 않습니다.")

    stats = _calculate_run_statistics(trades, args.balance, engine.balance)
    finish_backtest_run(
        args.data_db,
        run_id=run_id,
        final_balance=engine.balance,
        total_trades=len(trades),
        net_pnl=stats["net_pnl"],
        profit_factor=stats["profit_factor"],
        max_drawdown_pct=stats["max_drawdown_pct"],
    )
    print(f"💾 SQLite 백테스트 요약 갱신: {args.data_db} (run_id={run_id})")
    if report_archive:
        store_backtest_report(args.data_db, **report_archive)

    # JSON으로도 원본 데이터 저장
    if trades:
        results_dir = os.path.join(PROJECT_ROOT, "backtests", "results")
        os.makedirs(results_dir, exist_ok=True)
        json_path = os.path.join(results_dir, f"backtest_{args.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "symbol": args.symbol,
                "run_id": run_id,
                "initial_balance": args.balance,
                "final_balance": engine.balance,
                "data_paths": [path.strip() for path in data_paths],
                "data_db": args.data_db,
                "data_quality": engine.data_metadata,
                "timeframes": timeframes,
                "base_timeframe": engine.base_tf,
                "step_interval": engine.step_interval,
                "risk_per_trade_pct": engine.risk_per_trade_pct,
                "event_log_path": log_file,
                "event_log_level": args.log_level,
                "start_step": args.start_step,
                "max_steps": args.max_steps,
                "review_trades": engine.review_trades,
                "total_trades": len(trades),
                "trades": trades,
                "decisions": engine.decisions,
                "equity_curve": engine.equity_curve,
            }, f, indent=2, ensure_ascii=False)
        print(f"💾 원본 결과 JSON 저장: {json_path}")
    engine.event_logger.close()


if __name__ == "__main__":
    main()
