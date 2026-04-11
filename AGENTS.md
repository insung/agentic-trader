# AI Session Context & Agents Roster (AGENTS.md)

이 문서는 새로운 AI 세션(Gemini CLI, Claude Code 등)이 시작될 때, 이전 세션까지 합의된 프로젝트의 목표, 아키텍처 철학, 그리고 멀티 에이전트들의 역할을 단번에 파악하기 위한 **핵심 컨텍스트 전달 문서(Brain Dump)**입니다. AI 에이전트는 이 프로젝트를 수정하거나 코드를 짤 때 가장 먼저 이 문서를 읽고 현재의 방향성과 강제 규칙(Mandatory Rules)을 숙지해야 합니다.

---

## 🎯 1. Project Goal & Philosophy (우리의 지향점)
우리는 단순한 트레이딩 봇이 아닌, **"나만의 무인 펀드 회사(Zero-Human Hedge Fund)"**를 구축합니다.
1.  **Philosophy of Paperclip:** 최근 AI 씬의 트렌드인 Paperclip 프레임워크의 철학을 차용하여, AI 에이전트들에게 단순히 기능을 맡기는 것이 아니라 `CEO`, `CTO`, `수석 트레이더(Chief Trader)`, `기술 분석가(Tech Analyst)` 등의 **명확한 직책(Role)과 권한(Harness)**을 부여하여 완벽하게 협업시킵니다. 인간은 이사회(Board)의 역할만 수행합니다.
2.  **Engine of LangGraph:** 트레이딩은 1분 1초가 돈과 직결되는 특수한 도메인이므로, Paperclip 자체 플랫폼(느리고 통제 불가능한 비동기 티켓 시스템)을 엔진으로 쓰지 않습니다. 대신, **100% 확정적(Deterministic)이고 빠르고 비용이 극도로 싼 파이썬의 LangGraph**를 제어 흐름(Control Flow) 엔진으로 채택합니다.
3.  **Safety & Air-gap:** AI는 결코 거래소(MT5)에 직접 주문을 넣을 수 없습니다. 모든 매매 명령은 파이썬 백엔드(FastAPI)가 가로채어(Intercept) 하드코딩된 '절대 안전 규칙(1% 룰, 일일 손실 한도 등)'을 검사한 후 통과된 주문만 실행합니다.

---

## 🏢 2. Project Architecture & Structure (프로젝트 구조)
시스템은 크게 3가지 레이어로 구성됩니다.

1.  **Frontend (None for now):** UI는 당장 고려하지 않으나 향후 확장을 위해 철저히 API 기반으로 분리.
2.  **Orchestrator & Backend (Python FastAPI + LangGraph):**
    *   `backend/api/`: 외부(Webhook)나 내부 스케줄러(Cron)로부터 시장 이벤트를 감지하여 LangGraph 파이프라인을 격발(Trigger)시키는 디스패처.
    *   `backend/core/`: 1일 손실 락(Lock), 매매 횟수 제한, 랏수(Lot) 자동 계산 등 AI의 환각을 물리적으로 막아내는 절대 안전 장치(Guardrails).
    *   `workflows/ (LangGraph)`: 파이썬 코드로 각 에이전트 노드(Node)의 실행 순서를 100% 강제(Hard-coded Routing).
3.  **The AI Brains (`.gemini/agents/*.md`):**
    *   이 폴더의 마크다운 파일들은 CLI 에이전트용 실행 파일이 아닙니다! 파이썬 LangGraph 오케스트레이터가 LLM API(Gemini/Claude)를 호출할 때 주입하는 **'각 에이전트별 시스템 프롬프트(System Prompt Templates)'**입니다.

---

## 👔 3. Agent Roster (조직도 및 에이전트 명단)
LangGraph 파이프라인(Workflow) 내에서 순차적으로 호출되며 협업하는 AI 직원들의 명단입니다. (자세한 워크플로우는 `docs/agent-workflow-design.md` 참조)

1.  **Agent 1 (Tech Analyst / 기술 분석가)**
    *   **입력:** 백엔드가 순수 파이썬(pandas-ta)으로 계산한 차트 데이터 및 보조지표 JSON.
    *   **출력:** 현재 시장의 기술적 추세에 대한 편견 없는 요약 브리핑.
2.  **Agent 2 (Strategist / 전략가)**
    *   **입력:** Tech Analyst의 브리핑 데이터.
    *   **출력:** `docs/trading-strategy.md` 인덱스를 참고하여, 현재 장세에 가장 적합한 매매 가설 도출 (예: "현재는 RSI 역추세 전략이 유효함").
3.  **Agent 3 (Sentiment Analyst / 심리 분석가 - Optional)**
    *   **입력:** 뉴스 API, 공포/탐욕 지수.
    *   **출력:** 거시 경제 및 시장의 센티멘트 요약.
4.  **Agent 4 (Chief Trader / 수석 트레이더 - 최종 결정권자)**
    *   **입력:** 위 1,2,3번 요원들의 모든 브리핑 + **(중요) 과거 매매 일지 DB에서 검색해 온 유사 상황 피드백(RAG)**.
    *   **출력:** 매매 가설에 대한 최종 승인/기각 여부, 그리고 진입 방향과 손절선(SL)이 담긴 확정된 JSON 주문 객체.
5.  **Agent 5 (Risk Reviewer / 리스크 감사관 및 서기)**
    *   **입력:** 포지션 청산 후의 결과 데이터 및 당시 Agent 4의 매매 논리.
    *   **출력:** 무엇을 잘했고 틀렸는지 복기하는 '매매 일지(Trading Journal)'. 이 일지는 벡터 DB에 저장되어 다음 매매 시 Agent 4의 지식(Knowledge)으로 재사용됨(자가 발전).

---
> **미래의 AI 에이전트에게 보내는 메시지 (Mandatory Hook):**
> 당신이 새로운 세션으로 이 프로젝트에 접속했다면, 먼저 이 `AGENTS.md`의 구조를 완벽히 이해하십시오. CLI 스킬을 남용하여 스스로 모든 것을 해결하려 하지 말고, 파이썬 기반의 LangGraph 워크플로우와 FastAPI 백엔드의 안전 규칙을 준수하는 방향으로 코드를 작성하고 아키텍처를 고도화하십시오.
