# Replayable Trading Data

이 문서는 백테스트와 실전/Paper 매매를 같은 방식으로 다시 그리기 위한 데이터 원칙을 정리합니다.

## Source of Truth

차트와 매매 복기의 기준 데이터는 파일 경로가 아니라 SQLite row입니다.

`candles`
: `symbol`, `timeframe`, `time` 기준 OHLCV 원천입니다. 차트는 이 테이블에서 다시 그립니다.

`backtest_runs`
: 백테스트 실행 조건과 상태입니다. 시작 시 `running`, 정상 종료 시 `completed`, Ctrl-C 중단 시 `interrupted`, 예외 종료 시 `failed`입니다.

`backtest_trades`
: 진입/청산 marker입니다. `entry_time`, `exit_time`, `entry_price`, `exit_price`, `sl`, `tp`, `pnl`로 차트 위 거래를 재구성합니다.

`backtest_decisions`
: 판단/audit layer입니다. `HOLD`, `SKIP`, `REJECTED`, `OPENED`와 validator 차단 사유, indicator snapshot, final order를 저장합니다.

`backtest_reports`
: Markdown 본문과 요약 캐시를 보존하는 optional artifact입니다. 신규 저장에서는 `report_path`, `chart_path`를 NULL로 둡니다. 파일 경로가 없어도 `run_id`로 차트를 재생성할 수 있어야 합니다.

## Backtest Flow

- `run_backtest.py`는 시작 직후 `backtest_runs` row를 만듭니다.
- 각 판단은 즉시 `backtest_decisions`에 들어갑니다.
- 청산된 거래는 즉시 `backtest_trades`에 들어갑니다.
- 종료 시 `backtest_runs` 요약과 `status='completed'`만 갱신합니다.
- 강제 종료된 run은 삭제하지 않고 `status='interrupted'`로 남겨 성과 집계에서 제외합니다.

## Runtime Candle Archive

실전/Paper 판단 당시의 M5/M15/M30 candles도 같은 `candles` 테이블에 쌓을 수 있습니다.

```bash
PERSIST_MARKET_CANDLES=1 make run-wine
```

저장 DB를 바꾸려면:

```bash
PERSIST_MARKET_CANDLES=1 MARKET_DATA_DB_PATH=backtests/data/market_data.sqlite make run-wine
```

이 기능은 기본적으로 꺼져 있습니다. 켜면 `fetch_data_node`가 판단에 사용한 OHLCV snapshot을 `symbol + timeframe + time` 고유 키로 upsert합니다.

## Replay Rule

백테스트나 실전 매매 화면은 다음 순서로 재구성합니다.

1. `run_id` 또는 거래 시각 범위로 실행/거래 메타데이터를 찾습니다.
2. `candles`에서 필요한 timeframe과 기간을 조회합니다.
3. `backtest_trades` 또는 운영 execution/tracked position 데이터를 marker로 overlay합니다.
4. `backtest_decisions` 또는 운영 판단 로그를 audit layer로 overlay합니다.
5. Markdown/PNG 파일은 있으면 캐시로 쓰고, 없으면 DB에서 다시 생성합니다.

## Current Limit

백테스트는 run/trade/decision 구조가 갖춰져 있습니다. 실전/Paper는 candle archive를 켤 수 있지만, 백테스트의 `backtest_decisions`와 완전히 같은 운영용 decision/execution 테이블은 아직 없습니다. 후속 단계에서는 운영 판단 로그를 별도 테이블로 구조화해 백테스트와 같은 replay UI를 공유해야 합니다.
