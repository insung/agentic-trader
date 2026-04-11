# Agent Workflow Design (LangGraph Pipeline)

이 문서는 Agentic Trader의 핵심 두뇌 역할을 하는 멀티 에이전트 아키텍처를 정의합니다. 자율형 CLI 에이전트의 불확실성을 배제하고, **FastAPI + LangGraph** 기반의 확정적(Deterministic) 파이썬 상태 머신(State Machine)으로 제어 흐름을 강제합니다.

## 0. 아키텍처 다이어그램 (LangGraph Nodes & Edges)

파이썬 오케스트레이터가 그래프의 각 노드(Node)를 순차적으로 실행하며, LLM API를 호출하여 상태(State)를 업데이트합니다.

```mermaid
flowchart TD
    %% 트리거 소스
    subgraph Triggers [1. Python Dispatcher]
        W[Webhook / API Call] --> D{Dispatcher}
        M[Price Alert Scanner] --> D
        C[Cron Scheduler] --> D
    end

    %% LangGraph 파이프라인
    subgraph LangGraph [2. LangGraph State Machine]
        D -->|Start Graph| N_Data[Node 1: Fetch Data\n(Python Pandas)]
        
        N_Data -->|Raw JSON| N_Tech(Node 2: Tech Analyst\nLLM Call)
        
        N_Tech -->|Tech Summary| N_Strat(Node 3: Strategist\nLLM Call)
        
        N_Strat -->|Hypothesis| N_Sent(Node 4: Sentiment Analyst\nLLM Call - Optional)
        
        DB[(Knowledge Base\nVector DB / JSON)] -.->|Retrieve Past Logs| N_Trader
        N_Strat --> N_Trader
        N_Sent --> N_Trader(Node 5: Chief Trader\nLLM Call)
        
        N_Trader -->|Trade Signal| Guard{Python Guardrails\nRisk Check}
        Guard -->|Reject| End((End))
        
        Guard -->|Pass| Exec[Execute Order\n(MT5 API)]
        
        Exec -->|Result| N_Review(Node 6: Risk Reviewer\nLLM Call)
        N_Review -->|Save Journal| DB
        N_Review --> End
    end

    classDef python fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef llm fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef guard fill:#ffebee,stroke:#c62828,stroke-width:2px;
    
    class N_Data,Guard,Exec,D,W,M,C python;
    class N_Tech,N_Strat,N_Sent,N_Trader,N_Review llm;
```

## 1. 트리거링 시스템 (Python Dispatcher)
백그라운드에서 도는 파이썬 스크립트나 FastAPI 엔드포인트가 시장 이벤트를 감지하여 LangGraph 파이프라인(Workflow)을 격발시킵니다.
*   크론 스케줄러: 1시간봉, 4시간봉 완성 시점.
*   웹훅/API: 사용자의 수동 분석 요청.

## 2. 그래프 노드 정의 (LangGraph Nodes)

각 노드는 파이썬 함수이며, 내부에 프롬프트를 조립하여 LLM API(Gemini/Claude)를 호출하는 로직이 들어있습니다.

### Node 1: Fetch Data (Pure Python)
*   **동작:** MT5 API에서 캔들 데이터를 가져와 `pandas-ta`로 RSI, MACD 등을 계산하여 JSON 형태로 State 딕셔너리에 저장합니다. LLM을 쓰지 않습니다.

### Node 2: Tech Analyst (LLM)
*   **동작:** Node 1에서 만든 데이터 JSON과 미리 정의된 `[기술 분석가 프롬프트]`를 LLM API로 보냅니다. 반환받은 "현재 기술적 추세 요약 텍스트"를 State에 저장합니다.

### Node 3: Strategist (LLM)
*   **동작:** Node 2의 요약 텍스트와 `docs/trading-strategy.md`의 기초 전략 리스트를 LLM API에 넣어, "어떤 전략을 쓸 것인지" 매매 가설을 세웁니다.

### Node 4: Sentiment Analyst (LLM - Optional)
*   **동작:** 뉴스 API 등의 텍스트를 읽고 거시적 분위기를 요약합니다.

### Node 5: Chief Trader (LLM + RAG)
*   **동작:** 앞선 노드들의 모든 요약 텍스트와, 벡터 DB에서 검색해 온 과거의 '매매 일지(유사 상황)'를 묶어 최종 프롬프트를 만듭니다. LLM API는 `{"action": "BUY", "sl": 60000}` 형태의 확정적인 JSON만 반환하도록 강제(Structured Output)됩니다.

### Node 6: Risk Reviewer (LLM)
*   **동작:** 매매가 청산된 후, 당시 Node 5가 내렸던 판단과 실제 결과를 LLM에게 주어 '반성문(Trading Journal)'을 작성하게 하고 이를 DB에 저장합니다.

## 3. LangGraph의 압도적 장점
*   **Zero Hallucination Routing:** 에이전트가 "다음엔 뭘 할까?" 고민하지 않으므로 실행 순서가 100% 보장됩니다.
*   **비용 극소화:** 채팅 히스토리를 통째로 넘기지 않고, 파이썬이 딱 필요한 요약 텍스트만 프롬프트에 주입하여 1회성 API 호출로 끝내므로 토큰이 획기적으로 절약됩니다.
