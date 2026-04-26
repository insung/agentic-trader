# Agentic Trader AI Project Rules

이 파일은 Codex, Gemini CLI, Google Antigravity 등 이 저장소에 접속하는 모든 AI 세션의 **공통 지침 SSOT(Single Source of Truth)**입니다. 도구별 설정 파일이 있더라도 프로젝트 원칙은 이 파일을 우선합니다.

## 1. Project Goal

우리는 단순한 트레이딩 봇이 아니라 **"나만의 무인 펀드 회사(Zero-Human Hedge Fund)"**를 구축합니다.

1. **Role-based AI Organization:** Tech Analyst, Strategist, Chief Trader, Risk Reviewer처럼 명확한 직책과 책임을 가진 AI 직원들이 협업합니다. 인간은 이사회(Board) 역할을 합니다.
2. **LangGraph Engine:** 매매 제어 흐름은 느리고 비결정적인 티켓/스킬 체계가 아니라 Python LangGraph 상태 머신이 통제합니다.
3. **Safety & Air-gap:** 어떤 AI도 MT5/거래소에 직접 주문을 넣을 수 없습니다. 모든 주문은 FastAPI/Python 백엔드의 hard-coded guardrail을 통과해야 합니다.
4. **Deterministic Strategy Gates:** LLM은 전략을 제안할 수 있지만, 주문 직전에는 Python validator가 EMA/ADX/ATR/Bollinger/RSI 등 계산값으로 전략 조건을 다시 검산해야 합니다.

## 2. Mandatory Session Startup

새 AI 세션은 작업 전 반드시 아래 순서로 읽고 현재 상태를 파악합니다.

1. `AGENTS.md`
2. `README.md`
3. `docs/mvp-implementation-plan.md`
4. `git status --short`
5. `git log --oneline -5`
6. 백테스트/운영 작업이면 `docs/testing-and-execution-guide.md`, `docs/live-operation-runbook.md`
7. 전략 작업이면 `docs/trading-strategies/`, `backend/config/strategies_config.json`, `backend/features/trading/strategy_validators.py`

도구별 지침:

- Codex: 이 `AGENTS.md`만으로 충분해야 합니다.
- Gemini/Google Antigravity: `GEMINI.md`가 있더라도 얇은 호환 오버레이일 뿐이며, 프로젝트 원칙은 이 파일을 따릅니다.
- `.agents/agents/*.md`: CLI 에이전트 실행 파일이 아니라 LangGraph 런타임이 LLM API 호출 시 주입하는 system prompt template입니다.

## 3. Architecture Rules

1. **LLM is not the orchestrator.**
   - LangGraph와 FastAPI가 워크플로우, 라우팅, 주문 실행을 통제합니다.
   - CLI 에이전트가 ReAct loop나 스킬 연쇄 호출로 매매를 직접 진행하도록 설계하지 않습니다.
   - LLM은 특정 노드 상태를 읽고 structured JSON 판단을 반환하는 1회성 reasoning engine으로만 동작합니다.

2. **Python owns math, state, and safety.**
   - 지표 계산, 포지션 추적, 주문 검증, 리스크 한도, lot size 계산은 Python에서 결정적으로 처리합니다.
   - LLM에게 원시 데이터 계산을 맡기지 않습니다.
   - 주문은 반드시 `validate_order_prices`, `validate_strategy_setup`, risk-percent lot sizing, 일일 손실/횟수 제한 등 guardrail을 통과해야 합니다.

3. **AI-Native vertical slice over over-engineered layers.**
   - 과도한 인터페이스/추상 클래스/레이어 분리를 만들지 않습니다.
   - 특정 기능의 adapter, usecase, guardrail, validator는 가능한 한 `backend/features/<domain>/` 아래 응집시킵니다.
   - cross-cutting Pydantic state/model은 `backend/core/`에 둡니다.
   - 도메인 객체는 복잡한 OOP 메서드보다 직렬화 가능한 Pydantic model과 순수 함수 중심으로 유지합니다.

4. **Strategy registry, not strategy hallucination.**
   - 새 전략은 `docs/trading-strategies/`에 문서화하고 `backend/config/strategies_config.json`에 등록합니다.
   - 주문 가능한 전략은 `backend/features/trading/strategy_validators.py`에 deterministic gate가 있어야 합니다.
   - validator가 없는 전략은 실전/Paper 주문으로 승격하지 않습니다.

## 4. TDD Gate

모든 코드 변경은 아래 순서를 기본값으로 따릅니다.

1. 실패하는 테스트를 먼저 작성하거나 기존 테스트로 실패 조건을 재현합니다.
2. 실패를 확인합니다. 단, 문서/설정 정리처럼 테스트 선행이 의미 없는 경우에는 예외 사유를 최종 응답에 적습니다.
3. 최소 구현으로 테스트를 통과시킵니다.
4. `make test`를 실행합니다.
5. 테스트 명령과 결과를 최종 응답에 남깁니다.

테스트 작성 기준:

- Guardrail, validator, order execution, position tracking, state schema 변경은 반드시 단위 테스트를 추가/수정합니다.
- LangGraph routing이나 LLM node 변경은 mock 기반 테스트를 추가/수정합니다.
- 백테스트 결론은 대화에만 남기지 않고 `backtests/reports/`와 향후 결과 DB에 남깁니다.

## 5. Project Structure

```text
agentic-trader/
├── .agents/                 # LangGraph LLM system prompt templates
│   ├── agents/              # Tech Analyst, Strategist, Chief Trader, Risk Reviewer prompts
│   └── workflows/           # Human/AI workflow notes, not runtime orchestrators
├── backend/
│   ├── core/                # Pydantic state/models, shared exceptions, cross-cutting contracts
│   ├── features/trading/    # Trading vertical slice: indicators, guardrails, MT5 adapter, validators
│   ├── workflows/           # LangGraph graph, nodes, state alias
│   ├── scripts/             # Backtest/history scripts
│   └── main.py              # FastAPI entrypoint
├── docs/                    # Architecture, runbooks, strategy documents
├── tests/                   # Unit/integration tests
├── backtests/               # Ignored generated data/results/reports
└── trading_logs/            # Ignored generated trade reviews/state
```

## 6. Agent Roster

LangGraph 파이프라인은 아래 역할을 순차적으로 호출합니다. 자세한 워크플로우는 `docs/agent-workflow-design.md`를 참고합니다.

1. **Tech Analyst**
   - 입력: Python이 계산한 OHLCV/indicator JSON.
   - 출력: 매수/매도 지시가 아닌 객관적 기술 분석 브리핑.
2. **Strategist**
   - 입력: Tech Analyst 브리핑과 동적으로 주입된 전략 문서.
   - 출력: 현재 장세에 맞는 매매 가설.
3. **Sentiment Analyst (optional)**
   - 입력: 뉴스, 경제 일정, sentiment API.
   - 출력: 거시/심리 리스크 요약.
4. **Chief Trader**
   - 입력: 모든 브리핑, deterministic indicator data, 향후 RAG로 검색된 과거 복기.
   - 출력: 승인/기각 및 SL/TP가 포함된 structured order intent.
5. **Risk Reviewer**
   - 입력: 실제 청산 완료된 거래 결과와 당시 판단 컨텍스트.
   - 출력: 다음 판단에 재사용 가능한 trading journal.

## 7. Memory & Handoff

지식은 세 층으로 나누어 축적합니다.

1. **Permanent rules:** `AGENTS.md`
   - 오래 유지될 프로젝트 철학, 아키텍처 원칙, 금지 사항만 기록합니다.
2. **Current state and roadmap:** `docs/mvp-implementation-plan.md`
   - 완료 phase, 부족한 점, 다음 목표, 보류 이유를 기록합니다.
3. **Operational/experimental memory:** `trading_logs/`, `backtests/reports/`, `backtests/results/`
   - 복기, 백테스트 리포트, 원본 결과, validator 차단 사유를 축적합니다.

작업 종료 시:

- 코드 변경이 있으면 실행한 테스트 명령과 결과를 최종 응답에 남깁니다.
- 새로 알게 된 반복 교훈, 아키텍처 결정, 보류 이유는 `docs/mvp-implementation-plan.md`에 반영합니다.
- 사용자 변경으로 보이는 파일은 되돌리지 말고, 커밋 시 의도한 파일만 선별합니다.

## 8. Mandatory Hook

새 AI 세션이라면 먼저 이 파일의 구조를 이해하십시오. 이어서 `README.md`, `docs/mvp-implementation-plan.md`, 최근 git 상태를 확인하십시오. 범용 CLI 스킬이나 도구별 에이전트 파일을 늘리는 방식으로 문제를 해결하지 말고, Python LangGraph workflow, FastAPI backend, deterministic guardrail, strategy validator를 중심으로 코드를 작성하십시오.
