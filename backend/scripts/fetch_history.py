"""
MT5 과거 데이터 수집 스크립트
=============================
MT5 터미널에 연결하여 지정한 심볼·기간의 과거 OHLCV 데이터를
CSV 파일로 저장합니다.

사용법 (Wine Python 환경에서):
    python -m backend.scripts.fetch_history --symbol EURUSD --timeframe H1 --days 30
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

# MT5 라이브러리는 Wine 환경에서만 사용 가능
try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

# 타임프레임 매핑 (사람이 읽기 쉬운 문자열 → MT5 상수)
TIMEFRAME_MAP = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 16385,
    "H4": 16388,
    "D1": 16408,
    "W1": 32769,
}

# 기본 저장 경로
DEFAULT_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "backtests",
    "data",
)


def fetch_and_save(symbol: str, timeframe_str: str, days: int, output_dir: str) -> str:
    """
    MT5에서 과거 데이터를 조회하여 CSV로 저장합니다.

    Args:
        symbol: 종목 코드 (예: EURUSD)
        timeframe_str: 타임프레임 문자열 (예: H1)
        days: 조회할 과거 일수
        output_dir: CSV 저장 디렉토리

    Returns:
        저장된 CSV 파일의 절대 경로
    """
    if mt5 is None:
        print("❌ MetaTrader5 패키지를 찾을 수 없습니다. Wine Python 환경에서 실행하세요.")
        sys.exit(1)

    tf = TIMEFRAME_MAP.get(timeframe_str.upper())
    if tf is None:
        print(f"❌ 지원하지 않는 타임프레임: {timeframe_str}")
        print(f"   지원 목록: {list(TIMEFRAME_MAP.keys())}")
        sys.exit(1)

    # MT5 초기화
    from backend.features.trading.mt5_adapter import init_mt5_connection

    if not init_mt5_connection():
        print("❌ MT5 연결 실패.")
        sys.exit(1)

    # 기간 계산
    utc_to = datetime.utcnow()
    utc_from = utc_to - timedelta(days=days)

    print(f"📊 데이터 조회 중: {symbol} {timeframe_str} ({utc_from.date()} ~ {utc_to.date()})")

    rates = mt5.copy_rates_range(symbol, tf, utc_from, utc_to)
    if rates is None or len(rates) == 0:
        error = mt5.last_error() if mt5.last_error() else "Unknown"
        print(f"❌ 데이터 조회 실패. Error: {error}")
        print("   심볼이 Market Watch에 활성화되어 있는지 확인하세요.")
        mt5.shutdown()
        sys.exit(1)

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")

    # 저장
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{symbol}_{timeframe_str}_{days}d_{utc_to.strftime('%Y%m%d')}.csv"
    filepath = os.path.join(output_dir, filename)
    df.to_csv(filepath, index=False)

    print(f"✅ {len(df)}개 캔들 저장 완료: {filepath}")
    mt5.shutdown()
    return filepath


def main():
    parser = argparse.ArgumentParser(description="MT5 과거 데이터 수집 스크립트")
    parser.add_argument("--symbol", type=str, default="EURUSD", help="종목 코드 (기본: EURUSD)")
    parser.add_argument("--timeframe", type=str, default="H1", help="타임프레임 (기본: H1)")
    parser.add_argument("--days", type=int, default=30, help="과거 조회 일수 (기본: 30)")
    parser.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR, help="저장 디렉토리")
    args = parser.parse_args()

    fetch_and_save(args.symbol, args.timeframe, args.days, args.output_dir)


if __name__ == "__main__":
    main()
