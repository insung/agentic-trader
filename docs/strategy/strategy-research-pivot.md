# Strategy Research Pivot

이 문서는 최근 BTCUSD 백테스트에서 반복적으로 `0 trades`가 발생한 이유와, 다음 AI 세션이 같은 실험을 반복하지 않기 위한 전략 연구 방향을 정리합니다.

## 현재 결론

- [x] 최근 여러 BTCUSD 백테스트에서 매매가 거의 또는 전혀 발생하지 않았습니다.
- [x] 문제는 LLM이 충분히 공격적이지 않은 것만이 아니라, 전략 후보 생성 구조가 너무 좁다는 점입니다.
- [x] 현재 구조는 `LLM agents decide trade -> Python validates`에 가깝습니다.
- [x] 다음 단계는 `Python strategy candidates generate possible setups -> Python filters/scores -> LLM explains/selects among valid setups`로 피벗하는 것입니다.
- [x] `새 전략을 즉시 실전/Paper로 승격하는 것`은 보류하지만, 연구용 quant baseline 추가 자체는 허용됩니다.

## 관측된 현상

- [x] `Moving Average Crossover`는 Bullish/Bearish regime에서 대부분 주입됩니다.
- [x] `Bollinger Bands Reversion`은 Ranging/High Volatility regime에서만 제한적으로 주입됩니다.
- [x] 최근 실험에서는 MA Crossover를 임시 비활성화하고 Bollinger-only 백테스트를 분리 검증하기로 했습니다.
- [x] `STEP=1`, `MAX_STEPS=20`은 M15 기준 약 5시간만 보는 짧은 구간입니다. 월 전체 결과로 해석하면 안 됩니다.
- [x] `LOG_LEVEL=INFO`는 JSONL 구조화 로그의 최소 레벨이고, 콘솔 상세 로그가 아닙니다. decision 원인은 SQLite `backtest_decisions`를 봐야 합니다.

## 반복된 무매매 원인

- [x] MA Crossover는 최근 EMA cross를 요구하므로, 이미 진행 중인 추세를 거의 잡지 못합니다.
- [x] 강한 추세가 확인되어도 cross age가 오래되면 HOLD 또는 REJECTED가 됩니다.
- [x] 눌림목 구간에서는 M15 ADX가 약하거나 가격이 EMA20 아래/위 조건을 충족하지 못해 HOLD가 됩니다.
- [x] 다시 추세가 재개되는 구간에서는 RSI 과매수/과매도, Bollinger 상단/하단 근접 때문에 추격 진입으로 판단되어 HOLD가 됩니다.
- [x] 일부 주문은 R:R이 거의 2.0이어도 부동소수점 계산상 `1.999...`가 되어 guardrail에서 차단됐습니다.

## 참고 프로젝트

- [x] vectorbt를 빠른 quant research 레이어로 통합합니다.
  - SQLite `candles`를 입력으로 Bollinger baseline 파라미터 스윕을 실행합니다.
  - 결과는 `quant_runs`, `quant_results`에 저장하고, 실전 주문은 기존 MT5/guardrail 경로를 유지합니다.
- [ ] Freqtrade를 참고합니다.
  - 전략 파일, dry-run/live, hyperopt, 결과 비교, 운영 로그 구조가 좋습니다.
  - 참고 대상: 전략 운영 UX, 파라미터 실험, dry-run/live 승격.
- [ ] backtesting.py를 참고합니다.
  - 빠른 Python baseline backtest와 지표 overlay 설계에 적합합니다.
  - 참고 대상: 볼린저밴드 overlay, 단순 전략 성능 비교, 차트 리포트.
- [ ] QuantConnect Lean을 참고합니다.
  - 장기적으로 backtest/live 엔진 구조를 볼 때 참고합니다.
  - 현재 단계에서는 과하게 크므로 구조만 참고합니다.
- [ ] ai-hedge-fund류 프로젝트는 멀티 에이전트 철학만 참고합니다.
  - 실제 주문 guardrail, deterministic validator, MT5 execution은 이 프로젝트 원칙을 유지합니다.

## 권장 피벗

### Before

```text
LLM agents decide trade
Python validates
Guardrail executes or blocks
```

### After

```text
Python scans market data
Python generates candidate setups
Python validator filters/scores candidates
LLM explains/selects among valid candidates
Guardrail executes or blocks
```

## 새 구조의 목표

- [ ] 후보가 없으면 LLM을 호출하지 않고 SKIP합니다.
- [ ] 후보가 있으면 LLM은 무에서 BUY/SELL/HOLD를 만들지 않고, 이미 계산된 후보 중 선택/설명합니다.
- [ ] 무매매 원인을 `후보 없음`, `validator 차단`, `guardrail 차단`, `LLM 기각`으로 분리합니다.
- [ ] 전략 연구는 LLM 비용 없이 deterministic baseline부터 빠르게 비교합니다.
- [ ] live/paper 승격 전에는 후보 생성기, validator, guardrail, backtest 결과가 모두 일관되어야 합니다.

## 우선 구현할 것

### 1. No-Trade Audit

- [ ] 최근 run의 regime 분포를 집계합니다.
- [ ] 전략 주입 여부를 집계합니다.
- [ ] LLM이 주문 후보를 냈는지 집계합니다.
- [ ] validator 차단 사유를 집계합니다.
- [ ] guardrail 차단 사유를 집계합니다.
- [ ] HOLD reasoning을 키워드 또는 구조화 reason으로 분류합니다.
- [ ] 이후 N개 캔들에서 진입했으면 TP/SL 중 무엇이 먼저 닿았는지 시뮬레이션합니다.

### 2. Deterministic Baseline Backtests

- [x] LLM 없이 Bollinger Reversion baseline을 구현합니다.
  - `make install-quant`로 vectorbt를 옵션 설치합니다.
  - `make quant-run SYMBOL=BTCUSD TIMEFRAME=M15 FROM=... TO=...`로 실행합니다.
  - 결과는 `quant_runs`, `quant_results`에 저장합니다.
- [x] M15 진입 + M30 필터 구조의 Bollinger MTF baseline을 구현합니다.
  - `make quant-run QUANT_STRATEGY=bollinger_mtf TIMEFRAME=M15 FILTER_TIMEFRAME=M30 FROM=... TO=...`로 실행합니다.
  - 타임프레임별 독립 전략이 아니라, base timeframe 신호를 higher timeframe으로 필터링하는 단일 전략입니다.
- [x] LLM 없이 Trend Pullback baseline을 구현합니다.
  - `make quant-run QUANT_STRATEGY=trend_pullback TIMEFRAME=M15 FILTER_TIMEFRAME=M30 FROM=... TO=...`로 실행합니다.
  - M15 EMA 추세와 ATR 눌림목, M30 EMA 방향 필터를 사용합니다.
- [x] Trend Pullback 실패 분석을 반영한 `trend_pullback_reclaim` baseline을 구현합니다.
  - 거래 과다를 줄이기 위해 EMA reclaim, higher timeframe close alignment, RSI 회복, cooldown을 추가합니다.
  - EMA20 단일 이탈 청산 대신 EMA50 또는 추세 반전 청산으로 완화합니다.
- [x] LLM 없이 Breakout baseline을 구현합니다.
  - `make quant-run QUANT_STRATEGY=breakout TIMEFRAME=M15 FILTER_TIMEFRAME=M30 FROM=... TO=...`로 실행합니다.
  - 최근 고가/저가 돌파, ATR 버퍼, RSI momentum, higher timeframe trend filter를 사용합니다.
- [x] LLM 없이 MACD baseline을 구현합니다.
  - `make quant-run QUANT_STRATEGY=macd TIMEFRAME=M15 FROM=... TO=...`로 실행합니다.
  - MACD line, signal line, histogram cross를 사용한 momentum baseline입니다.
- [x] 저장된 quant run을 비교하는 `make quant-summary`를 추가합니다.
  - 대화에 붙여넣은 결과가 아니라 SQLite `quant_runs`, `quant_results` 기준으로 전략별 rank 1 결과를 비교합니다.
  - 월별 비교가 필요하면 `SUMMARY_MONTHLY=1`로 `data_from` 월별 best run을 확인합니다.
- [ ] LLM 없이 MA Crossover baseline을 구현합니다.
- [x] Buy & Hold benchmark를 추가합니다.
- [x] No-trade benchmark를 추가합니다.
- [ ] Random benchmark를 추가합니다.
- [ ] 각 baseline의 거래 수, 승률, profit factor, MDD, 기대값을 비교합니다.

### 3. Candidate Setup Generator

- [ ] Bollinger long/short candidate를 Python에서 생성합니다.
- [ ] MA cross long/short candidate를 Python에서 생성합니다.
- [ ] 후보마다 `candidate_id`, `strategy`, `action`, `entry`, `sl`, `tp`, `reason`, `score`, `reject_reason`을 부여합니다.
- [ ] 후보가 없으면 LLM을 호출하지 않는 경로를 설계합니다.
- [ ] 후보가 있으면 LLM이 후보 중 승인/기각/보류를 설명하게 합니다.

### 4. R:R 실험

- [ ] `min_rr=2.0`에 부동소수점 tolerance를 둘지 결정합니다.
- [ ] `min_rr=1.7`, `1.5`, `1.3` 실험군을 비교합니다.
- [ ] 비용/스프레드/슬리피지 반영 전에는 낮은 R:R을 live 기본값으로 승격하지 않습니다.

## 현재 보류할 것

- [ ] 새 전략을 즉시 실전/Paper로 승격하는 것은 보류합니다.
  - 이유: 전략 수를 늘리기 전에 현재 Bollinger/MA가 왜 후보를 만들지 못하는지 데이터로 분리해야 합니다.
  - 허용 범위: 연구용 quant baseline은 추가할 수 있습니다. breakout baseline처럼 DB에 기록되는 실험용 전략은 허용됩니다.
- [ ] LLM 프롬프트만 더 공격적으로 바꾸는 것은 보류합니다.
  - 이유: 통과 가능한 후보 자체가 적으면 프롬프트 변경은 검증 불가능한 주문을 늘릴 가능성이 큽니다.
- [ ] live/paper 장기 운영은 보류합니다.
  - 이유: 현재 구조는 실제 운영에서도 긴 무포지션 구간이 발생할 가능성이 큽니다.

## 다음 AI 세션의 시작 작업

가장 먼저 할 작업은 `No-Trade Audit`입니다.

완료 기준:

- [ ] 입력으로 `run_id`를 받습니다.
- [ ] `backtest_runs`, `backtest_decisions`, `backtest_trades`, `candles`를 조회합니다.
- [ ] regime, strategy, status, action, rejection reason을 집계합니다.
- [ ] HOLD reason을 최소한 키워드 기반으로 분류합니다.
- [ ] 결과를 콘솔 또는 Markdown으로 출력합니다.
- [ ] 이후 API/UI에서 재사용할 수 있게 Python 함수로 분리합니다.
- [ ] 테스트를 추가합니다.

## 관련 문서

- `docs/backtesting/backtesting-guide.md`
- `docs/storage/sqlite-schema-reference.md`
- `docs/ux/README.md`
- `docs/ux/operations-ux-roadmap.md`
- `backend/features/trading/strategy_validators.py`
- `backend/config/strategies_config.json`
