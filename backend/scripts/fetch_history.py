"""
MT5 과거 데이터 수집 스크립트
=============================
MT5 터미널에 연결하여 지정한 심볼·기간의 과거 OHLCV 데이터를
SQLite DB에 저장합니다.

사용법 (Wine Python 환경에서):
    python -m backend.scripts.fetch_history --symbol EURUSD --timeframes H1 --days 30
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional, List

import pandas as pd

# MT5 라이브러리는 Wine 환경에서만 사용 가능
try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from backend.features.trading.mt5_adapter import TIMEFRAME_MAP
from backend.features.trading.backtest_store import (
    DEFAULT_BACKTEST_DB_PATH,
    create_import_batch,
    update_import_batch_status,
    upsert_candles,
)

# 기본 저장 경로
DEFAULT_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "backtests",
    "data",
)


def build_history_filename(symbol: str, timeframe: str, start: datetime, end: datetime) -> str:
    """Return the canonical historical-data filename.

    Format: SYMBOL_YYYYMMDD-YYYYMMDD_TIMEFRAME.csv
    """
    date_range = f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"
    return f"{symbol}_{date_range}_{timeframe.upper()}.csv"


def fetch_and_save(
    symbol: str, 
    timeframe_str: str, 
    days: Optional[int] = None, 
    from_date: Optional[str] = None, 
    to_date: Optional[str] = None,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    db_path: str = DEFAULT_BACKTEST_DB_PATH,
    import_batch_id: Optional[int] = None,
) -> str:
    """
    MT5에서 과거 데이터를 조회하여 SQLite로 저장합니다.
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

    # 기간 계산 로직 (UTC timezone 적용)
    if from_date:
        utc_from = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if to_date:
            utc_to = datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            utc_to = datetime.now(timezone.utc)
    else:
        # days 기반 (기본값)
        num_days = days if days is not None else 30
        utc_to = datetime.now(timezone.utc)
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
    
    if len(df) < 10:
        print(f"⚠️ [WARNING] 조회된 데이터가 {len(df)}개뿐입니다.")
        print(f"   브로커 서버에 해당 과거 데이터({timeframe_str})가 다운로드되어 있지 않을 수 있습니다.")
        print(f"   터미널에서 수동으로 스크롤하여 데이터를 로드하거나 다른 날짜/타임프레임을 시도하세요.")

    saved_count = upsert_candles(db_path, symbol, timeframe_str, df, import_batch_id=import_batch_id)

    print(f"✅ {saved_count}개 캔들 SQLite 저장 완료: {db_path} ({symbol} {timeframe_str})")
    mt5.shutdown()
    return db_path


def main():
    parser = argparse.ArgumentParser(description="MT5 과거 데이터 수집 스크립트")
    parser.add_argument("--symbol", type=str, default="EURUSD", help="종목 코드 (기본: EURUSD)")
    parser.add_argument("--timeframes", type=str, default="M5", help="콤마로 구분된 타임프레임 (예: M5,H1)")
    parser.add_argument("--days", type=int, help="과거 조회 일수 (from/to가 없을 때 사용)")
    parser.add_argument("--from", dest="from_date", type=str, help="시작일 (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", type=str, help="종료일 (YYYY-MM-DD)")
    parser.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR, help="저장 디렉토리")
    parser.add_argument("--data-db", type=str, default=DEFAULT_BACKTEST_DB_PATH, help="SQLite market data DB path")
    args = parser.parse_args()

    timeframes = [tf.strip() for tf in args.timeframes.split(",")]
    requested_from = args.from_date or f"last_{args.days or 30}_days"
    requested_to = args.to_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    batch_id = create_import_batch(
        args.data_db,
        symbol=args.symbol,
        timeframes=timeframes,
        requested_from=requested_from,
        requested_to=requested_to,
    )
    try:
        for tf in timeframes:
            fetch_and_save(
                args.symbol,
                tf,
                args.days,
                args.from_date,
                args.to_date,
                args.output_dir,
                db_path=args.data_db,
                import_batch_id=batch_id,
            )
        update_import_batch_status(args.data_db, batch_id, "success")
    except BaseException as exc:
        update_import_batch_status(args.data_db, batch_id, "failed", str(exc))
        raise


if __name__ == "__main__":
    main()
