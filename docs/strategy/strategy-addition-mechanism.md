# Strategy Addition Mechanism

이 문서는 새 전략을 이 프로젝트에 추가할 때 따라야 하는 절차를 정리합니다.  
목표는 `docs/trading-strategies/`, `backend/config/strategies_config.json`, `backend/features/trading/strategy_validators.py`, quant research, 테스트를 서로 어긋나지 않게 유지하는 것입니다.

## 핵심 원칙

- 전략 설명은 `docs/trading-strategies/`에 둡니다.
- 전략 활성화와 장세 매핑은 `backend/config/strategies_config.json`에서 관리합니다.
- 주문 가능 여부는 `backend/features/trading/strategy_validators.py`의 deterministic gate가 최종 판단합니다.
- quant research는 `make quant-run`으로 별도 검증합니다.
- 실전/Paper로 올리기 전에는 문서, config, validator, 테스트가 한 세트로 존재해야 합니다.

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

### 4. quant research baseline을 만듭니다

`backend/features/trading/quant_research.py`와 `backend/scripts/run_quant_research.py`에 전략별 baseline을 추가합니다.

quant research에서는 다음을 확인합니다.

- PF
- MDD
- 수익률
- 거래 수
- 월별 일관성

현재 프로젝트의 기준은 비용/슬리피지 포함 PF와 MDD입니다.

### 5. 테스트를 추가합니다

전략 추가 시 최소한 아래 테스트가 필요합니다.

- quant baseline이 vectorbt를 타는지
- validator가 필수 조건을 걸러내는지
- persistence가 SQLite에 제대로 저장되는지
- summary/query가 run_id와 월별 비교를 지원하는지

### 6. 문서를 업데이트합니다

아래 문서들을 갱신합니다.

- `docs/strategy/strategy-research-pivot.md`
- `docs/backtesting/backtesting-guide.md`
- `docs/mvp-implementation-plan.md`

## 추가 후 확인 순서

1. `make test`
2. `make quant-run`
3. `make quant-summary`
4. 월별 비교 결과 확인
5. 비용/슬리피지 반영 후 재검증

## 금지 사항

- `docs/trading-strategies/`를 코드 패키지로 옮기지 않습니다.
- `strategies_config.json`을 없애지 않습니다.
- validator 없이 전략을 실전/Paper로 승격하지 않습니다.
- quant 결과 하나만 보고 승격하지 않습니다.

## 다른 AI 세션이 이 문서를 읽을 때의 사용법

새 전략을 추가하고 싶으면 다음 순서로만 진행합니다.

1. 전략 문서를 만든다.
2. registry에 등록한다.
3. validator를 만든다.
4. quant baseline을 만든다.
5. 테스트한다.
6. 결과가 좋을 때만 승격 문서를 갱신한다.

