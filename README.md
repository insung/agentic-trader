# Agentic Trader

AI(LLM)를 두뇌로 활용하여 해외선물 및 주식을 자율적으로 거래하는 시스템입니다. 현재 초기 브레인스토밍 및 아키텍처 설계 단계에 있습니다.

## 핵심 특징 (Key Features)
*   **LangGraph 기반 오케스트레이션:** 제어 흐름(Control Flow)을 LLM의 자율성에 맡기지 않고, 파이썬 기반의 상태 머신(LangGraph)으로 강제하여 환각을 방지하고 파이프라인의 안정성을 100% 보장합니다.
*   **Fault-Tolerant & Efficient:** LLM API 실패 시 자동 재시도(Tenacity) 및 횡보장 조기 종료(Short-circuit) 라우팅을 통해 안정성과 비용 효율성을 동시에 잡았습니다.
*   **Backend-First Architecture (FastAPI):** 외부 금융 API(MT5) 연동, 보조지표 연산(pandas-ta), 계좌 정보 주입 및 하드코딩된 절대 안전 규칙(Guardrails)은 모두 파이썬 백엔드가 담당하며, AI는 정제된 데이터를 받아 '판단'만 내립니다.
*   **Multi-Agent Reflexion Loop:** 단일 프롬프트가 아닌, 기술 분석가 -> 전략가 -> 트레이더 -> 복기 서기 로 이어지는 다중 페르소나 협업 구조를 통해 사람과 같은 입체적인 매매를 지향합니다.
*   **Knowledge-Based Reasoning:** `docs/trading-strategies/`에 저장된 전문 전략 지식 베이스를 동적으로 주입하여 전략적 일관성을 유지합니다.

## 💻 로컬 환경 세팅 가이드 (Linux/Wine)
MetaTrader 5는 공식적으로 Windows만 지원하므로, Linux 환경에서는 Wine을 사용해야 합니다. 

1. **[MQL5 공식 가이드](https://www.mql5.com/en/articles/625?utm_source=www.metatrader5.com&utm_campaign=download.mt5.linux)** : MetaTrader 5 on Linux 을 참고하여 메타트레이더5를 설치합니다.
2. **계정 로그인 및 자동 매매 허용:** MT5 설치 후 데모 계정으로 로그인하고, `[도구] -> [옵션] -> [전문가 조언자(Expert Advisors)]` 탭에서 **"자동 매매 허용 (Allow algorithmic trading)"**을 반드시 체크해야 합니다.

## 📌 프로젝트 구조 원칙
1.  **로직의 분리:** 복잡한 연산과 통제는 파이썬(FastAPI, LangGraph)이, 시장 상황에 대한 정성적 추론과 전략 매핑은 LLM(Prompt)이 담당합니다.
2.  **`.agents/` 의 역할 변화:** 더 이상 CLI 에이전트의 실행 스크립트가 아닌, 파이썬 오케스트레이터가 LLM API를 호출할 때 주입할 **'시스템 프롬프트 템플릿(System Prompt Templates)'** 저장소로 활용됩니다.

## 🗺️ 향후 실행 로드맵 (Action Plan)
프로젝트의 상세한 단계별 실행 로드맵 및 MVP 구현 체크리스트는 별도의 문서로 분리하여 관리합니다.
현재 `Phase 1`이 성공적으로 완료되었으며, 남은 구현 계획은 아래 문서를 참고하십시오.

👉 **[docs/mvp-implementation-plan.md](docs/mvp-implementation-plan.md) 참조**
