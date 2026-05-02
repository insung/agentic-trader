"""Historical candle and import batch persistence."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple

import pandas as pd

from backend.features.trading.persistence.schema import _connect, _now_iso, init_backtest_db


def _normalize_time(value: Any) -> str:
    timestamp = pd.to_datetime(value)
    if getattr(timestamp, "tzinfo", None) is not None:
        timestamp = timestamp.tz_convert(None)
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def _normalize_query_bounds(from_date: str, to_date: str) -> Tuple[str, str]:
    start = pd.to_datetime(from_date)
    end = pd.to_datetime(to_date)
    if len(to_date.strip()) == 10:
        end = end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return _normalize_time(start), _normalize_time(end)


def create_import_batch(
    db_path: str,
    symbol: str,
    timeframes: Iterable[str],
    requested_from: str,
    requested_to: str,
    source: str = "mt5",
    status: str = "running",
) -> int:
    init_backtest_db(db_path)
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO data_import_batches (
                symbol, timeframes, requested_from, requested_to, source, created_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                ",".join(timeframes),
                requested_from,
                requested_to,
                source,
                _now_iso(),
                status,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def update_import_batch_status(
    db_path: str,
    batch_id: int,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    init_backtest_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE data_import_batches
            SET status = ?, error_message = ?
            WHERE id = ?
            """,
            (status, error_message, batch_id),
        )
        conn.commit()


def upsert_candles(
    db_path: str,
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    import_batch_id: Optional[int] = None,
) -> int:
    """Insert or update OHLCV candles keyed by symbol/timeframe/time."""
    init_backtest_db(db_path)
    if df.empty:
        return 0

    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required candle columns: {', '.join(missing)}")

    rows = []
    created_at = _now_iso()
    for item in df.to_dict(orient="records"):
        rows.append(
            (
                symbol,
                timeframe.upper(),
                _normalize_time(item["time"]),
                float(item["open"]),
                float(item["high"]),
                float(item["low"]),
                float(item["close"]),
                int(item.get("tick_volume", 0) or 0),
                int(item.get("spread", 0) or 0),
                int(item.get("real_volume", 0) or 0),
                import_batch_id,
                created_at,
            )
        )

    with _connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO candles (
                symbol, timeframe, time, open, high, low, close,
                tick_volume, spread, real_volume, import_batch_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, timeframe, time) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                tick_volume = excluded.tick_volume,
                spread = excluded.spread,
                real_volume = excluded.real_volume,
                import_batch_id = excluded.import_batch_id
            """,
            rows,
        )
        conn.commit()
    return len(rows)


def load_candles(
    db_path: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
) -> pd.DataFrame:
    """Load candles for a symbol/timeframe/date range as a sorted DataFrame."""
    init_backtest_db(db_path)
    start, end = _normalize_query_bounds(from_date, to_date)
    with _connect(db_path) as conn:
        df = pd.read_sql_query(
            """
            SELECT time, open, high, low, close, tick_volume, spread, real_volume
            FROM candles
            WHERE symbol = ?
              AND timeframe = ?
              AND time >= ?
              AND time <= ?
            ORDER BY time ASC
            """,
            conn,
            params=(symbol, timeframe.upper(), start, end),
            parse_dates=["time"],
        )
    return df


def calculate_candle_quality(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty or "time" not in df.columns:
        return {
            "candle_count": 0,
            "duplicate_count": 0,
            "start_time": None,
            "end_time": None,
            "median_interval": None,
            "max_gap": None,
        }

    times = pd.to_datetime(df["time"]).sort_values()
    diffs = times.diff().dropna()
    return {
        "candle_count": int(len(df)),
        "duplicate_count": int(times.duplicated().sum()),
        "start_time": _normalize_time(times.iloc[0]),
        "end_time": _normalize_time(times.iloc[-1]),
        "median_interval": str(diffs.median()) if not diffs.empty else None,
        "max_gap": str(diffs.max()) if not diffs.empty else None,
    }
