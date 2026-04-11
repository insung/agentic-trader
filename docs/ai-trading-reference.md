# AI Trading System References

이 문서는 AI(특히 LLM) 기반의 자동매매 시스템을 설계할 때 참고할 수 있는 훌륭한 오픈소스 프로젝트와 아키텍처 레퍼런스를 정리한 문서입니다. 프로젝트의 방향성을 구체화하는 데 사용됩니다.

## 1. LLM 기반 트레이딩 오픈소스 프로젝트

최신 LLM을 활용한 트레이딩 프로젝트들은 주로 '멀티 에이전트(Multi-Agent)' 구조를 채택하여 LLM의 한계를 극복하고 있습니다.

*   **[TradingAgents](https://github.com/TauricResearch/TradingAgents)**
    *   **특징:** LangGraph를 기반으로 한 기관급 시뮬레이션 프레임워크입니다.
    *   **구조 참고점:** 펀더멘털 분석가, 센티멘탈 분석가, 기술적 분석가 등 여러 AI 에이전트가 각자의 분석을 내놓고, 이를 토론(Debate)하여 최종 매매 결정을 내리는 구조가 매우 인상적입니다.
*   **[LLM-TradeBot](https://github.com/EthanAlgoX/LLM-TradeBot)**
    *   **특징:** 적대적 결정 프레임워크(Adversarial Decision Framework)를 사용하는 암호화폐 봇입니다.
    *   **구조 참고점:** 바이낸스 퓨처스와 연동되어 있으며, AI가 서로의 논리를 반박하며 검증하는 구조를 통해 환각(Hallucination)에 의한 잘못된 매매를 방지합니다.
*   **[LLM_trader](https://github.com/qrak/LLM_trader)**
    *   **특징:** ChromaDB 같은 벡터 데이터베이스를 활용한 '의미론적 추론(Semantic Reasoning)' 봇입니다.
    *   **구조 참고점:** 과거의 매매 기록과 결과를 벡터 DB에 저장하고(RAG), 현재 시장 상황과 가장 유사했던 과거의 기억을 꺼내와 AI가 스스로 피드백하며 진화하는 구조를 갖추고 있습니다.

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
*   **비용 문제 (API Cost):** 이벤트마다 GPT-4나 Claude 3.5 Sonnet을 호출하면 하루 API 비용이 10~50달러에 달할 수 있습니다. 무의미한 호출을 줄이는 구조(트리거 설계)가 필수적입니다.
*   **Multi-Agent의 필요성:** 단일 프롬프트에 모든 차트 데이터를 밀어 넣고 "살까 팔까?"를 묻는 방식은 성공률이 매우 낮습니다. 역할을 쪼개는 구조(데이터 요약 에이전트 -> 전략가 에이전트 -> 리스크 검증 에이전트)가 대세입니다.
