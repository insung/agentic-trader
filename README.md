# Agentic Trader

AI(LLM)를 두뇌로 활용하여 해외선물 및 주식을 자율적으로 거래하는 시스템입니다. 현재 초기 브레인스토밍 및 아키텍처 설계 단계에 있습니다.

## 핵심 특징 (Key Features)
*   **LangGraph 기반 오케스트레이션:** 제어 흐름(Control Flow)을 LLM의 자율성에 맡기지 않고, 파이썬 기반의 상태 머신(LangGraph)으로 강제하여 환각을 방지하고 파이프라인의 안정성을 100% 보장합니다.
*   **Backend-First Architecture (FastAPI):** 외부 금융 API(MT5) 연동, 보조지표 연산(pandas-ta), 하드코딩된 절대 안전 규칙(Guardrails)은 모두 파이썬 백엔드가 담당하며, AI는 정제된 데이터를 받아 '판단'만 내립니다.
*   **Multi-Agent Reflexion Loop:** 단일 프롬프트가 아닌, 기술 분석가 -> 전략가 -> 트레이더 -> 복기 서기 로 이어지는 다중 페르소나 협업 구조를 통해 사람과 같은 입체적인 매매를 지향합니다.
*   **Low-Cost & Stateless:** 대화 컨텍스트가 무한히 쌓이는 CLI 에이전트 방식 대신, 각 단계(Node)마다 필요한 정보만 JSON으로 캡슐화하여 LLM API를 1회성(Stateless)으로 호출하므로 토큰 비용이 극도로 저렴합니다.

## 📌 프로젝트 구조 원칙
1.  **로직의 분리:** 복잡한 연산과 통제는 파이썬(FastAPI, LangGraph)이, 시장 상황에 대한 정성적 추론과 전략 매핑은 LLM(Prompt)이 담당합니다.
2.  **`.gemini/` 의 역할 변화:** 더 이상 CLI 에이전트의 실행 스크립트가 아닌, 파이썬 오케스트레이터가 LLM API를 호출할 때 주입할 **'시스템 프롬프트 템플릿(System Prompt Templates)'** 저장소로 활용됩니다.

## 향후 계획 (Implementation Plan)
현재 "아이디어 구체화 및 설계" 단계를 마치고, 실제 코드를 작성하는 구현 단계로 진입합니다.

1.  **파이썬 가상환경 및 패키지 세팅:** `fastapi`, `langgraph`, `pandas-ta`, `MetaTrader5` 등 핵심 라이브러리 설치 환경(`requirements.txt`) 구성.
2.  **FastAPI 백엔드 뼈대(Boilerplate) 구축:** `backend/` 디렉토리에 서버 엔드포인트를 띄우고, 5대 절대 방어 규칙(Guardrails) 중 일부를 빈 함수(Dummy) 형태로 우선 구현.
3.  **LangGraph 'Hello World' 워크플로우 작성:** 복잡한 프롬프트 없이 `분석가 -> 전략가 -> 트레이더` 노드로 이어지는 파이썬 상태 머신(State Machine) 배관 통신 테스트 진행.
4.  **MT5 API 연동 및 시스템 통합:** 실제 데모 계좌와 연결하여 파이프라인 전체 사이클 테스트 및 프롬프트 고도화.
