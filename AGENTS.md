# Agentic Trader AI Project Rules

이 파일은 Codex, Gemini CLI, Google Antigravity 등 이 저장소에 접속하는 모든 AI 세션의 **공통 진입점이자 프로젝트 규칙 SSOT**입니다. 도구별 설정 파일이 있더라도 프로젝트 원칙은 이 파일과 `.agents/rules/project-rule.md`, `.agents/rules/document-rule.md`를 우선합니다.

## 1. Mandatory Rule Files

작업 전 반드시 아래 파일을 읽고 따릅니다.

1. `AGENTS.md`
2. `.agents/rules/project-rule.md`
3. `.agents/rules/document-rule.md`

`AGENTS.md`는 프로젝트 철학과 세션 운영 규칙을 정의합니다. 실제 구현 구조, vertical slice, Clean Architecture 의존성 방향, DTO/API/DB 배치 규칙은 `.agents/rules/project-rule.md`를 따릅니다.
문서 생성, 이동, 로드맵 번호 체계, 문서 색인 갱신 규칙은 `.agents/rules/document-rule.md`를 따릅니다.

## 2. Project Goal

우리는 단순한 트레이딩 봇이 아니라 **"나만의 무인 펀드 회사(Zero-Human Hedge Fund)"**를 구축합니다.

1. **Role-based AI Organization:** Tech Analyst, Strategist, Chief Trader, Risk Reviewer처럼 명확한 직책과 책임을 가진 AI 직원들이 협업합니다. 인간은 이사회(Board) 역할을 합니다.
2. **LangGraph Engine:** 매매 제어 흐름은 느리고 비결정적인 티켓/스킬 체계가 아니라 Python LangGraph 상태 머신이 통제합니다.
3. **Safety & Air-gap:** 어떤 AI도 MT5/거래소에 직접 주문을 넣을 수 없습니다. 모든 주문은 FastAPI/Python 백엔드의 hard-coded guardrail을 통과해야 합니다.
4. **Deterministic Strategy Gates:** LLM은 전략을 제안할 수 있지만, 주문 직전에는 Python validator가 EMA/ADX/ATR/Bollinger/RSI 등 계산값으로 전략 조건을 다시 검산해야 합니다.

## 3. Mandatory Session Startup

새 AI 세션은 작업 전 반드시 아래 순서로 읽고 현재 상태를 파악합니다.

1. `AGENTS.md`
2. `.agents/rules/project-rule.md`
3. `.agents/rules/document-rule.md`
4. `README.md`
5. `docs/architecture/vision-and-philosophy.md`
6. `docs/roadmap/001-mvp-roadmap.md`
7. `git status --short`
8. `git log --oneline -5`
9. 테스트 작업이면 `docs/guides/testing-guide.md`
10. 백테스트/운영 작업이면 `docs/guides/backtesting-guide.md`, `docs/guides/execution-guide.md`, `docs/guides/live-operation-runbook.md`
11. 전략 작업이면 `docs/trading-strategies/`, `backend/config/strategies_config.json`, `backend/features/trading/strategy_validators.py`
12. 문서 작업이면 `docs/README.md`의 placement table

도구별 지침:

- Codex: 이 `AGENTS.md`, `.agents/rules/project-rule.md`, `.agents/rules/document-rule.md`만으로 충분해야 합니다.
- Gemini/Google Antigravity: `GEMINI.md`나 도구별 설정 파일이 있더라도 얇은 호환 오버레이일 뿐이며, 프로젝트 원칙은 `AGENTS.md`, `.agents/rules/project-rule.md`, `.agents/rules/document-rule.md`를 따릅니다.
- `.agents/agents/*.md`: CLI 에이전트 실행 파일이 아니라 LangGraph 런타임이 LLM API 호출 시 주입하는 system prompt template입니다.
- `.agents/workflows/*.md`: 사람과 AI 세션을 돕는 운영 노트이며, 런타임 오케스트레이터가 아닙니다.

## 4. Architecture Rules

1. **LLM is not the orchestrator.**
   - LangGraph와 FastAPI가 워크플로우, 라우팅, 주문 실행을 통제합니다.
   - CLI 에이전트가 ReAct loop나 스킬 연쇄 호출로 매매를 직접 진행하도록 설계하지 않습니다.
   - LLM은 특정 노드 상태를 읽고 structured JSON 판단을 반환하는 1회성 reasoning engine으로만 동작합니다.

2. **Python owns math, state, and safety.**
   - 지표 계산, 포지션 추적, 주문 검증, 리스크 한도, lot size 계산은 Python에서 결정적으로 처리합니다.
   - LLM에게 원시 데이터 계산을 맡기지 않습니다.
   - 주문은 반드시 `validate_order_prices`, `validate_strategy_setup`, risk-percent lot sizing, 일일 손실/횟수 제한 등 guardrail을 통과해야 합니다.

3. **Vertical slice with Clean Architecture dependency direction.**
   - 기능 코드는 기본적으로 `backend/features/<domain>/` 아래에 응집시킵니다.
   - 전통적인 전역 `domain/use_cases/adapters/infrastructure` 구조를 강제하지 않습니다.
   - 안쪽 정책 로직은 FastAPI, SQLite, MT5, LLM에 의존하지 않습니다.
   - 세부 구조 규칙은 `.agents/rules/project-rule.md`를 따릅니다.

4. **Strategy registry, not strategy hallucination.**
   - 새 전략은 `docs/trading-strategies/`에 문서화하고 `backend/config/strategies_config.json`에 등록합니다.
   - 주문 가능한 전략은 `backend/features/trading/strategy_validators.py`에 deterministic gate가 있어야 합니다.
   - validator가 없는 전략은 실전/Paper 주문으로 승격하지 않습니다.

## 5. TDD Gate

모든 코드 변경은 아래 순서를 기본값으로 따릅니다.

1. 실패하는 테스트를 먼저 작성하거나 기존 테스트로 실패 조건을 재현합니다.
2. 실패를 확인합니다. 단, 문서/설정 정리처럼 테스트 선행이 의미 없는 경우에는 예외 사유를 최종 응답에 적습니다.
3. 최소 구현으로 테스트를 통과시킵니다.
4. `make test`를 실행합니다.
5. 테스트 명령과 결과를 최종 응답에 남깁니다.

테스트 작성 기준:

- Guardrail, validator, order execution, position tracking, persistence, state schema 변경은 반드시 단위 테스트를 추가/수정합니다.
- API router 변경은 endpoint response와 error path 테스트를 추가/수정합니다.
- LangGraph routing이나 LLM node 변경은 mock 기반 테스트를 추가/수정합니다.
- 백테스트 결론은 대화에만 남기지 않고 `backtests/reports/`와 향후 결과 DB에 남깁니다.

## 6. Agent Roster

LangGraph 파이프라인은 아래 역할을 순차적으로 호출합니다. 자세한 워크플로우는 `docs/architecture/agent-workflow-design.md`를 참고합니다.

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

1. **Permanent rules:** `AGENTS.md`, `.agents/rules/project-rule.md`, `.agents/rules/document-rule.md`
   - 오래 유지될 프로젝트 철학, 아키텍처 원칙, 금지 사항만 기록합니다.
2. **Current state and roadmap:** `docs/roadmap/001-mvp-roadmap.md`
   - 완료 phase, 부족한 점, 다음 목표, 보류 이유를 기록합니다.
3. **Operational/experimental memory:** `trading_logs/`, `backtests/reports/`, `backtests/results/`
   - 복기, 백테스트 리포트, 원본 결과, validator 차단 사유를 축적합니다.

작업 종료 시:

- 코드 변경이 있으면 실행한 테스트 명령과 결과를 최종 응답에 남깁니다.
- 새로 알게 된 반복 교훈, 아키텍처 결정, 보류 이유는 `docs/roadmap/001-mvp-roadmap.md` 또는 적절한 `docs/roadmap/00x-*.md`에 반영합니다.
- 영구 규칙이 바뀌면 `AGENTS.md` 또는 `.agents/rules/project-rule.md`에 반영합니다.
- 문서 배치 규칙이 바뀌면 `.agents/rules/document-rule.md`와 `docs/README.md`에 반영합니다.
- 사용자 변경으로 보이는 파일은 되돌리지 말고, 커밋 시 의도한 파일만 선별합니다.

## 8. Mandatory Hook

새 AI 세션이라면 먼저 이 파일과 `.agents/rules/project-rule.md`, `.agents/rules/document-rule.md`의 구조를 이해하십시오. 이어서 `README.md`, `docs/roadmap/001-mvp-roadmap.md`, 최근 git 상태를 확인하십시오.

범용 CLI 스킬이나 도구별 에이전트 파일을 늘리는 방식으로 문제를 해결하지 말고, Python LangGraph workflow, FastAPI backend, deterministic guardrail, strategy validator, vertical slice 구조를 중심으로 코드를 작성하십시오.
