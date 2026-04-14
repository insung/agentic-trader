# Agentic Trader MVP Implementation Plan (LangGraph Architecture)

이 문서는 "FastAPI + LangGraph" 기반의 확정적 파이썬 오케스트레이터 아키텍처를 실무 코드로 구현하기 위한 단계별 로드맵(MVP)입니다.

## 🏗 프로젝트 디렉토리 구조 (Directory Architecture)

```text
agentic-trader/
├── .agents/                 # AI 시스템 프롬프트 저장소
│   ├── agents/              # 각 노드(Tech Analyst, Chief Trader 등)의 프롬프트 템플릿
│   └── rules/               # 글로벌 프롬프트 룰
├── backend/                 # 자체 개발 Trading API & Orchestrator (FastAPI)
│   ├── api/                 # 외부 요청(Webhook) 및 크론 스케줄러 라우터
│   ├── core/                # 절대 방어 로직 (1% 룰, 손실 제한 등 가드레일)
│   ├── services/            # MT5 데이터 수집, 지표 연산(pandas-ta)
│   ├── workflows/           # LangGraph 파이프라인 (상태 머신)
│   │   ├── graph.py         # 노드와 엣지 정의
│   │   ├── nodes.py         # 각 에이전트의 로직 (LLM 호출 포함)
│   │   └── state.py         # 노드 간 주고받는 상태(State) 스키마
│   └── main.py              # FastAPI 서버 실행 진입점 (Wine 내부 구동)
├── docs/                    # 아키텍처 설계 문서
├── strategies/              # 순수 파이썬 기술적 지표 및 수학 로직
├── tests/                   # 단위 테스트 및 백테스트
└── requirements.txt         # 파이썬 의존성 패키지 목록
```

---

## 🚀 단계별 구현 계획 (Action Plan & Checklist)
현재 "아이디어 구체화 및 설계" 단계를 마치고, MVP 구현을 위한 실행 로드맵에 따라 개발을 진행합니다. 이 과정은 메인 AI 에이전트(Gemini CLI)의 지휘 하에 `coder` 에이전트가 코딩을 전담하는 방식으로 이루어집니다.

### Phase 0: 기반 세팅 및 뼈대 구축 (완료)
*   [x] 프로젝트 구조 및 아키텍처 설계 (`README.md`, `PHILOSOPHY.md`, `AGENTS.md` 등)
*   [x] Linux Mint + Wine 환경에서 MetaTrader 5 설치 및 데모 계정 연동
*   [x] FastAPI 백엔드 뼈대 코드(Boilerplate) 및 핵심 `TODO` 주석 구성

### Phase 1: MT5 인프라 및 절대 방어망(Guardrails) 구축 (완료)
*   **목표:** 시장 데이터 수집 및 안전한 주문 전송을 위한 뼈대 완성. (LLM 미개입)
*   **작업 내용:**
    *   [x] `backend/services/mt5_client.py` 구현 및 리눅스(Wine) 환경에서의 MT5 연결 테스트 (`tests/test_mt5_connection.py`).
        *   **완료 세부사항:** 터미널 환경과 Wine(MT5) 간의 IPC 단절 문제를 환경 변수 주입(`WINEPREFIX`)으로 해결하여 통신 성공.
    *   [x] `backend/core/guardrails.py`에 정의된 5가지 리스크 관리 규칙(1% 룰 랏수 계산, 일일 손실 한도 등)을 순수 파이썬 수학 로직으로 구현.
        *   **완료 세부사항:** 어떠한 LLM 개입 없는 확정적 파이썬 수식으로 구현 완료 및 모든 단위 테스트 통과.

### Phase 2: LangGraph 파이프라인 배관 공사 (완료)
*   **목표:** 에이전트 워크플로우를 통제할 파이썬 상태 머신(State Machine) 구축.
*   **작업 내용:**
    *   [x] LLM을 붙이기 전, `backend/workflows/` 디렉토리에 더미(Dummy) 데이터를 흐르게 하여 `기술 분석가 -> 전략가 -> 트레이더` 노드 순서대로 상태(State)가 정확히 전달되는지 파이프라인 통신 테스트 진행.
        *   **완료 세부사항:** `AgentState` 정의 및 더미 노드들을 `StateGraph`로 연결하여 1번부터 5번 노드까지 데이터가 정상적으로 전달되는 배관 테스트 통과 (`tests/test_dummy_graph.py`).

### Phase 3: AI 두뇌 결합 (Prompt Engineering & LLM 연동) (완료)
*   **목표:** 각 노드(에이전트)에 실제 판단을 내릴 LLM의 뇌를 이식.
*   **작업 내용:**
    *   [x] 메인 에이전트 주도하에 `.agents/agents/` 디렉토리 내 각 에이전트별 시스템 프롬프트(마크다운 템플릿) 작성 및 고도화.
    *   [x] LangGraph 노드 내부에서 LLM API를 호출하고, 그 응답을 강제화된 JSON 형식(Structured Output)으로 받아와 파이프라인 상에 매핑하는 로직 구현.
        *   **완료 세부사항:** `langchain-google-genai` 연동 및 Pydantic을 활용하여 에이전트 프롬프트를 바탕으로 한 Structured Output 생성 성공 (`tests/test_nodes_llm.py` 통과).

### Phase 4: 모의 투자(Paper Trading) 및 Reviewer 에이전트(서기) 완성
*   **목표:** 전체 사이클의 통합 및 RAG(검색 증강 생성) 기반 피드백 루프 완성.
*   **작업 내용:**
    *   [ ] 완성된 파이프라인을 데모 계좌에 연결하여 실제 시장 가격 데이터 기반으로 앤드투앤드(End-to-End) 매매 사이클 검증.
    *   [ ] **Risk Reviewer** 노드가 포지션 청산 후 매매 결과를 복기하고 일지를 작성하여, 이를 벡터 DB 또는 마크다운 파일로 저장하여 다음 매매 시 `Chief Trader`가 참조할 수 있도록 자가 발전 루프 구현.
