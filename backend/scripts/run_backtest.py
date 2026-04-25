"""
Agentic Backtest Runner
========================
저장된 과거 데이터(CSV)를 캔들 단위로 순회하면서
LangGraph 에이전트 파이프라인(app.invoke)을 반복 호출하여
AI의 실제 매매 판단을 과거 데이터 위에서 시뮬레이션합니다.

사용법:
    python -m backend.scripts.run_backtest --data backtests/data/EURUSD_H1_30d_20260425.csv
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import patch, MagicMock

import pandas as pd

# 프로젝트 루트를 기준으로 경로 설정
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 기본 설정
DEFAULT_INITIAL_BALANCE = 10_000.0
LOOKBACK_CANDLES = 100  # 각 시점에서 에이전트에게 보여줄 과거 캔들 수
STEP_INTERVAL = 5       # 몇 캔들마다 파이프라인을 호출할지 (비용 절감)


class BacktestEngine:
    """
    과거 데이터를 LangGraph 파이프라인에 밀어 넣는 시뮬레이터.
    MT5 API 호출을 모킹(Mocking)하여 과거 데이터를 반환하도록 합니다.
    """

    def __init__(
        self,
        data_path: str,
        symbol: str = "EURUSD",
        timeframe: str = "M5",
        initial_balance: float = DEFAULT_INITIAL_BALANCE,
        step_interval: int = STEP_INTERVAL,
    ):
        self.data_path = data_path
        self.symbol = symbol
        self.timeframe = timeframe
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.step_interval = step_interval

        # 전체 과거 데이터 로드
        self.df = pd.read_csv(data_path, parse_dates=["time"])
        print(f"📂 데이터 로드 완료: {len(self.df)}개 캔들 ({self.df['time'].iloc[0]} ~ {self.df['time'].iloc[-1]})")

        # 결과 기록
        self.trades: List[Dict[str, Any]] = []
        self.equity_curve: List[Dict[str, Any]] = []

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

    def _evaluate_trade(self, trade: Dict[str, Any], future_candles: pd.DataFrame) -> Dict[str, Any]:
        """
        매매 결정 이후의 캔들들을 순회하여 SL/TP 도달 여부를 판정합니다.
        최대 step_interval * 5 개의 캔들까지 관찰합니다.
        """
        action = trade["action"].upper()
        entry_price = trade["entry_price"]
        sl = trade["sl"]
        tp = trade["tp"]
        lot_size = trade["lot_size"]

        if entry_price <= 0 or sl <= 0 or tp <= 0:
            return {**trade, "result": "INVALID", "pnl": 0.0, "exit_price": entry_price, "exit_reason": "Invalid prices"}

        max_look = min(len(future_candles), self.step_interval * 5)

        for i in range(max_look):
            candle = future_candles.iloc[i]
            high = candle["high"]
            low = candle["low"]

            if action == "BUY":
                # SL 먼저 체크 (보수적)
                if low <= sl:
                    pnl = (sl - entry_price) * lot_size
                    self.balance += pnl
                    return {**trade, "result": "SL_HIT", "pnl": round(pnl, 2), "exit_price": sl, "exit_reason": "Stop Loss"}
                if high >= tp:
                    pnl = (tp - entry_price) * lot_size
                    self.balance += pnl
                    return {**trade, "result": "TP_HIT", "pnl": round(pnl, 2), "exit_price": tp, "exit_reason": "Take Profit"}
            elif action == "SELL":
                if high >= sl:
                    pnl = (entry_price - sl) * lot_size
                    self.balance += pnl
                    return {**trade, "result": "SL_HIT", "pnl": round(pnl, 2), "exit_price": sl, "exit_reason": "Stop Loss"}
                if low <= tp:
                    pnl = (entry_price - tp) * lot_size
                    self.balance += pnl
                    return {**trade, "result": "TP_HIT", "pnl": round(pnl, 2), "exit_price": tp, "exit_reason": "Take Profit"}

        # SL/TP 도달하지 못한 경우 마지막 캔들의 종가로 청산
        last_close = future_candles.iloc[max_look - 1]["close"] if max_look > 0 else entry_price
        if action == "BUY":
            pnl = (last_close - entry_price) * lot_size
        else:
            pnl = (entry_price - last_close) * lot_size
        self.balance += pnl
        return {**trade, "result": "TIMEOUT", "pnl": round(pnl, 2), "exit_price": last_close, "exit_reason": "Max candles reached"}

    def run(self) -> List[Dict[str, Any]]:
        """
        백테스트를 실행합니다.
        과거 데이터를 step_interval 간격으로 슬라이싱하여
        각 시점에서 LangGraph 파이프라인을 호출합니다.
        """
        total_candles = len(self.df)
        if total_candles < LOOKBACK_CANDLES + 1:
            print(f"❌ 데이터 부족: {total_candles}개 캔들 (최소 {LOOKBACK_CANDLES + 1}개 필요)")
            return []

        # LangGraph 그래프 컴파일 (import를 여기서 수행하여 모킹 범위 밖에서 초기화)
        from backend.workflows.graph import get_compiled_graph
        graph = get_compiled_graph()

        start_idx = LOOKBACK_CANDLES
        step_positions = range(start_idx, total_candles - self.step_interval, self.step_interval)
        total_steps = len(list(step_positions))

        print(f"\n🚀 백테스트 시작: {self.symbol}")
        print(f"   총 {total_steps}개 시점에서 파이프라인 호출 예정")
        print(f"   초기 잔고: ${self.initial_balance:,.2f}")
        print(f"   Step Interval: {self.step_interval} 캔들")
        print("=" * 60)

        for step_num, i in enumerate(range(start_idx, total_candles - self.step_interval, self.step_interval), 1):
            current_time = self.df.iloc[i]["time"]
            window = self.df.iloc[i - LOOKBACK_CANDLES : i]
            current_candle = self.df.iloc[i]

            print(f"\n--- Step {step_num}/{total_steps} | {current_time} | Balance: ${self.balance:,.2f} ---")

            # 모킹할 반환값 준비
            mock_ohlcv = self._build_mock_ohlcv(window)
            mock_price = self._build_mock_price(current_candle)
            mock_account = self._build_mock_account()

            # MT5 함수들을 모킹하여 과거 데이터를 반환하도록 패치
            with patch("backend.workflows.nodes.fetch_ohlcv", return_value=mock_ohlcv), \
                 patch("backend.workflows.nodes.get_current_price", return_value=mock_price), \
                 patch("backend.workflows.nodes.get_account_summary", return_value=mock_account), \
                 patch("backend.workflows.nodes.is_mt5_available", return_value=True), \
                 patch("backend.workflows.nodes.is_market_open", return_value=True), \
                 patch("backend.workflows.nodes.execute_mock_order", side_effect=lambda *a, **kw: {
                     "retcode": 10009, "order": step_num, "price": mock_price["ask"],
                     "volume": a[2] if len(a) > 2 else 0.01
                 }):

                try:
                    initial_state = {"symbol": self.symbol, "timeframe": self.timeframe}
                    final_state = {}

                    for s in graph.stream(initial_state):
                        node_name = list(s.keys())[0]
                        final_state.update(list(s.values())[0])

                    # 결과 분석
                    if final_state.get("error_flag"):
                        print(f"   ⚠️ 에러 발생: {final_state.get('error_message', 'Unknown')}")
                        continue

                    final_order = final_state.get("final_order")
                    if not final_order:
                        print("   📊 매매 신호 없음 (Tech Analyst가 시장 비적합 판단)")
                        self.equity_curve.append({"time": str(current_time), "balance": self.balance, "action": "SKIP"})
                        continue

                    action = final_order.get("action", "HOLD")
                    if action.upper() in ("HOLD", "WAIT"):
                        print(f"   🛑 Chief Trader 판단: {action}")
                        self.equity_curve.append({"time": str(current_time), "balance": self.balance, "action": action})
                        continue

                    # 유효한 매매 결정
                    sl = final_order.get("sl_price", final_order.get("sl", 0.0))
                    tp = final_order.get("tp_price", final_order.get("tp", 0.0))
                    entry_price = mock_price["ask"] if action.upper() == "BUY" else mock_price["bid"]

                    # 1% 룰로 랏 계산
                    from backend.features.trading.guardrails import enforce_one_percent_rule
                    lot_size = enforce_one_percent_rule(self.balance, entry_price, sl)

                    if lot_size <= 0:
                        print(f"   ⛔ 가드레일: 랏 사이즈 0 (SL 거리 이상)")
                        continue

                    trade_record = {
                        "step": step_num,
                        "time": str(current_time),
                        "action": action.upper(),
                        "entry_price": entry_price,
                        "sl": sl,
                        "tp": tp,
                        "lot_size": lot_size,
                        "reasoning": final_order.get("reasoning", final_order.get("final_reasoning", "")),
                    }

                    # SL/TP 도달 여부 판정
                    future_candles = self.df.iloc[i + 1 : i + 1 + self.step_interval * 5]
                    if len(future_candles) > 0:
                        evaluated = self._evaluate_trade(trade_record, future_candles)
                    else:
                        evaluated = {**trade_record, "result": "NO_DATA", "pnl": 0.0, "exit_price": entry_price, "exit_reason": "No future data"}

                    self.trades.append(evaluated)
                    self.equity_curve.append({"time": str(current_time), "balance": self.balance, "action": action})

                    result_emoji = "✅" if evaluated["pnl"] >= 0 else "❌"
                    print(f"   {result_emoji} {action} @ {entry_price:.5f} → {evaluated['exit_reason']} @ {evaluated['exit_price']:.5f} | PnL: ${evaluated['pnl']:.2f}")

                except Exception as e:
                    print(f"   💥 파이프라인 에러: {e}")
                    import traceback
                    traceback.print_exc()
                    continue

        print("\n" + "=" * 60)
        print(f"🏁 백테스트 완료!")
        print(f"   최종 잔고: ${self.balance:,.2f} (변동: ${self.balance - self.initial_balance:+,.2f})")
        print(f"   총 매매 횟수: {len(self.trades)}")

        return self.trades


def main():
    parser = argparse.ArgumentParser(description="Agentic Backtest Runner")
    parser.add_argument("--data", type=str, required=True, help="과거 데이터 CSV 파일 경로")
    parser.add_argument("--symbol", type=str, default="EURUSD", help="종목 코드 (기본: EURUSD)")
    parser.add_argument("--timeframe", type=str, default="M5", help="타임프레임 (기본: M5)")
    parser.add_argument("--balance", type=float, default=DEFAULT_INITIAL_BALANCE, help="초기 잔고 (기본: 10000)")
    parser.add_argument("--step", type=int, default=STEP_INTERVAL, help="파이프라인 호출 간격 (캔들 수, 기본: 5)")
    parser.add_argument("--report", action="store_true", help="백테스트 완료 후 리포트 자동 생성")
    args = parser.parse_args()

    if not os.path.exists(args.data):
        print(f"❌ 데이터 파일을 찾을 수 없습니다: {args.data}")
        sys.exit(1)

    engine = BacktestEngine(
        data_path=args.data,
        symbol=args.symbol,
        timeframe=args.timeframe,
        initial_balance=args.balance,
        step_interval=args.step,
    )

    trades = engine.run()

    if args.report and trades:
        from backend.features.trading.reporting import generate_backtest_report
        report_path = generate_backtest_report(
            trades=trades,
            equity_curve=engine.equity_curve,
            df=engine.df,
            symbol=args.symbol,
            initial_balance=args.balance,
            final_balance=engine.balance,
        )
        print(f"\n📄 리포트 생성 완료: {report_path}")
    elif args.report and not trades:
        print("\n⚠️ 매매 기록이 없어 리포트를 생성하지 않습니다.")

    # JSON으로도 원본 데이터 저장
    if trades:
        results_dir = os.path.join(PROJECT_ROOT, "backtests", "results")
        os.makedirs(results_dir, exist_ok=True)
        json_path = os.path.join(results_dir, f"backtest_{args.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "symbol": args.symbol,
                "initial_balance": args.balance,
                "final_balance": engine.balance,
                "total_trades": len(trades),
                "trades": trades,
                "equity_curve": engine.equity_curve,
            }, f, indent=2, ensure_ascii=False)
        print(f"💾 원본 결과 JSON 저장: {json_path}")


if __name__ == "__main__":
    main()
