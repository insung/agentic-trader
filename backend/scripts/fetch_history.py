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


def fetch_and_save(
    symbol: str, 
    timeframe_str: str, 
    days: Optional[int] = None, 
    from_date: Optional[str] = None, 
    to_date: Optional[str] = None,
    output_dir: str = DEFAULT_OUTPUT_DIR
) -> str:
    """
    MT5에서 과거 데이터를 조회하여 CSV로 저장합니다.
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

    # 기간 계산 로직
    if from_date:
        utc_from = datetime.strptime(from_date, "%Y-%m-%d")
        if to_date:
            utc_to = datetime.strptime(to_date, "%Y-%m-%d")
        else:
            utc_to = datetime.utcnow()
    else:
        # days 기반 (기본값)
        num_days = days if days is not None else 30
        utc_to = datetime.utcnow()
        utc_from = utc_to - timedelta(days=num_days)

    print(f"📊 데이터 조회 중: {symbol} {timeframe_str} ({utc_from.strftime('%Y-%m-%d')} ~ {utc_to.strftime('%Y-%m-%d')})")

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
    date_str = f"{utc_from.strftime('%Y%m%d')}_{utc_to.strftime('%Y%m%d')}"
    filename = f"{symbol}_{timeframe_str}_{date_str}.csv"
    filepath = os.path.join(output_dir, filename)
    df.to_csv(filepath, index=False)

    print(f"✅ {len(df)}개 캔들 저장 완료: {filepath}")
    mt5.shutdown()
    return filepath


def main():
    parser = argparse.ArgumentParser(description="MT5 과거 데이터 수집 스크립트")
    parser.add_argument("--symbol", type=str, default="EURUSD", help="종목 코드 (기본: EURUSD)")
    parser.add_argument("--timeframe", type=str, default="H1", help="타임프레임 (기본: H1)")
    parser.add_argument("--days", type=int, help="과거 조회 일수 (from/to가 없을 때 사용)")
    parser.add_argument("--from", dest="from_date", type=str, help="시작일 (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", type=str, help="종료일 (YYYY-MM-DD)")
    parser.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR, help="저장 디렉토리")
    args = parser.parse_args()

    fetch_and_save(
        args.symbol, 
        args.timeframe, 
        args.days, 
        args.from_date, 
        args.to_date, 
        args.output_dir
    )


if __name__ == "__main__":
    main()
