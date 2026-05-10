---
trigger: always_on
---

# Agentic Trader Project Rule

이 문서는 `AGENTS.md`가 참조하는 구현 규칙 SSOT입니다. Hermes Agent는 이 규칙을 우선합니다.

## 1. Architecture Baseline

이 저장소는 전통적인 전역 레이어 구조(`backend/app/domain/use_cases/adapters/infrastructure`)를 강제하지 않습니다.

기본 구조는 **vertical slice + Clean Architecture dependency direction**입니다.

```text
backend/
├── main.py                  # thin entrypoint only
├── api/                     # FastAPI app factory and routers
│   └── v1/
├── core/                    # shared Pydantic contracts, exceptions
├── features/
│   └── trading/             # trading vertical slice
│       ├── schemas.py       # trading API DTOs
│       ├── usecase.py       # application use cases
│       ├── guardrails.py    # pure safety policy
│       ├── indicators.py    # pure indicator calculation
│       ├── strategy_validators.py
│       ├── mt5_adapter.py
│       └── persistence/     # SQLite stores and DB connection helpers
├── services/                # application services and schedulers
├── workflows/               # LangGraph state machine and LLM nodes
└── scripts/                 # CLI entrypoints for backtest, migration, research
```

기존 파일을 고칠 때는 위 구조로 점진적으로 이동합니다. 대규모 파일 이동은 사용자가 요청했거나 해당 작업의 안전한 완료에 필요할 때만 합니다.

## 2. Dependency Direction

안쪽 정책 로직은 바깥쪽 도구를 몰라야 합니다.

허용되는 흐름:

```text
FastAPI routers / scripts / LangGraph nodes
    -> services / use cases
    -> pure trading policy functions
    -> adapters / persistence stores
```

금지되는 흐름:

```text
guardrails.py -> FastAPI / SQLite / MT5 / LangChain
indicators.py -> FastAPI / SQLite / MT5 / LangChain
strategy_validators.py -> FastAPI / SQLite / MT5 / LangChain
core/* -> api / workflows / features implementation details
api routers -> private DB helpers such as _connect
```

## 3. FastAPI Rules

`backend/main.py`는 얇은 진입점이어야 합니다.

- `main.py`에는 `create_app()` 호출과 `uvicorn.run()` 정도만 둡니다.
- FastAPI app 생성, lifespan, router 등록은 `backend/api/app.py`로 분리합니다.
- API endpoint는 `backend/api/v1/*.py`에 둡니다.
- router는 HTTP request/response 변환과 usecase/service 호출만 담당합니다.
- router에서 raw SQL, `sqlite3.connect`, MT5 세부 호출, LangGraph 내부 상태 조작을 직접 하지 않습니다.

권장 router 구성:

```text
backend/api/v1/health.py
backend/api/v1/symbols.py
backend/api/v1/strategies.py
backend/api/v1/trade.py
backend/api/v1/triggers.py
```

## 4. DTO and Schema Rules

DTO는 사용 경계에 맞게 분리합니다.

- API request/response DTO는 `backend/features/<domain>/schemas.py`에 둡니다.
- trading API DTO는 `backend/features/trading/schemas.py`에 둡니다.
- 여러 도메인이 공유하는 Pydantic contract만 `backend/core/`에 둡니다.
- LangGraph state는 `backend/workflows/state.py` 또는 공유가 필요한 경우 `backend/core/state_models.py`에 둡니다.
- LLM structured output schema는 API DTO와 섞지 않습니다. workflow 전용 schema로 유지하거나 별도 agent schema로 분리합니다.

`main.py`, router, workflow node에 DTO class가 계속 쌓이면 분리 대상으로 봅니다.

## 5. Trading Slice Rules

trading 기능은 가능한 한 `backend/features/trading/`에 응집시킵니다.

- `guardrails.py`: 주문 안전 규칙, risk-percent lot sizing, SL/TP 검증 같은 순수 정책 함수.
- `indicators.py`: OHLCV 기반 deterministic indicator 계산.
- `strategy_validators.py`: 전략별 주문 직전 deterministic gate.
- `usecase.py`: 정책 함수와 adapter/store를 조합하는 application usecase.
- `mt5_adapter.py`: MT5 외부 연동만 담당.
- `persistence/`: SQLite 저장소와 DB 연결 정책.

LLM은 전략을 제안할 수 있지만, 주문 가능 여부는 반드시 Python guardrail과 strategy validator가 결정합니다.

## 6. Persistence and DB Rules

DB 코드는 흩어두지 않고 해당 domain slice의 `persistence/` 아래에 모읍니다.

권장 구조:

```text
backend/features/trading/persistence/
├── connection.py
├── backtest_store.py
├── trading_log_store.py
└── trigger_store.py
```

규칙:

- `sqlite3.connect`, row factory, schema init, migration helper는 persistence 모듈 안에 둡니다.
- `_connect` 같은 private helper는 persistence 모듈 밖에서 import하지 않습니다.
- API, workflow, script는 공개 store 함수만 호출합니다.
- store는 저장과 조회만 담당합니다. 전략 판단, 리스크 계산, 주문 승인 로직을 넣지 않습니다.
- DB schema 변경은 기존 데이터 호환과 migration 경로를 고려합니다.

예: router에서 직접 SQL을 실행하지 말고 store 공개 함수로 감쌉니다.

```python
# good
rules = list_schedule_rules()
set_schedule_rule_enabled(rule_id, enabled)
delete_schedule_rule(rule_id)

# bad
from backend.features.trading.trigger_store import _connect
conn.execute("UPDATE trigger_schedule_rules ...")
```

## 7. Workflow and LLM Rules

LangGraph는 workflow를 통제하고, LLM은 한 노드의 structured reasoning만 담당합니다.

- `backend/workflows/graph.py`는 노드와 edge 구성을 담당합니다.
- `backend/workflows/nodes.py`는 LLM 호출, prompt 주입, state 변환을 담당합니다.
- 지표 계산, 전략 검증, 주문 안전성 판단은 workflow node 안에 새로 구현하지 말고 trading slice의 함수/usecase를 호출합니다.
- LLM output은 Pydantic structured output으로 받습니다.
- LLM이 계산한 indicator, lot size, RR, SL/TP 안전성은 신뢰하지 않습니다.

## 8. Services and Scripts

`backend/services/`는 여러 구성 요소를 연결하는 application service와 scheduler에 한정합니다.

- trading 도메인 규칙은 `services/`가 아니라 `features/trading/`에 둡니다.
- scheduler, workflow trigger, background orchestration은 service에 둘 수 있습니다.
- `backend/scripts/`는 CLI entrypoint입니다. 핵심 로직은 feature/usecase/store 함수로 내려야 합니다.

## 9. Strategy Registry Rules

새 전략은 세 파일을 한 세트로 다룹니다.

- 전략 문서: `docs/trading-strategies/`
- 전략 registry: `backend/config/strategies_config.json`
- deterministic validator: `backend/features/trading/strategy_validators.py`

validator가 없는 전략은 live/paper 주문으로 승격하지 않습니다.

## 10. Testing Rules

코드 변경은 TDD gate를 기본값으로 따릅니다.

1. 실패하는 테스트를 먼저 작성하거나 기존 테스트로 실패 조건을 재현합니다.
2. 실패를 확인합니다.
3. 최소 구현으로 통과시킵니다.
4. `make test`를 실행합니다.
5. 최종 응답에 실행한 테스트 명령과 결과를 남깁니다.

문서만 변경하는 작업은 선행 실패 테스트를 생략할 수 있습니다. 이 경우 최종 응답에 문서 변경이라 테스트를 생략했다고 명시합니다.

필수 테스트 기준:

- guardrail, validator, order execution, position tracking, persistence 변경: 단위 테스트 추가/수정.
- LangGraph routing 또는 LLM node 변경: mock 기반 테스트 추가/수정.
- DB schema 변경: migration/compatibility 테스트 추가 또는 기존 데이터 호환 확인.
- API router 변경: endpoint response와 error path 테스트 추가/수정.

## 11. Python Coding Rules

모든 Python 코드는 PEP 8 스타일 가이드를 준수하며, 아래 규칙을 엄격히 따릅니다.

- **No Local Imports:** 모든 `import` 문은 반드시 파일 최상단(top-level)에 위치해야 합니다.
- 함수나 클래스 메서드 내부에서 `import`를 호출하는 지역 임포트는 어떤 경우에도 금지합니다.
- 의존성 구조를 설계할 때부터 순환 참조가 발생하지 않도록 vertical slice 원칙을 준수하십시오.

## 12. Refactor Rules

구조 개선은 동작 보존을 우선합니다.

- 먼저 현재 public API와 테스트 기대값을 확인합니다.
- 파일 이동 시 import 경로와 기존 테스트를 함께 갱신합니다.
- unrelated refactor를 섞지 않습니다.
- 사용자 변경으로 보이는 파일은 되돌리지 않습니다.
- 큰 구조 변경은 작은 단계로 나누고 각 단계마다 테스트 가능한 상태를 유지합니다.
