# AI Trading System References

이 문서는 AI(특히 LLM) 기반의 자동매매 시스템을 설계할 때 참고할 수 있는 훌륭한 오픈소스 프로젝트와 아키텍처 레퍼런스를 정리한 문서입니다. 프로젝트의 방향성을 구체화하는 데 사용됩니다.

## 1. LangGraph 및 Multi-Agent 오픈소스 프로젝트

최신 트렌드인 LangGraph 기반의 확정적 제어 흐름(State Machine)과 멀티 에이전트 구조를 훌륭하게 구현한 공개(Public) GitHub 리포지토리들입니다.

*   **[aianytime/trading-agent-langgraph](https://github.com/aianytime/trading-agent-langgraph)**
    *   **특징:** LangGraph를 사용하여 무려 12개의 활성 에이전트(시장, 소셜, 뉴스, 펀더멘털 분석 등)를 조율하는 종합 트레이딩 앱입니다.
    *   **구조 참고점:** '강세장(Bull) vs 약세장(Bear) 논쟁 노드'와 공격적/보수적/중립적 페르소나로 나뉜 리스크 팀이 투표를 통해 의사결정을 내리는 파이프라인이 훌륭한 레퍼런스입니다.
*   **[mubinshaikh/multi-agent-hedge-fund](https://github.com/mubinshaikh/multi-agent-hedge-fund)**
    *   **특징:** 헤지펀드의 분석 프로세스를 모방한 LangGraph 시뮬레이션 프로젝트입니다.
    *   **구조 참고점:** 포트폴리오 매니저(PM) 에이전트가 펀더멘털, 기술, 심리 분석가 에이전트들에게 작업을 '위임(Delegate)'하고 상태(State)를 주고받는 코드 골격을 참고하기 좋습니다.
*   **[lenaar/financial-ai-agent](https://github.com/lenaar/financial-ai-agent)**
    *   **특징:** 재무 분석 워크플로우를 자동화하고 CSV 데이터를 처리하는 금융 특화 AI 에이전트입니다.
*   **[virattt/langgraph-financial-agent.ipynb](https://gist.github.com/virattt/ba0b660cdcaf4161ca1e6e5d8b5de4f8)**
    *   **특징:** Polygon API를 사용하여 주가 데이터를 가져오고 재무 에이전트를 구축하는 LangGraph 입문용 쥬피터 노트북 코드입니다. 노드(Node) 설계의 가장 기초를 잡기 좋습니다.

> **💡 참고: 조직형 에이전트 프레임워크 (Paperclip & OpenClaw 트렌드)**
> 최근 AI 씬에서는 단일 에이전트를 넘어, 에이전트들에게 '직책'을 부여하여 협업시키는 조직형 아키텍처가 대세입니다.
> 
> *   **[paperclipai/paperclip](https://github.com/paperclipai/paperclip):** "Zero-human company(무인 회사)" 구축 프레임워크입니다. AI 에이전트들을 CEO, CTO, CBO(비즈니스 책임자), 엔지니어 등의 직책으로 조직도(Org Chart)에 배치합니다. 인간은 이사회(Board) 역할을 하여 목표와 예산만 승인하고, CEO 에이전트가 하위 에이전트들에게 티켓(Ticket) 기반으로 업무를 위임(Delegate)하는 멀티 에이전트 협업의 끝판왕 격 프로젝트입니다.
> *   **[openclaw/openclaw](https://github.com/openclaw/openclaw):** 로컬 환경에서 돌아가는 에이전트 실행 런타임(OS)으로, 메신저와 연결되어 실제 행동(Execution)을 수행하는 데 특화되어 있습니다. Paperclip 같은 관리 프레임워크 안에서 하나의 '직원(Employee)'으로 고용되어 동작할 수 있습니다.
> *   **우리 시스템에의 적용:** Paperclip의 '회사 조직도' 개념은 우리가 설계한 `docs/agent-workflow-design.md`의 멀티 에이전트 파이프라인(`Chief Trader`, `Tech Analyst` 등)과 철학적으로 완벽히 일치합니다. 우리는 FastAPI와 LangGraph를 결합하여, Paperclip처럼 각 에이전트가 명확한 직책(Role)과 권한을 갖고 협업하는 **"나만의 무인 트레이딩 펀드 회사"**를 구축하게 됩니다.

## 2. 알고리즘 트레이딩 코어 프레임워크

AI 에이전트가 매매 로직을 판단하더라도, 실제 백엔드에서 데이터를 수집하고 백테스트를 돌릴 때 참고할 수 있는 파이썬 생태계의 표준 오픈소스들입니다.

*   **[freqtrade](https://github.com/freqtrade/freqtrade)**
    *   가장 널리 쓰이는 파이썬 기반 오픈소스 암호화폐 트레이딩 봇입니다. 데이터 다운로드, 전략 작성, 백테스팅 파이프라인 구조를 잡을 때 교과서적인 역할을 합니다.
*   **[backtrader](https://github.com/mementum/backtrader)**
    *   역사가 깊고 안정적인 파이썬 백테스팅 프레임워크입니다. AI가 도출한 전략이나 로직을 과거 데이터로 검증할 때 코어 엔진으로 참고하기 좋습니다.
*   **[pandas-ta](https://github.com/twopirllc/pandas-ta)**
    *   트레이딩뷰를 쓰지 않고 파이썬 내부에서 기술적 지표를 계산할 때 필수적인 라이브러리입니다. 130개 이상의 기술적 지표(RSI, MACD, Bollinger Bands 등)를 빠르고 쉽게 계산할 수 있습니다.

## 3. 핵심 아키텍처 인사이트 (Research Summary)

*   **LLM의 한계와 타임프레임:** LLM 모델은 추론하는 데 시간이 걸립니다(수 초 ~ 수십 초). 따라서 초 단위의 스캘핑(HFT)은 불가능에 가깝고, 최소 15분봉 이상의 **스윙 트레이딩(Swing Trading)**이나 **데이 트레이딩**에 적합합니다.
*   **LangGraph 기반 오케스트레이션:** 자유도 높은 범용 CLI 에이전트에 통제권을 주면 토큰 폭발과 환각(Hallucination) 위험이 큽니다. 파이썬 기반의 LangGraph로 파이프라인을 100% 강제(Hard-coded routing)하는 것이 기관급 트레이딩 봇의 최신 트렌드입니다.
*   **Multi-Agent의 필요성:** 단일 프롬프트에 모든 차트 데이터를 밀어 넣고 "살까 팔까?"를 묻는 방식은 성공률이 매우 낮습니다. 역할을 쪼개는 구조(데이터 요약 에이전트 -> 전략가 에이전트 -> 리스크 검증 에이전트)가 대세입니다.
