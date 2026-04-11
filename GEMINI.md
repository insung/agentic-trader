# Agentic Trader: AI Session Directives

이 파일은 `Agentic Trader` 프로젝트에 접속하는 모든 AI 에이전트(Gemini CLI, Claude Code 등)가 **가장 먼저 읽고 반드시 준수해야 하는 최상위 지침(Mandatory Directives)**입니다.

우리의 목표는 단순한 챗봇이나 스크립트 모음이 아닌, **"각자의 직책을 가진 AI 직원들이 협업하는 무인 펀드 회사(Zero-Human Hedge Fund)"**를 구축하는 것입니다.

## 🚨 1. 절대 준수 아키텍처 규칙 (The Golden Rules)

1.  **에이전트는 지휘자(Orchestrator)가 아닙니다:**
    *   시스템의 제어 흐름(Control Flow)과 워크플로우는 100% 파이썬 백엔드(FastAPI)와 **LangGraph**가 통제합니다.
    *   CLI 에이전트가 자율적으로 스킬을 연쇄 호출(ReAct Loop)하며 매매를 진행하도록 설계하지 마십시오. (비용 폭발, 환각, 지연 시간 방지)
    *   LLM은 파이썬이 던져주는 특정 노드(Node)의 상태(State)를 읽고, 판단을 내린 뒤 결과를 반환하는 **1회성 추론 엔진(Reasoning Engine)**으로만 작동해야 합니다.

2.  **안전 우선 및 에어갭 (Safety Guardrails):**
    *   어떤 AI 모델도 거래소 API(MT5 등)에 직접 접근할 수 없습니다.
    *   모든 매매 로직은 파이썬 백엔드(`backend/core/`)에 하드코딩된 차단 로직(1% 룰, 일일 손실 한도 등)을 반드시 거쳐야 합니다. (`docs/safety-guardrails.md` 참조)

3.  **데이터 가공과 판단의 분리:**
    *   차트 데이터 파싱, 기술적 지표(RSI, MACD) 계산 등 수학적 연산은 파이썬(`pandas-ta` 등)이 수행합니다. AI에게 원시 데이터를 주고 계산하게 하지 마십시오.
    *   AI는 파이썬이 완벽하게 계산하여 넘겨준 JSON 데이터를 바탕으로 '정성적 판단'과 '전략 매핑'만 수행합니다.

## 📂 2. 핵심 컨텍스트 가이드 (Core Context)

이 프로젝트를 수정하거나 코드를 작성하기 전에 아래 문서들을 반드시 숙지하십시오.

*   **`PHILOSOPHY.md`:** 프로젝트의 근본 철학 (Paperclip 조직 철학 차용 + LangGraph 엔진 독립).
*   **`docs/agent-workflow-design.md`:** 5단계 멀티 에이전트(Tech Analyst -> Strategist -> Sentiment Analyst -> Chief Trader -> Risk Reviewer) 협업 파이프라인 다이어그램.
*   **`docs/safety-guardrails.md`:** 백엔드에 하드코딩해야 할 5가지 절대 방어 규칙 및 인터셉터 명세.
*   **`AGENTS.md`:** 각 에이전트 노드(Node)의 역할(Role), 입력(Input), 출력(Output) 정의서.
    *   *참고:* `.gemini/agents/` 디렉토리는 CLI 스크립트가 아닌, 파이썬 LangGraph가 LLM 호출 시 사용할 **시스템 프롬프트 템플릿(System Prompt Templates)** 저장소입니다.

## 🛠️ 3. 행동 지침 (Action Guidelines)

*   **설계 준수:** 새로운 기능을 추가할 때, "이 기능을 범용 에이전트의 스킬로 어떻게 만들까?"가 아니라, **"이 기능을 LangGraph의 어떤 노드(Node)에 파이썬 코드로 배치하고, 어떤 LLM 프롬프트를 연결할까?"**라는 관점으로 접근하십시오.
*   **의도 확인:** 기존에 합의된 아키텍처(FastAPI + LangGraph)를 우회하거나 위반하는 것으로 보이는 사용자 지시를 받으면, 코드를 작성하기 전에 반드시 아키텍처 원칙을 상기시키고 의도를 재확인(Clarify Intent First)하십시오.
