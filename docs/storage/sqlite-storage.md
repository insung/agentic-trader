# SQLite 저장소 가이드

Agentic Trader는 SQLite를 로컬 파일 기반 저장소로 사용합니다. SQLite는 PostgreSQL/MySQL처럼 Docker 컨테이너나 서버 프로세스로 띄우는 DB가 아닙니다. 별도 포트, 계정, 데몬, 컨테이너 없이 Python 표준 라이브러리 `sqlite3`가 `.sqlite` 파일을 직접 엽니다.

이 문서는 설치 여부, DB 위치, 기본 조회 명령을 다룹니다. 컬럼 단위 상세 스키마는 [sqlite-schema-reference.md](./sqlite-schema-reference.md)를 참고하십시오.

## 설치가 필요한가

앱 실행에는 별도 설치가 필요 없습니다.

- Python에는 `sqlite3` 모듈이 기본 포함되어 있습니다.
- `make backtest-fetch`, `make backtest-run`, `make migrate-legacy-data`는 이 Python 내장 모듈로 SQLite 파일을 읽고 씁니다.

사람이 터미널에서 직접 DB를 열어보고 싶다면 `sqlite3` CLI를 설치하면 됩니다.

```bash
sudo apt update
sudo apt install sqlite3
```

GUI로 보고 싶다면 `DB Browser for SQLite` 같은 도구를 사용할 수 있습니다.

```bash
sudo apt install sqlitebrowser
```

## DB 파일 위치

백테스트 DB:

```text
backtests/data/market_data.sqlite
```

포함 내용:

- 과거 OHLCV 캔들
- 백테스트 실행 요약
- 백테스트 거래 내역
- 백테스트 판단/HOLD/REJECTED/validator 차단 사유
- 백테스트 Markdown 리포트 아카이브
- 후보 lesson

운영/복기 DB:

```text
trading_logs/trading_logs.sqlite
```

포함 내용:

- 추적 중인 paper/live 포지션
- 복기 완료 trade id
- Risk Reviewer가 생성한 매매 복기 Markdown 아카이브

두 파일은 `backtests/`, `trading_logs/` 아래 생성되는 런타임 산출물입니다. 현재 `.gitignore` 정책상 Git에 커밋하지 않는 로컬 상태입니다.

## 직접 조회하기

테이블 목록 확인:

```bash
sqlite3 backtests/data/market_data.sqlite ".tables"
sqlite3 trading_logs/trading_logs.sqlite ".tables"
```

스키마 확인:

```bash
sqlite3 backtests/data/market_data.sqlite ".schema candles"
sqlite3 backtests/data/market_data.sqlite ".schema backtest_runs"
sqlite3 trading_logs/trading_logs.sqlite ".schema trade_reviews"
```

저장된 row 개수 확인:

```bash
sqlite3 backtests/data/market_data.sqlite "SELECT COUNT(*) FROM candles;"
sqlite3 backtests/data/market_data.sqlite "SELECT COUNT(*) FROM backtest_runs;"
sqlite3 trading_logs/trading_logs.sqlite "SELECT COUNT(*) FROM trade_reviews;"
```

최근 백테스트 실행 보기:

```bash
sqlite3 -header -column backtests/data/market_data.sqlite \
  "SELECT run_id, status, symbol, timeframes, data_from, data_to, total_trades, net_pnl, profit_factor FROM backtest_runs ORDER BY created_at DESC LIMIT 10;"
```

완료된 백테스트만 보기:

```bash
sqlite3 -header -column backtests/data/market_data.sqlite \
  "SELECT run_id, symbol, timeframes, total_trades, net_pnl, profit_factor FROM backtest_runs WHERE status = 'completed' ORDER BY created_at DESC LIMIT 10;"
```

전략별 백테스트 거래 성과 보기:

```bash
sqlite3 -header -column backtests/data/market_data.sqlite \
  "SELECT strategy, COUNT(*) AS trades, ROUND(SUM(pnl), 2) AS pnl FROM backtest_trades GROUP BY strategy ORDER BY pnl DESC;"
```

validator 차단 사유 보기:

```bash
sqlite3 -header -column backtests/data/market_data.sqlite \
  "SELECT rejection_reason, COUNT(*) AS count FROM backtest_decisions WHERE status = 'REJECTED' GROUP BY rejection_reason ORDER BY count DESC;"
```

최근 복기 보기:

```bash
sqlite3 -header -column trading_logs/trading_logs.sqlite \
  "SELECT review_id, reviewed_at, substr(summary, 1, 80) AS summary FROM trade_reviews ORDER BY reviewed_at DESC LIMIT 10;"
```

## sqlite3 CLI 없이 조회하기

`sqlite3` CLI를 설치하지 않아도 Python으로 간단히 볼 수 있습니다.

```bash
python3 - <<'PY'
import sqlite3

for path, tables in [
    ("backtests/data/market_data.sqlite", ["candles", "backtest_runs", "backtest_trades", "backtest_decisions", "backtest_reports"]),
    ("trading_logs/trading_logs.sqlite", ["tracked_positions", "reviewed_trade_ids", "trade_reviews"]),
]:
    print(path)
    conn = sqlite3.connect(path)
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count}")
    conn.close()
PY
```

## 백테스트 DB 스키마

컬럼별 상세 설명과 제약 조건은 [sqlite-schema-reference.md](./sqlite-schema-reference.md)를 기준으로 관리합니다.

`data_import_batches`
: 과거 데이터 수집 요청 단위입니다. symbol, timeframe 목록, 요청 기간, source, status, error_message를 기록합니다.

`candles`
: OHLCV 캔들 테이블입니다. `UNIQUE(symbol, timeframe, time)`으로 중복을 막습니다. 같은 기간을 다시 수집하면 row가 중복 생성되지 않고 기존 row가 갱신됩니다.

`backtest_runs`
: 백테스트 1회 실행 요약입니다. symbol, timeframes, base timeframe, 기간, 초기/최종 잔고, risk, step interval, 거래 수, PnL, profit factor, max drawdown을 저장합니다.

`backtest_trades`
: 백테스트에서 실제로 열린 뒤 청산된 거래 내역입니다. `run_id`로 `backtest_runs`와 연결됩니다.

`backtest_decisions`
: 백테스트 각 판단 시점의 결과입니다. `HOLD`, `SKIP`, `REJECTED`, `OPENED` 같은 상태와 validator 차단 사유를 저장합니다.

`backtest_reports`
: Markdown 백테스트 리포트 본문을 optional artifact/cache로 저장합니다. `report_path`, `chart_path`는 신규 저장 시 NULL이며, 차트는 `candles + backtest_runs + backtest_trades + backtest_decisions`로 재생성합니다.

`lessons`
: 향후 자동 학습/RAG에 사용할 후보 lesson 저장소입니다. symbol, timeframe, strategy, market_regime, confidence, status 같은 scope 정보를 함께 둡니다.

## 운영 로그 DB 스키마

컬럼별 상세 설명과 제약 조건은 [sqlite-schema-reference.md](./sqlite-schema-reference.md)를 기준으로 관리합니다.

`tracked_positions`
: 현재 추적 중인 열린 포지션입니다. 런타임은 사람이 보기 쉬운 `trading_logs/tracked_positions.json`도 계속 지원하지만 SQLite도 함께 동기화합니다.

`reviewed_trade_ids`
: 이미 복기 완료한 trade id 목록입니다. 중복 복기를 막기 위한 상태입니다.

`trade_reviews`
: Risk Reviewer 복기 기록입니다. summary, risk_assessment, lessons_learned, markdown_body를 분리해 저장합니다.

## 주요 명령

과거 데이터 수집:

```bash
make backtest-fetch SYMBOL=BTCUSD TIMEFRAMES=M15,M30 FROM=2025-01-01 TO=2025-02-28
```

SQLite에서 백테스트 실행:

```bash
make backtest-run SYMBOL=BTCUSD TIMEFRAMES=M15,M30 FROM=2025-01-01 TO=2025-02-28
```

기존 CSV/JSON/Markdown 산출물 마이그레이션:

```bash
make migrate-legacy-data
```

## 현재 판단

현재 단계에서는 SQLite가 적합합니다.

- 데이터 접근이 로컬 파일 중심입니다.
- 백테스트 분석은 `symbol`, `timeframe`, `strategy`, `run_id`, `status` 기준 SQL 집계가 중요합니다.
- 동시 쓰기 부하가 낮습니다.
- LLM payload나 indicator snapshot처럼 구조가 유동적인 값은 JSON text 컬럼으로 저장합니다.

NoSQL은 지금 도입하지 않습니다. 나중에 대량 tick 데이터가 필요하면 DuckDB/Parquet를, 긴 문서 유사도 검색이 중요해지면 vector DB를 보조 저장소로 검토합니다.
