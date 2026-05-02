# Strategy Addition Mechanism

이 문서는 새 전략을 이 프로젝트에 추가할 때 따라야 하는 절차를 정리합니다.  
목표는 `docs/trading-strategies/`, `backend/config/strategies_config.json`, `backend/features/trading/strategy_validators.py`, quant research, 테스트를 서로 어긋나지 않게 유지하는 것입니다.

## 핵심 원칙

- 전략 설명은 `docs/trading-strategies/`에 둡니다.
- 전략 활성화와 장세 매핑은 `backend/config/strategies_config.json`에서 관리합니다.
- 주문 가능 여부는 `backend/features/trading/strategy_validators.py`의 deterministic gate가 최종 판단합니다.
- quant research는 `make quant-run`으로 별도 검증합니다.
- 실전/Paper로 올리기 전에는 문서, config, validator, 테스트가 한 세트로 존재해야 합니다.
- research baseline과 runtime promotion은 다른 단계입니다.

## 연구용 baseline과 실전 승격을 분리합니다

새 전략을 다룰 때 가장 먼저 구분해야 하는 것은 아래 두 단계입니다.

### 1. 연구용 baseline

- `backend/features/trading/quant_research.py`에 구현합니다.
- `backend/scripts/run_quant_research.py`와 `Makefile`을 통해 실행합니다.
- vectorbt로 과거 캔들을 빠르게 스윕합니다.
- 결과는 `quant_runs`, `quant_results`에 저장합니다.
- 목적은 "데이터상 작동하는가"를 보는 것입니다.

### 2. 실전/Paper 승격

- `docs/trading-strategies/`에 문서를 둡니다.
- `backend/config/strategies_config.json`에 등록합니다.
- `backend/features/trading/strategy_validators.py`에 deterministic gate를 둡니다.
- unit test와 backtest/summary 검증을 추가합니다.
- 목적은 "지금 주문해도 되는가"를 결정하는 것입니다.

research baseline이 좋다고 자동으로 실전 전략이 되지 않습니다.

## 전략 추가 순서

### 1. 전략 문서를 작성합니다

`docs/trading-strategies/<strategy_name>.md`를 생성합니다.

문서에는 최소한 아래가 있어야 합니다.

- 전략 개요
- 롱/숏 진입 조건
- 청산 조건
- 금지 장세
- 상위 타임프레임 조건
- ATR/RSI/Bollinger/EMA 등 검증 가능한 지표 조건

이 문서는 Strategist와 Chief Trader가 읽는 런타임 지식입니다.

### 2. 전략 registry에 등록합니다

`backend/config/strategies_config.json`에 전략을 추가합니다.

등록 시 명시할 항목:

- 전략 이름
- 허용 장세
- 주입할 문서 파일
- 필요한 타임프레임

이 단계가 끝나야 전략이 LangGraph pipeline에서 후보로 주입됩니다.

### 3. validator를 추가합니다

`backend/features/trading/strategy_validators.py`에 deterministic gate를 추가합니다.

검증해야 하는 항목:

- 필요한 indicator snapshot 존재 여부
- 방향별 진입 조건
- 상위 타임프레임 충돌 여부
- ATR 기반 최소 SL 거리
- 과열/추격/횡보장 차단 조건

validator는 “좋아 보인다”가 아니라 “실제로 수치가 맞는가”만 판단해야 합니다.

### 3-1. Chief Trader 계약을 전략 문서와 맞춥니다

전략이 paper/live 승격 후보가 되면 Chief Trader는 문서를 직접 해석하는 대신, 전략 registry와 문서에 적힌 **실행 계약**을 읽어야 합니다.

핵심은 다음입니다.

- `minimum_risk_reward`: 주문이 실행되기 위해 만족해야 하는 최소 손익비
- `target_rr`: Chief Trader가 실행용 TP를 계산할 때 사용하는 목표 손익비
- `exit_plan`: primary target, runner, full exit처럼 청산 의도를 설명하는 메타데이터

현재 런타임은 단일 executable TP만 지원하므로, 전략 문서에 1:3 runner가 적혀 있더라도 실제 주문은 `minimum_risk_reward`를 만족하는 **단일 TP**로 변환되어야 합니다.

즉, 새 전략을 추가할 때마다 Chief Trader 로직을 전략별로 고치는 방식이 아니라:

1. 전략 문서에 실행 계약을 적고
2. `backend/config/strategies_config.json`에 같은 계약을 넣고
3. Chief Trader는 그 계약을 읽어 공통 규칙으로 TP를 계산합니다.

이 방식이어야 전략이 늘어나도 Chief Trader 유지보수 비용이 폭증하지 않습니다.

### 4. quant research baseline을 만듭니다

`backend/features/trading/quant_research.py`와 `backend/scripts/run_quant_research.py`에 전략별 baseline을 추가합니다.

quant research에서는 다음을 확인합니다.

- PF
- MDD
- 수익률
- 거래 수
- 월별 일관성

현재 프로젝트의 기준은 비용/슬리피지 포함 PF와 MDD입니다.

quant research는 공통 harness를 사용하므로, 실행 로그에는 다른 전략의 기본 knob가 같이 보일 수 있습니다.

- 예를 들어 `macd`는 `MACD_FAST_WINDOWS`, `MACD_SLOW_WINDOWS`, `MACD_SIGNAL_WINDOWS`가 핵심입니다.
- `breakout`은 `BREAKOUT_LOOKBACKS`, `BREAKOUT_ATR_BUFFERS`, `BREAKOUT_RSI_LOWERS`, `BREAKOUT_RSI_UPPERS`가 핵심입니다.
- `bollinger`는 `BB_WINDOWS`, `BB_STDS`, `RSI_LOWERS`, `RSI_UPPERS`가 핵심입니다.

이 값들은 `Makefile`이 공통 인자로 넘기더라도, 실제 전략이 읽지 않으면 결과에 영향을 주지 않아야 합니다.

비교 기준용 baseline은 승격 후보와 분리해서 봅니다.

- `buy_hold`: 시장 자체의 방향성 기준
- `no_trade`: 아무 것도 하지 않았을 때의 기준
- `random`: 무작위 진입/청산의 기준

이 세 baseline은 "전략이 의미가 있는가"를 해석하는 축이지, 실전 승격 후보가 아닙니다.

### 파라미터 수가 기대와 다를 때 해석하는 법

`run_quant_research` 결과의 parameter set 수는 보통 아래 조합입니다.

- 전략 고유 파라미터 리스트의 카디널리티
- 공통 sweep 리스트의 카디널리티
- 선택적 cooldown / stop / rr 리스트의 카디널리티

예를 들어 MACD에서 다음처럼 보이면:

```text
--macd-fast-windows "12"
--macd-slow-windows "26"
--macd-signal-windows "9"
--cooldown-bars "8,12,20"
--atr-stop-multipliers "1.0,1.5"
--rrs "1.3,1.5,2.0"
```

이론상 조합 수는 `1 * 1 * 1 * 3 * 2 * 3 = 18`입니다.
즉, 18개가 나오면 이상한 것이 아니라 **공통 sweep이 곱해진 결과**입니다.

MACD에서 조합 수를 더 줄이고 싶으면 아래처럼 단일 값으로 고정합니다.

```bash
make quant-run \
  SYMBOL=BTCUSD \
  TIMEFRAME=M15 \
  FROM=2025-01-01 \
  TO=2025-06-30 \
  QUANT_STRATEGY=macd \
  MACD_FAST_WINDOWS=12 \
  MACD_SLOW_WINDOWS=26 \
  MACD_SIGNAL_WINDOWS=9 \
  COOLDOWN_BARS=8 \
  ATR_STOP_MULTIPLIERS=1.0 \
  RRS=1.3
```

이 문서에서 중요한 것은 "로그에 무엇이 보였는가"가 아니라 "실제로 어떤 전략 knob가 결과를 만들었는가"입니다.

### MACD 사례의 교훈

- MACD baseline은 research baseline으로는 유효합니다.
- 다만 6개월 BTCUSD M15 구간에서 PF가 1 미만이면 승격 대상이 아닙니다.
- `Makefile`과 런처가 공통 knobs를 넘기는 것은 버그가 아니라 연구 harness의 기본 동작입니다.
- 다른 전략의 기본 knob가 출력에 보여도, 해당 전략이 읽지 않으면 결과 해석에 넣지 않습니다.
- 기대와 다른 카디널리티가 보이면 먼저 `cooldown`, `atr_stop_multiplier`, `rr` 같은 공통 sweep을 확인합니다.

### 5. 테스트를 추가합니다

전략 추가 시 최소한 아래 테스트가 필요합니다.

- quant baseline이 vectorbt를 타는지
- validator가 필수 조건을 걸러내는지
- persistence가 SQLite에 제대로 저장되는지
- summary/query가 run_id와 월별 비교를 지원하는지

### 6. 문서를 업데이트합니다

아래 문서들을 갱신합니다.

- `docs/research/strategy-research-pivot.md`
- `docs/guides/backtesting-guide.md`
- `docs/roadmap/001-mvp-roadmap.md`

## 승격 전 체크리스트

새 전략이 quant research에서 좋아 보여도 아래를 전부 통과하기 전에는 승격하지 않습니다.

- [ ] 전략 문서가 `docs/trading-strategies/`에 있다.
- [ ] `backend/config/strategies_config.json`에 등록되어 있다.
- [ ] `backend/features/trading/strategy_validators.py`에 deterministic gate가 있다.
- [ ] `make quant-run`으로 재현 가능한 baseline이 있다.
- [ ] `quant_runs`, `quant_results`에 저장된다.
- [ ] `make quant-summary`로 run_id와 월별 비교가 가능하다.
- [ ] 비용/슬리피지 포함 PF가 1.20 이상이다.
- [ ] MDD가 10% 이하이다.
- [ ] 거래 수가 충분하다.
- [ ] 월별로 일관성이 있다.
- [ ] validator와 quant baseline이 같은 방향의 조건을 평가한다.
- [ ] Chief Trader가 전략 문서의 `minimum_risk_reward`와 registry 계약을 읽고 실행용 TP를 계산한다.
- [x] No-Trade Audit을 통해 후보 없음/validator 차단/guardrail 차단을 분리했다.
- [ ] 테스트가 존재한다.
- [ ] 단독 전략으로 먼저 검증했으며, 다른 전략과 섞지 않았다.

## 추가 후 확인 순서

1. `make test`
2. `make quant-run`
3. `make quant-summary`
4. 월별 비교 결과 확인
5. 비용/슬리피지 반영 후 재검증
6. run_id 기준 DB 원문 확인
7. 승격 기준을 만족하지 못하면 문서만 남기고 실전 승격하지 않음

## 금지 사항

- `docs/trading-strategies/`를 코드 패키지로 옮기지 않습니다.
- `strategies_config.json`을 없애지 않습니다.
- validator 없이 전략을 실전/Paper로 승격하지 않습니다.
- quant 결과 하나만 보고 승격하지 않습니다.
- 전략별 baseline과 runtime validator를 혼동하지 않습니다.
- 공통 harness 출력에 보이는 불필요한 knobs를 곧바로 버그로 단정하지 않습니다.

## 다른 AI 세션이 이 문서를 읽을 때의 사용법

새 전략을 추가하고 싶으면 다음 순서로만 진행합니다.

1. 전략 문서를 만든다.
2. registry에 등록한다.
3. validator를 만든다.
4. quant baseline을 만든다.
5. 테스트한다.
6. 결과가 좋을 때만 승격 문서를 갱신한다.

새 AI 세션은 research baseline과 실전 승격을 같은 단계로 취급하면 안 됩니다.
quant baseline은 많이 추가할 수 있지만, 실제 주문 경로에 들어가는 전략은 보수적으로 선별해야 합니다.
