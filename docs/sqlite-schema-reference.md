# SQLite 테이블 스키마 레퍼런스

이 문서는 Agentic Trader가 생성하는 SQLite 테이블을 컬럼 단위로 설명합니다. 운영 방법과 조회 명령은 [sqlite-storage.md](./sqlite-storage.md), 백테스트 실행 절차는 [backtesting-guide.md](./backtesting-guide.md)를 참고하십시오.

## DB 파일

백테스트 DB:

```text
backtests/data/market_data.sqlite
```

운영/복기 DB:

```text
trading_logs/trading_logs.sqlite
```

두 DB 모두 Python 표준 `sqlite3` 모듈로 직접 읽고 씁니다. 코드에서 연결할 때 `PRAGMA foreign_keys = ON`을 켜므로, 애플리케이션 경로에서는 외래 키 검증이 활성화됩니다.

## 공통 설계 원칙

- 시간 컬럼은 문자열 `TEXT`로 저장합니다. 대부분 ISO 형식 또는 `YYYY-MM-DD HH:MM:SS` 형식입니다.
- 복잡한 LLM 판단 컨텍스트, 주문 원문, indicator snapshot은 JSON 문자열 컬럼에 저장합니다.
- 백테스트 원천 캔들은 `symbol + timeframe + time` 조합으로 중복을 방지합니다.
- 백테스트 실행 단위는 `run_id`, 운영 복기 단위는 `review_id`, 열린 포지션 단위는 `trade_id`를 자연 키로 사용합니다.
- Markdown 리포트와 복기 본문은 사람이 읽을 수 있도록 파일로도 남기고, 검색과 보존을 위해 SQLite에도 저장합니다.

## 관계 요약

```text
data_import_batches 1 ── N candles

backtest_runs 1 ── N backtest_trades
backtest_runs 1 ── N backtest_decisions
backtest_runs 1 ── N lessons
backtest_runs 1 ── N backtest_reports

tracked_positions      독립 운영 상태
reviewed_trade_ids     중복 복기 방지 상태
trade_reviews          Risk Reviewer 복기 아카이브
```

## 백테스트 DB

### `data_import_batches`

과거 OHLCV 데이터 수집 요청 1회를 기록합니다. `make backtest-fetch` 또는 legacy CSV 마이그레이션이 이 테이블에 batch를 만들고, 수집 결과에 따라 `status`를 갱신합니다.

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `id` | `INTEGER` | PK, AUTOINCREMENT | 내부 batch ID입니다. |
| `symbol` | `TEXT` | NOT NULL | 수집 대상 심볼입니다. 예: `BTCUSD`, `EURUSD`. |
| `timeframes` | `TEXT` | NOT NULL | 요청한 timeframe 목록입니다. 콤마 문자열로 저장합니다. 예: `M15,M30`. |
| `requested_from` | `TEXT` | NOT NULL | 사용자가 요청한 시작일입니다. |
| `requested_to` | `TEXT` | NOT NULL | 사용자가 요청한 종료일입니다. |
| `source` | `TEXT` | NOT NULL, default `mt5` | 데이터 출처입니다. 예: `mt5`, `legacy_csv`. |
| `created_at` | `TEXT` | NOT NULL | batch row 생성 시각입니다. |
| `status` | `TEXT` | NOT NULL | 수집 상태입니다. 현재 코드에서는 `running`, `success`, `failed`를 사용합니다. |
| `error_message` | `TEXT` | nullable | 수집 실패 시 예외 메시지입니다. |

주요 사용:

- 어떤 기간의 데이터를 언제 가져왔는지 추적합니다.
- CSV 마이그레이션 결과와 MT5 수집 결과를 구분합니다.
- `candles.import_batch_id`로 캔들이 어떤 수집 작업에서 들어왔는지 연결합니다.

### `candles`

백테스트에 사용하는 OHLCV 캔들 원천 테이블입니다. 같은 심볼, 같은 timeframe, 같은 시간의 캔들은 하나만 존재합니다.

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `id` | `INTEGER` | PK, AUTOINCREMENT | 내부 candle row ID입니다. |
| `symbol` | `TEXT` | NOT NULL | 심볼입니다. |
| `timeframe` | `TEXT` | NOT NULL | timeframe입니다. 대문자로 저장합니다. 예: `M15`, `M30`, `H1`. |
| `time` | `TEXT` | NOT NULL | 캔들 시작 시각입니다. 조회 시 정렬 기준입니다. |
| `open` | `REAL` | NOT NULL | 시가입니다. |
| `high` | `REAL` | NOT NULL | 고가입니다. |
| `low` | `REAL` | NOT NULL | 저가입니다. |
| `close` | `REAL` | NOT NULL | 종가입니다. |
| `tick_volume` | `INTEGER` | NOT NULL, default `0` | MT5 tick volume입니다. |
| `spread` | `INTEGER` | NOT NULL, default `0` | MT5 spread 값입니다. |
| `real_volume` | `INTEGER` | NOT NULL, default `0` | MT5 real volume입니다. 없으면 0입니다. |
| `import_batch_id` | `INTEGER` | FK nullable | `data_import_batches.id` 참조입니다. |
| `created_at` | `TEXT` | NOT NULL | 최초 저장 시각입니다. |

제약과 인덱스:

- `UNIQUE(symbol, timeframe, time)`: 같은 캔들의 중복 저장을 막습니다.
- `idx_candles_lookup(symbol, timeframe, time)`: 기간 조회 성능을 위한 인덱스입니다.
- `import_batch_id`는 `data_import_batches(id)`를 참조합니다.

갱신 동작:

- `upsert_candles`는 중복 키가 있으면 OHLCV, volume, spread, `import_batch_id`를 갱신합니다.
- `created_at`은 현재 upsert 갱신 시 덮어쓰지 않습니다. 최초 row 생성 시각의 의미로 유지됩니다.

### `backtest_runs`

백테스트 실행 1회의 요약 테이블입니다. 리포트 목록, 거래 목록, 의사결정 목록을 묶는 기준이 `run_id`입니다.

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `id` | `INTEGER` | PK, AUTOINCREMENT | 내부 run row ID입니다. |
| `run_id` | `TEXT` | NOT NULL, UNIQUE | 백테스트 실행 고유 ID입니다. 파일명이나 리포트와 연결할 때 사용합니다. |
| `symbol` | `TEXT` | NOT NULL | 백테스트 대상 심볼입니다. |
| `timeframes` | `TEXT` | NOT NULL | 사용한 timeframe 목록입니다. 콤마 문자열입니다. |
| `base_timeframe` | `TEXT` | NOT NULL | 차트와 step 기준이 되는 주 timeframe입니다. 보통 첫 번째 timeframe입니다. |
| `data_from` | `TEXT` | NOT NULL | 실제 백테스트 데이터 시작 시각입니다. |
| `data_to` | `TEXT` | NOT NULL | 실제 백테스트 데이터 종료 시각입니다. |
| `initial_balance` | `REAL` | NOT NULL | 시작 잔고입니다. |
| `final_balance` | `REAL` | nullable | 종료 잔고입니다. |
| `risk_per_trade_pct` | `REAL` | NOT NULL | 거래당 계좌 리스크 비율입니다. `0.005`는 0.5%입니다. |
| `step_interval` | `INTEGER` | NOT NULL | 몇 개 캔들마다 AI 판단을 호출했는지 나타냅니다. |
| `total_trades` | `INTEGER` | default `0` | 청산까지 완료된 거래 수입니다. |
| `net_pnl` | `REAL` | nullable | 전체 손익입니다. 일반적으로 `final_balance - initial_balance`입니다. |
| `profit_factor` | `REAL` | nullable | 총 이익 / 총 손실 절대값입니다. 손실이 없으면 NULL일 수 있습니다. |
| `max_drawdown_pct` | `REAL` | nullable | 백테스트 기간 최대 낙폭 비율입니다. |
| `created_at` | `TEXT` | NOT NULL | 백테스트 실행 기록 생성 시각입니다. |

갱신 동작:

- 같은 `run_id`를 다시 저장하면 요약 지표만 갱신합니다.
- 관련 `backtest_trades`, `backtest_decisions`, `lessons`는 해당 `run_id` 기준으로 삭제 후 다시 삽입합니다.

### `backtest_trades`

백테스트 중 실제로 열린 뒤 청산된 거래 기록입니다. HOLD, validator reject 같은 비거래 판단은 이 테이블이 아니라 `backtest_decisions`에 들어갑니다.

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `id` | `INTEGER` | PK, AUTOINCREMENT | 내부 trade row ID입니다. |
| `run_id` | `TEXT` | NOT NULL, FK | `backtest_runs.run_id` 참조입니다. |
| `trade_id` | `TEXT` | NOT NULL | 백테스트 내부 거래 ID입니다. 현재 테이블 단독 unique는 아닙니다. |
| `symbol` | `TEXT` | NOT NULL | 거래 심볼입니다. |
| `strategy` | `TEXT` | nullable | Chief Trader가 선택한 전략명입니다. |
| `market_regime` | `TEXT` | nullable | Tech Analyst 또는 Strategist가 판단한 시장 상태입니다. |
| `action` | `TEXT` | NOT NULL | `BUY` 또는 `SELL` 같은 진입 방향입니다. |
| `entry_time` | `TEXT` | NOT NULL | 진입 시각입니다. |
| `exit_time` | `TEXT` | nullable | 청산 시각입니다. |
| `entry_price` | `REAL` | NOT NULL | 진입 가격입니다. |
| `exit_price` | `REAL` | nullable | 청산 가격입니다. |
| `sl` | `REAL` | NOT NULL | 손절 가격입니다. |
| `tp` | `REAL` | NOT NULL | 익절 가격입니다. |
| `lot_size` | `REAL` | NOT NULL | 계산된 lot size입니다. |
| `result` | `TEXT` | nullable | 거래 결과입니다. 예: `WIN`, `LOSS`, `OPEN`, `CLOSED`. |
| `exit_reason` | `TEXT` | nullable | 청산 이유입니다. 예: `TP`, `SL`, `BACKTEST_END`. |
| `pnl` | `REAL` | nullable | 해당 거래의 손익입니다. |
| `reasoning` | `TEXT` | nullable | 진입 당시 LLM reasoning 또는 요약입니다. |

주요 사용:

- 전략별 손익 집계
- `exit_reason`별 손실 원인 분석
- `risk_per_trade_pct` 변경 전후 결과 비교

### `backtest_decisions`

백테스트 각 판단 시점의 결과를 저장합니다. 실제 거래가 열리지 않은 경우도 포함하기 때문에, validator가 왜 막았는지 분석할 때 핵심 테이블입니다.

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `id` | `INTEGER` | PK, AUTOINCREMENT | 내부 decision row ID입니다. |
| `run_id` | `TEXT` | NOT NULL, FK | `backtest_runs.run_id` 참조입니다. |
| `decision_time` | `TEXT` | NOT NULL | AI 판단 또는 gate 판단이 발생한 캔들 시각입니다. |
| `action` | `TEXT` | NOT NULL | 판단된 액션입니다. 예: `BUY`, `SELL`, `HOLD`. |
| `strategy` | `TEXT` | nullable | 판단에 사용된 전략명입니다. |
| `market_regime` | `TEXT` | nullable | 판단 당시 시장 상태입니다. |
| `status` | `TEXT` | NOT NULL | 판단 처리 결과입니다. 예: `HOLD`, `SKIP`, `REJECTED`, `OPENED`. |
| `rejection_reason` | `TEXT` | nullable | validator나 guardrail이 차단한 이유입니다. |
| `indicator_snapshot_json` | `TEXT` | nullable | 판단 당시 지표 스냅샷 JSON입니다. |
| `final_order_json` | `TEXT` | nullable | 최종 주문 intent 또는 gate 통과 전후 주문 JSON입니다. |

주요 사용:

- 어떤 전략이 자주 차단되는지 집계
- `REJECTED`가 손실 회피에 기여했는지 검토
- 미래 RAG/lesson 후보를 만들기 위한 근거 데이터 확보

### `lessons`

백테스트나 거래 복기에서 추출한 후보 lesson 저장소입니다. 현재는 향후 자동 학습/RAG를 위한 구조를 먼저 잡아둔 테이블입니다.

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `id` | `INTEGER` | PK, AUTOINCREMENT | 내부 lesson row ID입니다. |
| `run_id` | `TEXT` | FK nullable | lesson이 나온 `backtest_runs.run_id`입니다. 운영 복기 기반이면 NULL일 수 있습니다. |
| `trade_id` | `TEXT` | nullable | 특정 거래에서 나온 lesson이면 거래 ID를 저장합니다. |
| `symbol` | `TEXT` | NOT NULL | 적용 대상 심볼입니다. |
| `timeframe` | `TEXT` | NOT NULL | 적용 대상 timeframe입니다. |
| `strategy` | `TEXT` | nullable | 적용 대상 전략입니다. |
| `market_regime` | `TEXT` | nullable | 적용 대상 시장 상태입니다. |
| `lesson_text` | `TEXT` | NOT NULL | 재사용 가능한 교훈 본문입니다. |
| `evidence_type` | `TEXT` | NOT NULL | 근거 유형입니다. 예: `backtest`, `trade_review`. |
| `confidence` | `REAL` | NOT NULL, default `0.0` | lesson 신뢰도입니다. 현재는 사람이 검토하기 위한 후보 점수입니다. |
| `status` | `TEXT` | NOT NULL, default `candidate` | lesson 상태입니다. 예: `candidate`, `approved`, `deprecated`. |
| `created_at` | `TEXT` | NOT NULL | lesson 생성 시각입니다. |
| `deprecated_at` | `TEXT` | nullable | 더 이상 유효하지 않게 된 시각입니다. |

상충 lesson 처리 방향:

- 서로 다른 장세에서만 맞는 lesson은 `symbol`, `timeframe`, `strategy`, `market_regime` 범위를 좁혀 저장합니다.
- 과거에는 맞았지만 최근에는 틀리는 lesson은 삭제하지 않고 `status='deprecated'`, `deprecated_at`으로 비활성화합니다.
- 같은 주제의 lesson이 충돌하면 `confidence`, 최근 out-of-sample 성과, 적용 범위를 함께 보고 승격 여부를 결정합니다.

### `backtest_reports`

Markdown 백테스트 리포트 원문을 보존합니다. 차트 이미지는 DB에 바이너리로 넣지 않고 파일 경로만 저장합니다.

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `id` | `INTEGER` | PK, AUTOINCREMENT | 내부 report row ID입니다. |
| `report_id` | `TEXT` | NOT NULL, UNIQUE | 리포트 고유 ID입니다. 보통 파일명 기반입니다. |
| `run_id` | `TEXT` | FK nullable | 연결된 백테스트 실행 ID입니다. legacy 리포트는 NULL일 수 있습니다. |
| `symbol` | `TEXT` | NOT NULL | 리포트 대상 심볼입니다. |
| `report_path` | `TEXT` | nullable | Markdown 파일 경로입니다. |
| `chart_path` | `TEXT` | nullable | 차트 PNG 파일 경로입니다. |
| `report_created_at` | `TEXT` | nullable | 리포트 본문 또는 파일에서 추출한 생성 시각입니다. |
| `markdown_body` | `TEXT` | NOT NULL | 리포트 Markdown 전체 본문입니다. |
| `summary_json` | `TEXT` | nullable | 리포트 요약 메타데이터 JSON입니다. |
| `created_at` | `TEXT` | NOT NULL | SQLite에 저장한 시각입니다. |

## 운영/복기 DB

### `tracked_positions`

현재 봇이 추적 중인 열린 포지션 목록입니다. 기존 `trading_logs/tracked_positions.json`과 병행 저장되며, 재시작 복구와 조회를 쉽게 하기 위한 mirror 역할을 합니다.

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `id` | `INTEGER` | PK, AUTOINCREMENT | 내부 position row ID입니다. |
| `trade_id` | `TEXT` | NOT NULL, UNIQUE | 시스템 내부 거래 ID입니다. 중복 추적을 막는 자연 키입니다. |
| `ticket` | `TEXT` | nullable | MT5 ticket 또는 broker 주문/포지션 식별자입니다. |
| `mode` | `TEXT` | NOT NULL | `paper` 또는 `live` 같은 실행 모드입니다. |
| `symbol` | `TEXT` | NOT NULL | 거래 심볼입니다. |
| `action` | `TEXT` | NOT NULL | 진입 방향입니다. 예: `BUY`, `SELL`. |
| `entry_time` | `TEXT` | NOT NULL | 진입 시각입니다. |
| `entry_price` | `REAL` | NOT NULL | 진입 가격입니다. |
| `sl` | `REAL` | NOT NULL | 손절 가격입니다. |
| `tp` | `REAL` | NOT NULL | 익절 가격입니다. |
| `lot_size` | `REAL` | NOT NULL | 주문 lot size입니다. |
| `order_result_json` | `TEXT` | nullable | 주문 실행 결과 원문 JSON입니다. |
| `decision_context_json` | `TEXT` | nullable | 진입 당시 AI 판단 컨텍스트 JSON입니다. |
| `created_at` | `TEXT` | NOT NULL | 포지션 추적 시작 시각입니다. |
| `updated_at` | `TEXT` | NOT NULL | SQLite mirror 갱신 시각입니다. |

제약과 인덱스:

- `trade_id`는 unique입니다.
- `idx_tracked_positions_symbol_mode(symbol, mode)` 인덱스로 심볼/모드별 조회를 빠르게 합니다.

갱신 동작:

- 현재 구현은 전체 추적 목록을 `DELETE` 후 다시 삽입하는 replace 방식입니다.
- 운영 원자성 강화와 JSON 완전 제거는 후속 과제입니다.

### `reviewed_trade_ids`

이미 Risk Reviewer 복기를 완료한 거래 ID 목록입니다. reconcile 루프가 같은 청산 거래를 반복 복기하지 않도록 막습니다.

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `trade_id` | `TEXT` | PK | 복기 완료한 거래 ID입니다. |
| `reviewed_at` | `TEXT` | NOT NULL | 복기 완료로 표시한 시각입니다. |
| `source` | `TEXT` | NOT NULL, default `reconcile` | 이 상태가 기록된 출처입니다. 예: `reconcile`, `legacy_json`. |

갱신 동작:

- 같은 `trade_id`를 다시 기록하면 `reviewed_at`, `source`를 갱신합니다.
- legacy JSON 마이그레이션 시 기존 reviewed list도 이 테이블에 들어갑니다.

### `trade_reviews`

Risk Reviewer가 생성한 청산 후 복기 기록입니다. Markdown 파일 원문과 함께 요약, 리스크 평가, lesson 구간을 분리 저장합니다.

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `id` | `INTEGER` | PK, AUTOINCREMENT | 내부 review row ID입니다. |
| `review_id` | `TEXT` | NOT NULL, UNIQUE | 복기 고유 ID입니다. 보통 파일명 또는 trade 기반 ID입니다. |
| `trade_id` | `TEXT` | nullable | 복기 대상 거래 ID입니다. legacy Markdown에서는 없을 수 있습니다. |
| `symbol` | `TEXT` | nullable | 거래 심볼입니다. |
| `reviewed_at` | `TEXT` | nullable | 복기 생성 또는 청산 검토 시각입니다. |
| `source_path` | `TEXT` | nullable | 원본 Markdown 파일 경로입니다. |
| `summary` | `TEXT` | nullable | 복기 문서의 Summary 섹션입니다. |
| `risk_assessment` | `TEXT` | nullable | Risk Assessment 섹션입니다. |
| `lessons_learned` | `TEXT` | nullable | Lessons Learned 섹션입니다. |
| `markdown_body` | `TEXT` | NOT NULL | 복기 Markdown 전체 본문입니다. |
| `raw_payload_json` | `TEXT` | nullable | Risk Reviewer 원본 payload JSON입니다. |
| `source` | `TEXT` | NOT NULL, default `risk_reviewer` | 기록 출처입니다. 예: `risk_reviewer`, `legacy_markdown`. |
| `created_at` | `TEXT` | NOT NULL | SQLite 저장 시각입니다. |

갱신 동작:

- 같은 `review_id`를 다시 저장하면 본문, 요약, payload, source를 갱신합니다.
- `created_at`은 현재 upsert 갱신 시 덮어쓰지 않습니다.

## JSON 컬럼 해석

| 컬럼 | 저장 내용 | 용도 |
| --- | --- | --- |
| `backtest_decisions.indicator_snapshot_json` | 계산된 OHLCV/indicator snapshot | LLM이 실제 수치를 제대로 반영했는지 검토 |
| `backtest_decisions.final_order_json` | Chief Trader 또는 guardrail 통과 전후 주문 intent | 주문 검증 실패 원인 추적 |
| `backtest_reports.summary_json` | 리포트 메타데이터 요약 | 리포트 목록 화면이나 집계용 |
| `tracked_positions.order_result_json` | MT5/Paper 주문 실행 결과 | 재시작 후 주문 상태 추적 |
| `tracked_positions.decision_context_json` | 진입 당시 AI 판단 컨텍스트 | 청산 후 Risk Reviewer 입력 재구성 |
| `trade_reviews.raw_payload_json` | Risk Reviewer structured output 원문 | Markdown 파싱 실패 시 원본 보존 |

## 자주 쓰는 확인 쿼리

테이블별 row 수:

```bash
sqlite3 backtests/data/market_data.sqlite \
  "SELECT 'candles', COUNT(*) FROM candles UNION ALL SELECT 'backtest_runs', COUNT(*) FROM backtest_runs UNION ALL SELECT 'backtest_trades', COUNT(*) FROM backtest_trades UNION ALL SELECT 'backtest_decisions', COUNT(*) FROM backtest_decisions UNION ALL SELECT 'backtest_reports', COUNT(*) FROM backtest_reports;"
```

기간별 캔들 범위:

```bash
sqlite3 -header -column backtests/data/market_data.sqlite \
  "SELECT symbol, timeframe, COUNT(*) AS candles, MIN(time) AS first_time, MAX(time) AS last_time FROM candles GROUP BY symbol, timeframe ORDER BY symbol, timeframe;"
```

최근 백테스트 실행과 거래 수:

```bash
sqlite3 -header -column backtests/data/market_data.sqlite \
  "SELECT r.run_id, r.symbol, r.timeframes, r.data_from, r.data_to, r.total_trades, ROUND(r.net_pnl, 2) AS net_pnl FROM backtest_runs r ORDER BY r.created_at DESC LIMIT 10;"
```

validator 차단 사유:

```bash
sqlite3 -header -column backtests/data/market_data.sqlite \
  "SELECT rejection_reason, COUNT(*) AS count FROM backtest_decisions WHERE status = 'REJECTED' GROUP BY rejection_reason ORDER BY count DESC;"
```

최근 운영 복기:

```bash
sqlite3 -header -column trading_logs/trading_logs.sqlite \
  "SELECT review_id, trade_id, symbol, reviewed_at, substr(summary, 1, 100) AS summary FROM trade_reviews ORDER BY created_at DESC LIMIT 10;"
```

## 변경 시 주의사항

- 컬럼을 추가하면 `backend/features/trading/*_store.py`의 `CREATE TABLE`과 insert/upsert 코드를 함께 바꿔야 합니다.
- 기존 로컬 DB가 이미 생성된 뒤에는 `CREATE TABLE IF NOT EXISTS`만으로 새 컬럼이 추가되지 않습니다. 마이그레이션용 `ALTER TABLE` 경로가 별도로 필요합니다.
- `candles`의 unique key를 바꾸면 기존 데이터 중복 정책이 달라지므로, 백테스트 기간 조회와 마이그레이션 테스트를 함께 갱신해야 합니다.
- `run_id`, `report_id`, `review_id`, `trade_id`는 재실행/재마이그레이션의 idempotency를 지키는 키입니다. 생성 규칙을 바꿀 때는 기존 산출물 재적재 결과를 반드시 확인해야 합니다.
