"""
백테스트 리포팅 모듈
===================
백테스트 결과를 통계 테이블, 차트 이미지, 마크다운 문서로 생성합니다.
"""
import os
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd

# matplotlib은 GUI 없는 서버에서도 동작하도록 Agg 백엔드 사용
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# 기본 저장 경로
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_REPORT_DIR = os.path.join(PROJECT_ROOT, "docs", "trading_logs", "backtest_results")


def _calculate_statistics(trades: List[Dict[str, Any]], initial_balance: float, final_balance: float) -> Dict[str, Any]:
    """매매 기록으로부터 핵심 통계를 계산합니다."""
    if not trades:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "net_pnl": 0.0,
            "net_pnl_pct": 0.0,
            "avg_pnl": 0.0,
            "max_win": 0.0,
            "max_loss": 0.0,
            "max_drawdown_pct": 0.0,
            "profit_factor": 0.0,
        }

    pnls = [t.get("pnl", 0.0) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    total_wins = sum(wins) if wins else 0.0
    total_losses = abs(sum(losses)) if losses else 0.0
    profit_factor = (total_wins / total_losses) if total_losses > 0 else float("inf")

    # MDD (Maximum Drawdown) 계산
    cumulative = initial_balance
    peak = initial_balance
    max_dd = 0.0
    for pnl in pnls:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        dd = (peak - cumulative) / peak * 100
        if dd > max_dd:
            max_dd = dd

    net_pnl = final_balance - initial_balance

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
        "net_pnl": round(net_pnl, 2),
        "net_pnl_pct": round(net_pnl / initial_balance * 100, 2),
        "avg_pnl": round(sum(pnls) / len(pnls), 2),
        "max_win": round(max(pnls), 2) if pnls else 0.0,
        "max_loss": round(min(pnls), 2) if pnls else 0.0,
        "max_drawdown_pct": round(max_dd, 2),
        "profit_factor": round(profit_factor, 2),
    }


def _generate_chart(
    df: pd.DataFrame,
    trades: List[Dict[str, Any]],
    equity_curve: List[Dict[str, Any]],
    symbol: str,
    output_dir: str,
) -> str:
    """
    가격 차트 위에 매매 타점을 표시하고, 자산 곡선(Equity Curve)을 하단에 배치한
    2-panel 차트를 생성합니다.
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), gridspec_kw={"height_ratios": [3, 1]}, sharex=False)
    fig.suptitle(f"Backtest Result: {symbol}", fontsize=16, fontweight="bold")

    # --- Panel 1: 가격 차트 + 매매 타점 ---
    ax1.plot(df["time"], df["close"], color="#4A90D9", linewidth=0.8, alpha=0.9, label="Close Price")
    ax1.fill_between(df["time"], df["low"], df["high"], alpha=0.1, color="#4A90D9")

    # 매매 타점 마커
    buy_times, buy_prices = [], []
    sell_times, sell_prices = [], []

    for trade in trades:
        try:
            trade_time = pd.to_datetime(trade["time"])
        except (ValueError, KeyError):
            continue
        entry = trade.get("entry_price", 0)
        action = trade.get("action", "").upper()
        if action == "BUY":
            buy_times.append(trade_time)
            buy_prices.append(entry)
        elif action == "SELL":
            sell_times.append(trade_time)
            sell_prices.append(entry)

    if buy_times:
        ax1.scatter(buy_times, buy_prices, marker="^", color="#00C853", s=100, zorder=5, label=f"BUY ({len(buy_times)})", edgecolors="black", linewidths=0.5)
    if sell_times:
        ax1.scatter(sell_times, sell_prices, marker="v", color="#FF1744", s=100, zorder=5, label=f"SELL ({len(sell_times)})", edgecolors="black", linewidths=0.5)

    ax1.set_ylabel("Price", fontsize=12)
    ax1.legend(loc="upper left", fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))

    # --- Panel 2: Equity Curve ---
    if equity_curve:
        eq_times = [pd.to_datetime(e["time"]) for e in equity_curve]
        eq_balances = [e["balance"] for e in equity_curve]
        ax2.plot(eq_times, eq_balances, color="#FF6F00", linewidth=1.5, label="Equity")
        ax2.fill_between(eq_times, eq_balances, eq_balances[0], alpha=0.15, color="#FF6F00")
        ax2.axhline(y=eq_balances[0], color="gray", linestyle="--", alpha=0.5, label="Initial Balance")
        ax2.set_ylabel("Balance ($)", fontsize=12)
        ax2.legend(loc="upper left", fontsize=10)
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))

    plt.tight_layout()

    os.makedirs(output_dir, exist_ok=True)
    chart_filename = f"chart_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    chart_path = os.path.join(output_dir, chart_filename)
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(f"📊 차트 저장: {chart_path}")
    return chart_path


def generate_backtest_report(
    trades: List[Dict[str, Any]],
    equity_curve: List[Dict[str, Any]],
    df: pd.DataFrame,
    symbol: str,
    initial_balance: float,
    final_balance: float,
    output_dir: str = DEFAULT_REPORT_DIR,
) -> str:
    """
    백테스트 결과를 마크다운 리포트 + 차트 이미지로 생성합니다.

    Returns:
        생성된 마크다운 파일의 절대 경로.
    """
    stats = _calculate_statistics(trades, initial_balance, final_balance)

    # 차트 생성
    chart_path = _generate_chart(df, trades, equity_curve, symbol, output_dir)
    chart_filename = os.path.basename(chart_path)

    # 마크다운 리포트 생성
    os.makedirs(output_dir, exist_ok=True)
    report_filename = f"backtest_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    report_path = os.path.join(output_dir, report_filename)

    # 데이터 기간
    data_start = df["time"].iloc[0].strftime("%Y-%m-%d %H:%M") if not df.empty else "N/A"
    data_end = df["time"].iloc[-1].strftime("%Y-%m-%d %H:%M") if not df.empty else "N/A"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# 📊 Backtest Report: {symbol}\n\n")
        f.write(f"**생성일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")
        f.write(f"**데이터 기간**: {data_start} ~ {data_end}  \n")
        f.write(f"**총 캔들 수**: {len(df)}  \n\n")

        # 핵심 통계 테이블
        f.write("## 📈 성과 요약 (Performance Summary)\n\n")
        f.write("| 지표 | 값 |\n")
        f.write("|------|----|\n")
        f.write(f"| 초기 잔고 | ${initial_balance:,.2f} |\n")
        f.write(f"| 최종 잔고 | ${final_balance:,.2f} |\n")
        f.write(f"| 순 손익 (Net PnL) | ${stats['net_pnl']:+,.2f} ({stats['net_pnl_pct']:+.2f}%) |\n")
        f.write(f"| 총 매매 횟수 | {stats['total_trades']} |\n")
        f.write(f"| 승리 / 패배 | {stats['wins']} / {stats['losses']} |\n")
        f.write(f"| 승률 (Win Rate) | {stats['win_rate']}% |\n")
        f.write(f"| 평균 손익 | ${stats['avg_pnl']:+,.2f} |\n")
        f.write(f"| 최대 수익 (Best Trade) | ${stats['max_win']:+,.2f} |\n")
        f.write(f"| 최대 손실 (Worst Trade) | ${stats['max_loss']:+,.2f} |\n")
        f.write(f"| 최대 낙폭 (MDD) | {stats['max_drawdown_pct']}% |\n")
        f.write(f"| 수익 팩터 (Profit Factor) | {stats['profit_factor']} |\n\n")

        # 차트 이미지
        f.write("## 📉 차트 (Price Chart + Equity Curve)\n\n")
        f.write(f"![Backtest Chart](./{chart_filename})\n\n")

        # 개별 매매 내역 테이블
        f.write("## 📋 매매 내역 (Trade Log)\n\n")
        if trades:
            f.write("| # | 시간 | 방향 | 진입가 | SL | TP | 랏 | 결과 | 손익 |\n")
            f.write("|---|------|------|--------|----|----|-----|------|------|\n")
            for i, t in enumerate(trades, 1):
                action_emoji = "🟢" if t.get("action", "").upper() == "BUY" else "🔴"
                result_emoji = "✅" if t.get("pnl", 0) >= 0 else "❌"
                f.write(
                    f"| {i} | {t.get('time', 'N/A')[:16]} | {action_emoji} {t.get('action', 'N/A')} "
                    f"| {t.get('entry_price', 0):.5f} | {t.get('sl', 0):.5f} | {t.get('tp', 0):.5f} "
                    f"| {t.get('lot_size', 0):.2f} | {result_emoji} {t.get('result', 'N/A')} "
                    f"| ${t.get('pnl', 0):+.2f} |\n"
                )
        else:
            f.write("매매 기록 없음.\n")

        # AI 추론 로그 (최대 5개만 표시)
        f.write("\n## 🤖 AI 추론 기록 (샘플)\n\n")
        sample_trades = trades[:5] if len(trades) > 5 else trades
        for i, t in enumerate(sample_trades, 1):
            reasoning = t.get("reasoning", "N/A")
            f.write(f"### Trade #{i} ({t.get('time', 'N/A')[:16]})\n")
            f.write(f"> {reasoning}\n\n")

    print(f"📄 마크다운 리포트 저장: {report_path}")
    return report_path
