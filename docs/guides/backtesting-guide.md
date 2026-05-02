# 백테스트 실행 가이드

이 문서는 사용자가 직접 확인할 테스트 목록과 `make` 기반 백테스트 절차를 정리합니다. 현재 백테스트 데이터의 기본 저장소는 `backtests/data/market_data.sqlite`입니다.

## 핵심 파라미터

`RISK_PCT=0.005`
: 거래당 계좌 리스크를 `0.5%`로 제한한다는 뜻입니다. 예를 들어 초기 잔고가 `10,000`이면 한 거래에서 SL에 도달했을 때 계획 손실은 약 `50`입니다. 포지션 명목 금액을 계좌의 `0.5%`로 잡는다는 뜻이 아니라, 진입가와 SL 거리 기준으로 손실 한도를 맞추도록 lot size를 계산한다는 뜻입니다.

`STEP=20`
: 백테스트에서 20개 캔들마다 한 번 AI 판단을 실행한다는 뜻입니다. 빠른 검토에는 큰 값을 쓰고, 최종 검증에는 더 촘촘한 값을 사용합니다.

`START_STEP=10`
: 처음 10개 판단 지점을 건너뛰고 그 다음 판단 지점부터 실행합니다. `MAX_STEPS=10` 결과가 계속 HOLD라면 `START_STEP=10`, `START_STEP=20`처럼 구간을 밀어서 확인합니다.

`MAX_STEPS=10`
: 디버그용으로 파이프라인 호출 횟수를 제한합니다. 긴 기간 데이터를 모두 돌리기 전에 느린 구간, validator 차단 사유, LLM 응답 흐름을 빠르게 확인할 때 사용합니다.

`NO_REVIEW=1`
: 청산 후 Risk Reviewer LLM 복기를 생략합니다. 전략 진입/청산 성능만 빠르게 확인할 때 유용합니다. 최종 리포트용 실행에서는 복기를 켜는 편이 좋습니다.

`LOG_FILE=...`
: 백테스트 구조화 JSONL 로그 경로를 직접 지정합니다. 지정하지 않으면 `backtests/logs/backtest_<run_id>.jsonl`에 기록됩니다.

`LOG_LEVEL=INFO`
: JSONL 로그에 남길 최소 레벨을 지정합니다. 기본값은 `TRACE`라 모든 이벤트를 남깁니다. `INFO`는 run 시작/종료와 거래 open/close처럼 큰 이벤트만 남기고, `DEBUG`는 decision/review 이벤트까지, `TRACE`는 step/node timing까지 남깁니다.

## vectorbt Quant Research

`make quant-run`은 LangGraph/LLM을 호출하지 않고, SQLite에 저장된 캔들로 빠른 전략 리서치를 수행합니다. 현재 1차 대상은 Bollinger Reversion baseline이며, 결과는 `quant_runs`, `quant_results` 테이블에 저장합니다.

처음 한 번 옵션 의존성을 설치합니다.

```bash
make install-quant
```

이미 수집된 캔들로 실행합니다. 새 캔들이 필요하면 먼저 `make backtest-fetch`로 MT5에서 SQLite에 저장합니다.

```bash
make quant-run \
  SYMBOL=BTCUSD \
  TIMEFRAME=M15 \
  FROM=2025-01-01 \
  TO=2025-01-31 \
  QUANT_STRATEGY=bollinger \
  INIT_CASH=10000
```

파라미터 스윕은 콤마 문자열로 조정합니다.

```bash
make quant-run \
  SYMBOL=BTCUSD \
  TIMEFRAME=M15 \
  FROM=2025-01-01 \
  TO=2025-03-31 \
  BB_WINDOWS=14,20,30 \
  BB_STDS=1.8,2.0,2.2 \
  RSI_LOWERS=25,30,35 \
  RSI_UPPERS=65,70,75 \
  RRS=1.3,1.5,2.0 \
  STOP_PCTS=0.01
```

이 결과는 전략 후보를 빠르게 거르는 연구용 baseline입니다. 좋은 결과가 나와도 자동으로 실전 전략으로 승격하지 않으며, 승격 시에는 전략 문서, config 등록, deterministic validator, 테스트를 별도 작업으로 추가해야 합니다.

저장된 quant 결과는 `quant-summary`로 비교합니다.

```bash
make quant-summary \
  SYMBOL=BTCUSD \
  FROM=2025-01-01 \
  TO=2025-03-31
```

월별 비교가 필요하면 `SUMMARY_MONTHLY=1`을 켭니다.

```bash
make quant-summary \
  SYMBOL=BTCUSD \
  FROM=2025-01-01 \
  TO=2025-03-31 \
  SUMMARY_MONTHLY=1
```

특정 전략만 보고 싶다면 `SUMMARY_STRATEGY`를 사용합니다.

```bash
make quant-summary \
  SYMBOL=BTCUSD \
  FROM=2025-01-01 \
  TO=2025-03-31 \
  SUMMARY_STRATEGY=trend_pullback_reclaim
```

특정 `run_id` 하나만 보고 싶다면 `SUMMARY_RUN_ID`를 사용합니다.

```bash
make quant-summary \
  SUMMARY_RUN_ID=QR_BTCUSD_20260430_143755
```

No-Trade Audit은 `backtest_decisions`와 `backtest_trades`를 run_id 기준으로 읽어, HOLD/SKIP/REJECTED의 원인을 요약합니다.

```bash
make no-trade-audit RUN_ID=BTCUSD_20260429_221853
```

멀티 타임프레임 Bollinger + RSI 실험은 `bollinger_mtf`를 사용합니다. 기본 구조는 `TIMEFRAME`에서 진입 타이밍을 보고, `FILTER_TIMEFRAME`에서 강한 추세 역행 진입을 막는 단일 전략입니다.

```bash
make quant-run \
  SYMBOL=BTCUSD \
  TIMEFRAME=M15 \
  FILTER_TIMEFRAME=M30 \
  FROM=2025-01-01 \
  TO=2025-03-31 \
  QUANT_STRATEGY=bollinger_mtf \
  FEES=0.0002 \
  SLIPPAGE=0.0002
```

`bollinger_mtf`의 현재 규칙:

- M15 Long 후보: 하단 밴드 근처, RSI 과매도, 양봉 또는 하단 밴드 재진입
- M15 Short 후보: 상단 밴드 근처, RSI 과매수, 음봉 또는 상단 밴드 재진입
- M30 Long 필터: M30 `EMA20 < EMA50`이고 RSI가 `FILTER_RSI_LOWS` 아래면 Long 금지
- M30 Short 필터: M30 `EMA20 > EMA50`이고 RSI가 `FILTER_RSI_HIGHS` 위면 Short 금지
- 청산/리스크: 중심선 청산, `STOP_PCTS`, `RRS` 기반 vectorbt SL/TP 실험

추세추종 눌림목 baseline은 `trend_pullback`을 사용합니다. 평균회귀 Bollinger 계열과 비교하기 위한 전략이며, `FILTER_TIMEFRAME`이 필수입니다.

```bash
make quant-run \
  SYMBOL=BTCUSD \
  TIMEFRAME=M15 \
  FILTER_TIMEFRAME=M30 \
  FROM=2025-01-01 \
  TO=2025-03-31 \
  QUANT_STRATEGY=trend_pullback \
  FEES=0.0002 \
  SLIPPAGE=0.0002
```

`trend_pullback`의 현재 규칙:

- M15 Long 후보: `EMA_FAST > EMA_SLOW`, EMA fast 근처 눌림, 양봉 재개, RSI가 `TREND_RSI_LOWERS` 이상
- M15 Short 후보: `EMA_FAST < EMA_SLOW`, EMA fast 근처 반등, 음봉 재개, RSI가 `TREND_RSI_UPPERS` 이하
- M30 필터: Long은 M30 `EMA20 > EMA50`, Short는 M30 `EMA20 < EMA50`일 때만 허용
- SL/TP: `ATR14 * ATR_STOP_MULTIPLIERS`를 진입가 대비 비율로 변환해 `sl_stop`으로 쓰고, `RRS`로 `tp_stop`을 계산
- 주요 스윕 변수: `PULLBACK_ATRS`, `ATR_STOP_MULTIPLIERS`, `RRS`, `TREND_RSI_LOWERS`, `TREND_RSI_UPPERS`

`trend_pullback`이 거래 과다와 빠른 EMA20 exit로 실패한 경우, 더 엄격한 개선판 `trend_pullback_reclaim`을 사용합니다. 기존 실패 baseline은 비교를 위해 보존합니다.

```bash
make quant-run \
  SYMBOL=BTCUSD \
  TIMEFRAME=M15 \
  FILTER_TIMEFRAME=M30 \
  FROM=2025-01-01 \
  TO=2025-03-31 \
  QUANT_STRATEGY=trend_pullback_reclaim \
  FEES=0.0002 \
  SLIPPAGE=0.0002 \
  ATR_STOP_MULTIPLIERS=2.0,3.0 \
  RRS=2.0,3.0
```

`trend_pullback_reclaim`의 현재 규칙:

- Long: `EMA_FAST > EMA_SLOW`, 최근 `RECLAIM_LOOKBACKS` 안에 EMA fast 아래 종가가 있었고, 현재 EMA fast 위로 재진입
- Short: `EMA_FAST < EMA_SLOW`, 최근 `RECLAIM_LOOKBACKS` 안에 EMA fast 위 종가가 있었고, 현재 EMA fast 아래로 재진입
- MTF 필터 강화: Long은 higher timeframe `close > EMA20 > EMA50`, Short는 `close < EMA20 < EMA50`
- RSI 회복: Long은 최근 RSI 과매도권 이후 `TREND_RSI_LOWERS` 이상, Short는 최근 RSI 과매수권 이후 `TREND_RSI_UPPERS` 이하
- Cooldown: 신호 발생 후 `COOLDOWN_BARS` 동안 같은 방향 재진입을 막음
- Exit 완화: EMA20이 아니라 EMA50 이탈 또는 EMA fast/slow 추세 반전 때 조건부 청산
- 기본 실험 변수: `RECLAIM_LOOKBACKS=3,5,8`, `COOLDOWN_BARS=8,12,20`, `ATR_STOP_MULTIPLIERS=2.0,3.0`, `RRS=2.0,3.0`

돌파 추종 baseline은 `breakout`을 사용합니다. 최근 고가/저가를 넘는 추세 지속을 노리며, 필요하면 higher timeframe 필터를 함께 씁니다.

```bash
make quant-run \
  SYMBOL=BTCUSD \
  TIMEFRAME=M15 \
  FILTER_TIMEFRAME=M30 \
  FROM=2025-01-01 \
  TO=2025-03-31 \
  QUANT_STRATEGY=breakout \
  FEES=0.0002 \
  SLIPPAGE=0.0002 \
  BREAKOUT_LOOKBACKS=20,30,50 \
  BREAKOUT_ATR_BUFFERS=0.0,0.25,0.5
```

`breakout`의 현재 규칙:

- M15 Long 후보: 최근 `BREAKOUT_LOOKBACKS` 구간 고가를 상향 돌파하고, RSI가 `BREAKOUT_RSI_LOWERS` 이상이며, 양봉 재개
- M15 Short 후보: 최근 `BREAKOUT_LOOKBACKS` 구간 저가를 하향 이탈하고, RSI가 `BREAKOUT_RSI_UPPERS` 이하이며, 음봉 재개
- MTF 필터(선택): higher timeframe에서 `close > EMA20 > EMA50`이면 Long만 허용, `close < EMA20 < EMA50`이면 Short만 허용
- 진입 버퍼: `BREAKOUT_ATR_BUFFERS`를 ATR 비율로 더해 노이즈성 돌파를 줄임
- 청산/리스크: `EMA50` 이탈 또는 추세 반전, `ATR_STOP_MULTIPLIERS`, `RRS` 기반 vectorbt SL/TP 실험

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
  MAX_STEPS=10 \
  NO_REVIEW=1 \
  LOG_LEVEL=INFO \
  RISK_PCT=0.005
```

성공 기준:

- `backtests/data/market_data.sqlite`에서 캔들을 읽어 백테스트가 시작됩니다.
- 백테스트 시작 직후 `backtest_runs`에 실행 row가 먼저 생성됩니다.
- 실행 중 각 판단은 `backtest_decisions`에 즉시 저장되고, 청산된 거래는 `backtest_trades`에 즉시 저장됩니다.
- 종료 시 최종 잔고, 거래 수, PnL 같은 요약값이 `backtest_runs`에 갱신되고 `status='completed'`가 됩니다.
- Ctrl-C 등으로 중단하면 `status='interrupted'`, 예외 종료면 `status='failed'`로 남습니다. 미완료 run은 성과 집계에서 제외합니다.
- 리포트와 JSON 산출물은 종료 후 `backtests/reports/`, `backtests/results/`, SQLite 리포트 테이블에 기록됩니다.
- SQLite `backtest_reports`는 Markdown 본문과 요약 캐시만 저장하고, `report_path`/`chart_path`는 신규 저장 시 NULL로 둡니다. 차트는 `run_id` 기준으로 candles/trades/decisions에서 다시 그리는 것을 기준으로 합니다.
- validator가 차단한 판단은 실행 중에도 `backtest_decisions`에 `REJECTED`로 저장됩니다.
- `backtests/logs/backtest_<run_id>.jsonl`에 `backtest_start`, `step_start`, `node_complete`, `decision_recorded`, `trade_opened`, `trade_closed`, `step_complete`, `backtest_complete` 이벤트가 남습니다.
- 로그의 `elapsed_ms`, `rejection_reason`, `strategy`, `market_regime`, `trade_id`를 보면 어떤 단계가 느린지, 어떤 조건이 수익/손실에 영향을 줬는지 추적할 수 있습니다.

첫 10개 판단 지점이 모두 HOLD라면 다음 구간으로 이동합니다.

```bash
make backtest-run \
  SYMBOL=BTCUSD \
  TIMEFRAMES=M15,M30 \
  FROM=2025-01-01 \
  TO=2025-01-31 \
  STEP=20 \
  START_STEP=10 \
  MAX_STEPS=10 \
  NO_REVIEW=1 \
  LOG_LEVEL=INFO \
  RISK_PCT=0.005
```

빠른 진단 후 최종 검증은 `MAX_STEPS`와 `NO_REVIEW`를 빼고 실행합니다.

```bash
make backtest-run \
  SYMBOL=BTCUSD \
  TIMEFRAMES=M15,M30 \
  FROM=2025-01-01 \
  TO=2025-01-31 \
  STEP=20 \
  RISK_PCT=0.005
```

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

구조화 실행 로그:

```text
backtests/logs/
```

청산 후 복기:

```text
trading_logs/review_*.md
trading_logs/trading_logs.sqlite
```

## 자주 쓰는 조회 쿼리

상세 스키마와 추가 조회 예시는 [sqlite-storage.md](../storage/sqlite-storage.md)를 기준으로 관리합니다. 여기서는 백테스트 후 바로 확인할 최소 쿼리만 둡니다.

최근 백테스트 실행:

```bash
sqlite3 -header -column backtests/data/market_data.sqlite \
  "SELECT run_id, status, symbol, timeframes, data_from, data_to, total_trades, net_pnl FROM backtest_runs ORDER BY created_at DESC LIMIT 10;"
```

완료된 백테스트만 보기:

```bash
sqlite3 -header -column backtests/data/market_data.sqlite \
  "SELECT run_id, symbol, timeframes, total_trades, net_pnl, profit_factor FROM backtest_runs WHERE status = 'completed' ORDER BY created_at DESC LIMIT 10;"
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

- SQLite 저장소 구조: [sqlite-storage.md](../storage/sqlite-storage.md)
- 재생 가능한 트레이딩 데이터 원칙: [replayable-trading-data.md](../storage/replayable-trading-data.md)
- 전체 실행 가이드: [execution-guide.md](./execution-guide.md)
- 테스트 정책: [testing-guide.md](./testing-guide.md)
