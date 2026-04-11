# Agentic Trader MVP Implementation Plan (LangGraph Architecture)

이 문서는 "FastAPI + LangGraph" 기반의 확정적 파이썬 오케스트레이터 아키텍처를 실무 코드로 구현하기 위한 단계별 로드맵(MVP)입니다.

## 🏗 프로젝트 디렉토리 구조 (Directory Architecture)

```text
agentic-trader/
├── .gemini/                 # AI 시스템 프롬프트 저장소
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

## 🚀 단계별 구현 계획 (Phased Implementation)

### Phase 1: 코어 백엔드 및 MT5 연동 (Infrastructure & Safety)
가장 먼저, AI 없이 파이썬만으로 MT5와 통신하고 안전장치를 통과하는 "뼈대"를 만듭니다.
1. `requirements.txt` 작성 및 Wine 파이썬 가상환경에 `fastapi`, `MetaTrader5`, `pandas-ta` 설치.
2. `backend/main.py` 생성 후 헬스 체크 엔드포인트 확인.
3. `backend/services/`에 MT5로부터 OHLCV 데이터를 가져와 RSI 등 지표를 붙이는 순수 파이썬 함수 구현.
4. `backend/core/`에 "손익비 검증", "1일 손실 한도 체크" 등 하드코딩된 가드레일(Interceptor) 인터페이스 껍데기 구현.

### Phase 2: LangGraph 파이프라인 배관 공사 (Orchestration)
LLM을 붙이기 전에 파이썬 상태 머신(State Machine)이 1번부터 5번 노드까지 잘 흘러가는지 테스트합니다.
1. `backend/workflows/state.py`에 에이전트들이 주고받을 데이터 구조(예: `dict` 형태의 `AgentState`) 정의.
2. `backend/workflows/nodes.py`에 더미(Dummy) 응답을 뱉는 가짜 에이전트 함수들 작성.
3. `backend/workflows/graph.py`에서 노드들을 연결하고, 조건부 엣지(예: Chief Trader가 승인하면 매매 노드로, 아니면 종료) 라우팅 로직 구현.
4. 디스패처(API 엔드포인트)를 통해 그래프 실행 테스트.

### Phase 3: AI 두뇌 결합 및 프롬프트 엔지니어링 (AI Integration)
더미 노드들을 실제 LLM 호출 로직으로 교체합니다.
1. `.gemini/agents/` 디렉토리에 각 역할(Tech Analyst, Strategist, Chief Trader)에 맞는 시스템 프롬프트 마크다운 파일 작성.
2. `langchain-google-genai` (또는 anthropic) 패키지를 사용하여 노드 함수 내에서 LLM API를 호출하고 응답을 JSON 구조로 파싱(Structured Output)하도록 구현.
3. AI가 뱉어낸 JSON 응답이 Phase 1에서 만든 가드레일(안전장치)을 통과하는지 통합 테스트.

### Phase 4: 모의 트레이딩 (Paper Trading) 및 피드백 루프 완성
1. MT5 데모 계좌와 연동하여 실시간 가격 변화에 따른 앤드투앤드(End-to-End) 매매 사이클 검증.
2. 매매 종료 후 Risk Reviewer 노드가 '매매 일지'를 로컬 DB(또는 마크다운 파일)에 작성하고, 다음 매매 시 이를 RAG로 불러오는 자가 발전 사이클 완비.
