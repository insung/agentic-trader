# 백테스트 실행 가이드

이 문서는 사용자가 직접 확인할 테스트 목록과 `make` 기반 백테스트 절차를 정리합니다. 현재 백테스트 데이터의 기본 저장소는 `backtests/data/market_data.sqlite`입니다.

## 핵심 파라미터

`RISK_PCT=0.005`
: 거래당 계좌 리스크를 `0.5%`로 제한한다는 뜻입니다. 예를 들어 초기 잔고가 `10,000`이면 한 거래에서 SL에 도달했을 때 계획 손실은 약 `50`입니다. 포지션 명목 금액을 계좌의 `0.5%`로 잡는다는 뜻이 아니라, 진입가와 SL 거리 기준으로 손실 한도를 맞추도록 lot size를 계산한다는 뜻입니다.

`STEP=20`
: 백테스트에서 20개 캔들마다 한 번 AI 판단을 실행한다는 뜻입니다. 빠른 검토에는 큰 값을 쓰고, 최종 검증에는 더 촘촘한 값을 사용합니다.

## 먼저 테스트할 목록

1. 기본 코드 테스트

```bash
make test
```

성공 기준:

- 전체 테스트가 통과해야 합니다.
- Linux native Python 환경에서는 MT5/Wine 의존 테스트가 skip될 수 있습니다.

2. SQLite 마이그레이션 확인

```bash
make migrate-legacy-data
```

성공 기준:

- 기존 `backtests/data/*.csv`가 `backtests/data/market_data.sqlite`의 `candles` 테이블로 들어갑니다.
- 기존 `backtests/results/*.json`, `backtests/reports/*.md`가 백테스트 결과/리포트 테이블로 들어갑니다.
- 기존 `trading_logs/review_*.md`가 `trading_logs/trading_logs.sqlite`의 `trade_reviews` 테이블로 들어갑니다.

3. SQLite 데이터 존재 확인

`sqlite3` CLI가 설치되어 있다면:

```bash
sqlite3 backtests/data/market_data.sqlite "SELECT COUNT(*) FROM candles;"
sqlite3 backtests/data/market_data.sqlite "SELECT COUNT(*) FROM backtest_runs;"
sqlite3 trading_logs/trading_logs.sqlite "SELECT COUNT(*) FROM trade_reviews;"
```

`sqlite3` CLI가 없다면 Python으로 확인합니다.

```bash
python3 - <<'PY'
import sqlite3

checks = [
    ("backtests/data/market_data.sqlite", ["candles", "backtest_runs", "backtest_trades", "backtest_decisions", "backtest_reports"]),
    ("trading_logs/trading_logs.sqlite", ["tracked_positions", "reviewed_trade_ids", "trade_reviews"]),
]

for path, tables in checks:
    print(path)
    conn = sqlite3.connect(path)
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count}")
    conn.close()
PY
```

4. 기존 SQLite 데이터로 짧은 백테스트 실행

먼저 이미 DB에 있는 기간을 사용합니다. 현재 저장소에는 BTCUSD의 2025년 1월 데이터가 들어 있습니다.

```bash
make backtest-run \
  SYMBOL=BTCUSD \
  TIMEFRAMES=M15,M30 \
  FROM=2025-01-01 \
  TO=2025-01-31 \
  STEP=20 \
  RISK_PCT=0.005
```

성공 기준:

- `backtests/data/market_data.sqlite`에서 캔들을 읽어 백테스트가 시작됩니다.
- 결과가 `backtests/reports/`, `backtests/results/`, SQLite 결과 테이블에 기록됩니다.
- validator가 차단한 판단은 `backtest_decisions`에 `REJECTED`로 저장됩니다.

5. 새 기간 데이터 수집 후 백테스트 실행

이 단계는 MT5/Wine 연결이 필요합니다.

```bash
make backtest-fetch \
  SYMBOL=BTCUSD \
  TIMEFRAMES=M15,M30 \
  FROM=2025-02-01 \
  TO=2025-02-28
```

수집 후 실행:

```bash
make backtest-run \
  SYMBOL=BTCUSD \
  TIMEFRAMES=M15,M30 \
  FROM=2025-02-01 \
  TO=2025-02-28 \
  STEP=20 \
  RISK_PCT=0.005
```

6. 여러 달을 이어서 백테스트

SQLite는 같은 `symbol/timeframe/time`을 고유 키로 저장하므로 월별 데이터를 이어서 조회할 수 있습니다.

```bash
make backtest-run \
  SYMBOL=BTCUSD \
  TIMEFRAMES=M15,M30 \
  FROM=2025-01-01 \
  TO=2025-03-31 \
  STEP=20 \
  RISK_PCT=0.005
```

성공 기준:

- 1월, 2월, 3월 데이터가 같은 DB에서 기간 조회됩니다.
- 리포트의 데이터 품질 표에서 timeframe별 캔들 수, 중복 수, 최대 gap을 확인할 수 있습니다.

## 결과 확인 위치

백테스트 원천/결과 SQLite:

```text
backtests/data/market_data.sqlite
```

Markdown 리포트와 차트:

```text
backtests/reports/
```

디버그용 JSON 결과:

```text
backtests/results/
```

청산 후 복기:

```text
trading_logs/review_*.md
trading_logs/trading_logs.sqlite
```

## 자주 쓰는 조회 쿼리

상세 스키마와 추가 조회 예시는 [sqlite-storage.md](./sqlite-storage.md)를 기준으로 관리합니다. 여기서는 백테스트 후 바로 확인할 최소 쿼리만 둡니다.

최근 백테스트 실행:

```bash
sqlite3 -header -column backtests/data/market_data.sqlite \
  "SELECT run_id, symbol, timeframes, data_from, data_to, total_trades, net_pnl FROM backtest_runs ORDER BY created_at DESC LIMIT 10;"
```

전략별 손익:

```bash
sqlite3 -header -column backtests/data/market_data.sqlite \
  "SELECT strategy, COUNT(*) AS trades, ROUND(SUM(pnl), 2) AS pnl FROM backtest_trades GROUP BY strategy ORDER BY pnl DESC;"
```

validator 차단 사유:

```bash
sqlite3 -header -column backtests/data/market_data.sqlite \
  "SELECT rejection_reason, COUNT(*) AS count FROM backtest_decisions WHERE status = 'REJECTED' GROUP BY rejection_reason ORDER BY count DESC;"
```

## 참고 문서

- SQLite 저장소 구조: [sqlite-storage.md](./sqlite-storage.md)
- 전체 실행 가이드: [execution-guide.md](./execution-guide.md)
- 테스트 정책: [testing-guide.md](./testing-guide.md)
