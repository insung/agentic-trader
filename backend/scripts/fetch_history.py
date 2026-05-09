"""MT5 과거 데이터 수집 스크립트.

MT5 터미널에 연결하여 지정한 심볼/기간의 과거 OHLCV 데이터를
SQLite DB에 저장합니다.

사용법 (Wine Python 환경에서):
    python -m backend.scripts.fetch_history --symbol EURUSD --timeframes H1 --days 30
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Tuple

import pandas as pd

# MT5 라이브러리는 Wine 환경에서만 사용 가능
try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from backend.features.trading.adapters.mt5_connection import init_mt5_connection
from backend.features.trading.adapters.mt5_market_data import TIMEFRAME_MAP
from backend.features.trading.persistence.backtest_store import (
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

TIMEFRAME_CHUNK_POLICIES = {
    "M1": timedelta(days=7),
    "M5": timedelta(days=14),
    "M15": timedelta(days=30),
    "M30": timedelta(days=90),
    "H1": timedelta(days=90),
    "H4": timedelta(days=180),
    "D1": timedelta(days=180),
    "W1": timedelta(days=365),
}


def build_history_filename(symbol: str, timeframe: str, start: datetime, end: datetime) -> str:
    """Return the canonical historical-data filename.

    Format: SYMBOL_YYYYMMDD-YYYYMMDD_TIMEFRAME.csv
    """
    date_range = f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"
    return f"{symbol}_{date_range}_{timeframe.upper()}.csv"


def _parse_utc_datetime(value: str, *, end_of_day: bool = False) -> datetime:
    """Parse an input string as a UTC datetime.

    Date-only values are treated as UTC calendar dates. For end bounds,
    date-only values become inclusive end-of-day timestamps.
    """
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(timezone.utc)
    else:
        timestamp = timestamp.tz_convert(timezone.utc)

    if end_of_day and isinstance(value, str) and len(value.strip()) == 10:
        timestamp = timestamp.normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return timestamp.to_pydatetime()


def _resolve_history_bounds(
    days: Optional[int],
    from_date: Optional[str],
    to_date: Optional[str],
) -> Tuple[datetime, datetime]:
    if from_date:
        utc_from = _parse_utc_datetime(from_date)
        if to_date:
            utc_to = _parse_utc_datetime(to_date, end_of_day=True)
        else:
            utc_to = datetime.now(timezone.utc)
        return utc_from, utc_to

    num_days = days if days is not None else 30
    utc_to = datetime.now(timezone.utc)
    utc_from = utc_to - timedelta(days=num_days)
    return utc_from, utc_to


def _get_timeframe_chunk_delta(timeframe_str: str) -> timedelta:
    return TIMEFRAME_CHUNK_POLICIES.get(timeframe_str.upper(), timedelta(days=30))


def _iter_history_chunks(
    start: datetime,
    end: datetime,
    timeframe_str: str,
) -> Iterable[Tuple[datetime, datetime]]:
    chunk_delta = _get_timeframe_chunk_delta(timeframe_str)
    current_start = start
    while current_start <= end:
        chunk_end = min(current_start + chunk_delta, end)
        yield current_start, chunk_end
        if chunk_end >= end:
            break
        current_start = chunk_end + timedelta(seconds=1)


def _format_mt5_error(error: object) -> str:
    if isinstance(error, tuple) and len(error) >= 2:
        return f"{error[0]} / {error[1]}"
    return str(error)


def _fetch_chunk(
    symbol: str,
    tf: int,
    chunk_start: datetime,
    chunk_end: datetime,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    rates = mt5.copy_rates_range(symbol, tf, chunk_start, chunk_end)
    if rates is None or len(rates) == 0:
        error = mt5.last_error() if mt5.last_error() else "Unknown"
        return None, _format_mt5_error(error)

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df, None


def _merge_chunk_frames(frames: List[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    if "time" in combined.columns:
        combined = combined.drop_duplicates(subset=["time"], keep="last").sort_values("time")
    return combined.reset_index(drop=True)


def fetch_and_save(
    symbol: str,
    timeframe_str: str,
    days: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    db_path: str = DEFAULT_BACKTEST_DB_PATH,
    import_batch_id: Optional[int] = None,
    strict: bool = True,
) -> str:
    """Fetch historical data from MT5 and persist it to SQLite."""
    if mt5 is None:
        print("❌ MetaTrader5 패키지를 찾을 수 없습니다. Wine Python 환경에서 실행하세요.")
        sys.exit(1)

    tf = TIMEFRAME_MAP.get(timeframe_str.upper())
    if tf is None:
        print(f"❌ 지원하지 않는 타임프레임: {timeframe_str}")
        print(f"   지원 목록: {list(TIMEFRAME_MAP.keys())}")
        sys.exit(1)

    if not init_mt5_connection():
        print("❌ MT5 연결 실패.")
        sys.exit(1)

    utc_from, utc_to = _resolve_history_bounds(days, from_date, to_date)
    print(
        f"📊 데이터 조회 중: {symbol} {timeframe_str} "
        f"({utc_from.strftime('%Y-%m-%d')} ~ {utc_to.strftime('%Y-%m-%d')})"
    )

    chunk_frames: List[pd.DataFrame] = []
    chunk_failures: List[Tuple[int, str, str]] = []
    try:
        chunks = list(_iter_history_chunks(utc_from, utc_to, timeframe_str))
        for index, (chunk_start, chunk_end) in enumerate(chunks, start=1):
            print(
                f"   ↳ chunk {index}/{len(chunks)}: "
                f"{chunk_start.strftime('%Y-%m-%d %H:%M:%S')} ~ {chunk_end.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            chunk_df, error = _fetch_chunk(symbol, tf, chunk_start, chunk_end)
            if chunk_df is None:
                print(f"      ❌ chunk {index} 실패: {error}")
                chunk_failures.append((index, chunk_start.isoformat(), chunk_end.isoformat()))
                if strict:
                    break
                continue

            print(f"      ✅ chunk {index} 수집 완료: {len(chunk_df)}개")
            chunk_frames.append(chunk_df)

        df = _merge_chunk_frames(chunk_frames)

        if strict and chunk_failures:
            failed_chunks = ", ".join(f"#{idx}({start} ~ {end})" for idx, start, end in chunk_failures)
            print(f"❌ 일부 chunk에서 데이터 조회 실패: {failed_chunks}")
            print(
                "   심볼 활성화 문제뿐 아니라, 요청 기간이 너무 길거나 "
                "MT5 history cache가 부족할 수 있습니다."
            )
            sys.exit(1)

        if df.empty:
            print("❌ 데이터 조회 실패. 모든 chunk가 비어 있습니다.")
            print(
                "   심볼 활성화 문제뿐 아니라, 요청 기간이 너무 길거나 "
                "MT5 history cache가 부족할 수 있습니다."
            )
            sys.exit(1)

        if len(df) < 10:
            print(f"⚠️ [WARNING] 조회된 데이터가 {len(df)}개뿐입니다.")
            print(f"   브로커 서버에 해당 과거 데이터({timeframe_str})가 다운로드되어 있지 않을 수 있습니다.")
            print("   터미널에서 수동으로 스크롤하여 데이터를 로드하거나 다른 날짜/타임프레임을 시도하세요.")

        if chunk_failures and not strict:
            failed_chunks = ", ".join(f"#{idx}" for idx, _, _ in chunk_failures)
            print(f"⚠️ [WARNING] 일부 chunk를 건너뛰고 저장합니다: {failed_chunks}")

        saved_count = upsert_candles(db_path, symbol, timeframe_str, df, import_batch_id=import_batch_id)
        min_time = df["time"].min()
        max_time = df["time"].max()
        print(f"✅ {saved_count}개 캔들 SQLite 저장 완료: {db_path} ({symbol} {timeframe_str})")
        print(f"   저장 범위: {min_time} ~ {max_time}")
        return db_path
    finally:
        mt5.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="MT5 과거 데이터 수집 스크립트")
    parser.add_argument("--symbol", type=str, default="EURUSD", help="종목 코드 (기본: EURUSD)")
    parser.add_argument("--timeframes", type=str, default="M5", help="콤마로 구분된 타임프레임 (예: M5,H1)")
    parser.add_argument("--timeframe", type=str, help="단일 타임프레임 별칭 (예: M5)")
    parser.add_argument("--days", type=int, help="과거 조회 일수 (from/to가 없을 때 사용)")
    parser.add_argument("--from", dest="from_date", type=str, help="시작일 (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", type=str, help="종료일 (YYYY-MM-DD)")
    parser.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR, help="저장 디렉토리")
    parser.add_argument("--data-db", type=str, default=DEFAULT_BACKTEST_DB_PATH, help="SQLite market data DB path")
    parser.add_argument("--allow-partial", action="store_true", help="일부 chunk 실패 시에도 성공한 chunk를 저장")
    args = parser.parse_args()

    timeframe_arg = args.timeframes or args.timeframe or "M5"
    timeframes = [tf.strip() for tf in timeframe_arg.split(",") if tf.strip()]
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
                strict=not args.allow_partial,
            )
        update_import_batch_status(args.data_db, batch_id, "success")
    except BaseException as exc:
        update_import_batch_status(args.data_db, batch_id, "failed", str(exc))
        raise


if __name__ == "__main__":
    main()
