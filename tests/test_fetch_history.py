from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from backend.scripts import fetch_history


def _rates(start: str, count: int, freq: str = "1min", base: float = 1.0):
    times = pd.date_range(start=start, periods=count, freq=freq, tz="UTC")
    rows = []
    for index, ts in enumerate(times):
        rows.append(
            {
                "time": int(ts.timestamp()),
                "open": base + index,
                "high": base + index + 0.5,
                "low": base + index - 0.5,
                "close": base + index + 0.25,
                "tick_volume": 100 + index,
                "spread": 1,
                "real_volume": 0,
            }
        )
    return rows


class FakeMT5:
    def __init__(self, responses, errors=None):
        self.responses = responses
        self.errors = errors or {}
        self.calls = []
        self.shutdown_calls = 0
        self._last_error = None

    def copy_rates_range(self, symbol, tf, start, end):
        self.calls.append((symbol, tf, start, end))
        response = self.responses[len(self.calls) - 1]
        if response is None or response == []:
            self._last_error = self.errors.get(len(self.calls) - 1, (-2, "Terminal: Invalid params"))
            return response
        self._last_error = None
        return response

    def last_error(self):
        return self._last_error

    def shutdown(self):
        self.shutdown_calls += 1


def test_parse_utc_datetime_inclusive_date_only_boundaries():
    assert fetch_history._parse_utc_datetime("2026-04-30") == datetime(
        2026, 4, 30, 0, 0, 0, tzinfo=timezone.utc
    )
    assert fetch_history._parse_utc_datetime("2026-04-30", end_of_day=True) == datetime(
        2026, 4, 30, 23, 59, 59, tzinfo=timezone.utc
    )
    assert fetch_history._parse_utc_datetime("2026-04-30 15:45:00", end_of_day=True) == datetime(
        2026, 4, 30, 15, 45, 0, tzinfo=timezone.utc
    )


def test_resolve_history_bounds_keeps_days_path():
    utc_from, utc_to = fetch_history._resolve_history_bounds(7, None, None)
    delta = utc_to - utc_from
    assert timedelta(days=6, hours=23, minutes=59) < delta < timedelta(days=7, minutes=1)


def test_iter_history_chunks_uses_timeframe_policy():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 1, 20, 23, 59, 59, tzinfo=timezone.utc)

    chunks = list(fetch_history._iter_history_chunks(start, end, "M5"))

    assert len(chunks) == 2
    assert chunks[0][0] == start
    assert chunks[0][1] == datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
    assert chunks[1][0] == datetime(2025, 1, 15, 0, 0, 1, tzinfo=timezone.utc)
    assert chunks[1][1] == end


def test_fetch_and_save_merges_chunked_results(monkeypatch, tmp_path, capsys):
    fake_mt5 = FakeMT5(
        [
            _rates("2025-01-01 00:00:00", 2),
            _rates("2025-01-02 00:00:00", 2),
        ]
    )
    captured = {}

    def fake_upsert_candles(db_path, symbol, timeframe, df, import_batch_id=None):
        captured["payload"] = {
            "db_path": db_path,
            "symbol": symbol,
            "timeframe": timeframe,
            "df": df.copy(),
            "import_batch_id": import_batch_id,
        }
        return len(df)

    monkeypatch.setattr(fetch_history, "mt5", fake_mt5)
    monkeypatch.setattr(fetch_history, "init_mt5_connection", lambda: True)
    monkeypatch.setattr(fetch_history, "upsert_candles", fake_upsert_candles)

    db_path = tmp_path / "market_data.sqlite"
    result = fetch_history.fetch_and_save(
        symbol="BTCUSD",
        timeframe_str="M5",
        from_date="2025-01-01",
        to_date="2025-01-20",
        db_path=str(db_path),
        strict=True,
    )

    output = capsys.readouterr().out
    assert "chunk 1/2" in output
    assert "저장 범위" in output
    assert result == str(db_path)
    assert len(fake_mt5.calls) == 2
    assert fake_mt5.shutdown_calls == 1
    saved_df = captured["payload"]["df"]
    assert list(saved_df["time"]) == sorted(saved_df["time"].tolist())
    assert len(saved_df) == 4


def test_fetch_and_save_strict_mode_fails_on_partial_chunk(monkeypatch, tmp_path, capsys):
    fake_mt5 = FakeMT5(
        [
            _rates("2025-01-01 00:00:00", 2),
            [],
        ]
    )

    upsert_calls = []

    monkeypatch.setattr(fetch_history, "mt5", fake_mt5)
    monkeypatch.setattr(fetch_history, "init_mt5_connection", lambda: True)
    monkeypatch.setattr(
        fetch_history,
        "upsert_candles",
        lambda *args, **kwargs: upsert_calls.append((args, kwargs)) or 0,
    )

    with pytest.raises(SystemExit):
        fetch_history.fetch_and_save(
            symbol="BTCUSD",
            timeframe_str="M5",
            from_date="2025-01-01",
            to_date="2025-01-20",
            db_path=str(tmp_path / "market_data.sqlite"),
            strict=True,
        )

    output = capsys.readouterr().out
    assert "일부 chunk에서 데이터 조회 실패" in output
    assert "history cache" in output
    assert upsert_calls == []
    assert fake_mt5.shutdown_calls == 1


def test_fetch_and_save_allow_partial_saves_successful_chunks(monkeypatch, tmp_path, capsys):
    fake_mt5 = FakeMT5(
        [
            _rates("2025-01-01 00:00:00", 2),
            [],
        ]
    )
    captured = {}

    def fake_upsert_candles(db_path, symbol, timeframe, df, import_batch_id=None):
        captured["payload"] = {
            "db_path": db_path,
            "symbol": symbol,
            "timeframe": timeframe,
            "df": df.copy(),
            "import_batch_id": import_batch_id,
        }
        return len(df)

    monkeypatch.setattr(fetch_history, "mt5", fake_mt5)
    monkeypatch.setattr(fetch_history, "init_mt5_connection", lambda: True)
    monkeypatch.setattr(fetch_history, "upsert_candles", fake_upsert_candles)

    result = fetch_history.fetch_and_save(
        symbol="BTCUSD",
        timeframe_str="M5",
        from_date="2025-01-01",
        to_date="2025-01-20",
        db_path=str(tmp_path / "market_data.sqlite"),
        strict=False,
    )

    output = capsys.readouterr().out
    assert "일부 chunk를 건너뛰고 저장합니다" in output
    assert result.endswith("market_data.sqlite")
    assert len(captured["payload"]["df"]) == 2
    assert fake_mt5.shutdown_calls == 1
