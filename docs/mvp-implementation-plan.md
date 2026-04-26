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
현재 "아이디어 구체화 및 설계" 단계를 마치고, MVP 구현을 위한 실행 로드맵에 따라 개발을 진행합니다. Codex, Gemini CLI, Google Antigravity 등 어떤 AI 도구를 쓰더라도 root `AGENTS.md`를 공통 SSOT로 삼고, TDD gate와 FastAPI/LangGraph/deterministic guardrail 원칙을 동일하게 적용합니다.

### Phase 0: 기반 세팅 및 뼈대 구축 (완료)
*   [x] 프로젝트 구조 및 아키텍처 설계 (`README.md`, `docs/vision-and-philosophy.md`, `AGENTS.md` 등)
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

### Phase 4: 모의 투자(Paper Trading) 및 Reviewer 에이전트(서기) 완성 (완료)
*   **목표:** 전체 사이클의 통합 및 RAG(검색 증강 생성) 기반 피드백 루프 완성.
*   **작업 내용:**
    *   [x] 완성된 파이프라인을 데모 계좌에 연결하여 실제 시장 가격 데이터 기반으로 앤드투앤드(End-to-End) 매매 사이클 검증.
        *   **완료 세부사항:** `main.py`에 `/api/v1/trade/trigger` 비동기 워크플로우 실행 엔드포인트를 연동하고, 주문 성공 시 열린 포지션을 로컬 JSON에 추적하도록 구현.
    *   [x] **Risk Reviewer** 노드가 포지션 청산 후 매매 결과를 복기하고 일지를 작성하여, 이를 벡터 DB 또는 마크다운 파일로 저장하여 다음 매매 시 `Chief Trader`가 참조할 수 있도록 자가 발전 루프 구현.
        *   **완료 세부사항:** `risk_reviewer_node`는 `closed_trade` 입력이 있을 때만 실행되며, 백테스트/실전/Paper 모두 청산 감지 후 `trading_logs/review_*.md`를 생성. 수동 동기화 엔드포인트 `/api/v1/trade/reconcile` 추가.

### Phase 5: 동적 전략 주입 시스템 및 환경 최적화 (완료)
*   **목표:** 에이전트의 전략 환각을 방지하고 유연한 플러그인식 전략 추가 구조 마련 및 테스트 환경 안정화.
*   **작업 내용:**
    *   [x] 리눅스 환경에서 MT5 의존성 에러 우회 처리 및 테스트 환경 통과. (`tests/test_mt5_connection.py`, `conftest.py` -> `Makefile` 자동화로 대체)
    *   [x] `Tech Analyst` 노드가 시장 상태(Market Regime)를 진단하도록 프롬프트 업데이트.
    *   [x] `backend/config/strategies_config.json` 레지스트리를 구축하여, 장세에 맞는 전략만 `Strategist` 에이전트에게 동적으로 주입하는 파이프라인 구현 완료. (`backend/workflows/nodes.py`)

### Phase 5.5: 백테스트 기반 전략 튜닝 및 검증 강화 (완료)
*   **배경:** `backtests/reports/backtest_BTCUSD_20260426_051456.md` 분석 결과, 1% 룰은 정확히 작동했지만 4회 연속 SL로 손실이 발생했습니다. 문제는 손실 크기가 아니라 LLM이 EMA/ADX/볼린저 조건을 실제 수치로 검산하지 못한 진입 품질이었습니다.
*   **작업 내용:**
    *   [x] `backend/features/trading/indicators.py`를 추가하여 EMA20/EMA50, ATR14, ADX14, Bollinger Bands, RSI14를 백엔드에서 확정적으로 계산하고 각 타임프레임별 indicator snapshot을 생성합니다.
    *   [x] `fetch_data_node`가 최근 OHLCV뿐 아니라 계산된 지표와 snapshot을 `raw_data` 및 `indicator_data`에 주입하도록 변경했습니다. Tech Analyst/Strategist/Chief Trader는 더 이상 지표를 추정하지 않고 계산값을 기반으로 판단해야 합니다.
    *   [x] `backend/features/trading/strategy_validators.py`를 추가했습니다. 주문 직전 MA Crossover는 최근 EMA 교차, 가격 위치, ADX를 검증하고, Bollinger Reversion은 밴드 이탈/반전 캔들/추세 과열 여부를 검증합니다.
    *   [x] ATR14 대비 SL 거리가 너무 좁은 주문을 차단합니다. 기본 최소값은 `1.0 ATR`입니다.
    *   [x] 검증 단계의 기본 백테스트 리스크를 거래당 `0.5%`로 낮추고, `--risk-pct` 및 Makefile `RISK_PCT`로 조정 가능하게 했습니다. 실전/Paper는 `RISK_PER_TRADE_PCT` 환경 변수로 조정합니다.
    *   [x] 백테스트 리포트와 원본 JSON에 차트 기준 타임프레임, 의사결정 타임프레임, 호출 간격, 거래당 리스크 한도를 기록합니다.
*   **검증 결과:**
    *   기존 BTCUSD 손실 리포트의 4개 진입은 새 validator 기준으로 모두 차단됩니다.
        *   Trade #1, #2: SL 거리가 ATR14 대비 너무 좁음.
        *   Trade #3: Bollinger Double Bottom 조건 미충족.
        *   Trade #4: Bollinger Double Top 조건 및 상승 추세 해소 조건 미충족.
    *   관련 단위 테스트: `tests/test_strategy_validators.py`, `tests/test_guardrails.py`.

---

## 🔮 향후 과제 (Future Roadmap)
MVP 단계가 완료된 이후, 진정한 "무인 펀드(Zero-Human Hedge Fund)"로 거듭나기 위해 필요한 고도화 작업들입니다.

### 현재 부족한 부분 요약 (2026-04 기준)
*   **백테스트 속도와 재현성:** 현재 백테스트는 각 Step마다 LangGraph와 LLM을 호출하므로 느리고, 같은 데이터라도 LLM 응답/외부 API 상태에 따라 결과가 흔들릴 수 있습니다. 빠른 반복 실험을 위해 LLM 응답 캐시, deterministic replay, `--from/--to`, `--max-steps` 같은 부분 실행 옵션이 필요합니다.
*   **성과 데이터의 구조화 부족:** 리포트는 사람이 읽기 좋지만, 전략별/기간별/타임프레임별 성과를 누적 비교하기에는 부족합니다. 모든 백테스트 결과를 SQLite 또는 Parquet에 저장하고, `strategy`, `symbol`, `timeframe`, `risk_pct`, `step`, `win_rate`, `profit_factor`, `max_drawdown`, `blocked_reason`을 쿼리할 수 있어야 합니다.
*   **전략 검증은 시작 단계:** MA/Bollinger validator는 생겼지만, 아직 전략별 파라미터 튜닝, walk-forward 검증, out-of-sample 검증, 비용/스프레드/슬리피지 반영이 부족합니다. 현재 결과는 실제 체결 환경보다 낙관적일 수 있습니다.
*   **운영 상태 저장이 취약:** 열린 포지션과 복기 상태가 로컬 JSON 중심이라 재시작/동시 실행/중복 처리에 취약합니다. 운영 단계에서는 SQLite 이상으로 옮겨 원자적 업데이트와 중복 방지를 보장해야 합니다.
*   **세션 간 실행 기억 구조화 부족:** `AGENTS.md`를 Codex/Gemini/Antigravity 공통 SSOT로 정리했지만, 최근 실험 결과와 운영 지표는 아직 Markdown/JSON 중심입니다. 향후 SQLite/Vector DB 기반의 검색 가능한 기억 구조가 필요합니다.
*   **관측 가능성 부족:** 주문 차단 사유, LLM 판단, validator 통과/실패, MT5 응답, reconcile 결과를 한눈에 보는 로그/대시보드/알림 체계가 필요합니다.

### AI 세션 지식 축적 프로토콜 (필수 운영 규칙)
새 AI 세션이 매번 프로젝트를 처음부터 다시 추론하지 않도록, 지식을 다음 3층으로 나누어 축적합니다.

1.  **영구 컨텍스트:** `AGENTS.md`
    *   프로젝트 철학, 아키텍처 원칙, 반드시 지켜야 할 금지 사항을 기록합니다.
    *   새로운 세션은 작업 전 반드시 `AGENTS.md`를 먼저 읽고, FastAPI/LangGraph/Guardrail 중심 구조와 TDD gate를 우선해야 합니다.
    *   `GEMINI.md`는 Google 도구 호환용 얇은 오버레이이며, 프로젝트 원칙은 `AGENTS.md`에만 중복 없이 기록합니다.
    *   바꾸기 어려운 원칙만 기록하고, 실험 로그나 임시 결론은 넣지 않습니다.
2.  **로드맵 및 현재 상태:** `docs/mvp-implementation-plan.md`
    *   완료된 Phase, 아직 부족한 점, 다음 목표를 기록합니다.
    *   큰 기능을 끝냈거나 중요한 방향 전환이 생기면 이 문서를 갱신합니다.
    *   새 세션은 `AGENTS.md` 다음으로 이 문서를 읽어 “지금 어디까지 왔는지”를 파악합니다.
3.  **실험/운영 지식:** `trading_logs/`, `backtests/reports/`, 향후 `backtests/results/index.sqlite`
    *   개별 매매 복기, 백테스트 리포트, validator 차단 사유, 성과 통계는 여기에 축적합니다.
    *   향후에는 마크다운뿐 아니라 SQLite/Vector DB에 구조화하여, Chief Trader와 새 AI 세션이 검색 가능한 기억으로 사용합니다.

새 세션 시작 시 권장 로드 순서:
1.  `AGENTS.md`
2.  `README.md`
3.  `docs/vision-and-philosophy.md`
4.  `docs/mvp-implementation-plan.md`
5.  최근 변경 확인: `git status --short`, `git log --oneline -5`
6.  현재 작업이 테스트 관련이면 `docs/testing-guide.md`
7.  백테스트/운영 관련이면 `docs/execution-guide.md`, `docs/live-operation-runbook.md`
8.  전략 관련이면 `docs/trading-strategies/`, `backend/config/strategies_config.json`, `backend/features/trading/strategy_validators.py`

작업 종료 시 handoff 규칙:
*   코드 변경이 있으면 테스트 명령과 결과를 최종 응답 및 관련 문서에 남깁니다.
*   아키텍처 결정이나 반복될 교훈은 `docs/mvp-implementation-plan.md` 또는 `AGENTS.md`에 반영합니다.
*   백테스트에서 나온 수치/차단 사유/결론은 리포트와 결과 DB에 남기고, 단순 대화 안에만 두지 않습니다.
*   “지금은 보류한 이유”도 기록합니다. 다음 세션이 같은 길을 다시 탐색하지 않게 하기 위함입니다.

### Phase 6: 운영 안정성 및 재시작 복구 강화 (예정)
*   **목표:** 봇을 장시간 켜두는 운영 환경에서 중복 진입, 상태 유실, 청산 미복기를 방지합니다.
*   **계획:**
    *   서버 시작 시 MT5 open positions와 `trading_logs/tracked_positions.json`을 대조하여 추적 상태를 자동 복구합니다.
    *   이미 열린 포지션이 있으면 동일 심볼/전략의 신규 진입을 가드레일에서 차단합니다.
    *   현재 로컬 JSON 기반 상태 저장(`tracked_positions.json`, `reviewed_trades.json`)을 SQLite로 이전하여 원자적 업데이트, 중복 방지, 재시작 복구를 강화합니다.
    *   주문 실패, MT5 연결 끊김, LLM API 실패, reconcile 실패에 대한 재시도/백오프/알림 정책을 정의합니다.
    *   VPS 운영 runbook을 기준으로 데모 계좌에서 1주일 이상 연속 구동 검증을 수행합니다.

### Phase 6.5: 백테스트 엔진 속도, 캐시, 성과 DB 강화 (예정)
*   **목표:** LLM 기반 백테스트를 빠르고 재현 가능하게 만들고, 결과를 누적 분석 가능한 데이터 자산으로 전환합니다.
*   **계획:**
    *   `run_backtest.py`에 `--from`, `--to`, `--max-steps`, `--no-review` 옵션을 추가하여 짧은 디버그 실행과 긴 검증 실행을 분리합니다.
    *   동일한 `(symbol, timeframes, candle_time, raw_data, prompt_version)` 조합의 LLM 응답을 캐시하여 반복 백테스트 비용과 시간을 줄입니다.
    *   LLM 호출 없이 저장된 의사결정 캐시를 재생하는 deterministic replay 모드를 추가합니다.
    *   백테스트 결과 JSON을 SQLite/Parquet 인덱스로 적재하여 전략별 성과를 비교합니다.
    *   validator 차단 사유를 별도로 집계하여 “어떤 조건 때문에 거래가 줄었는지”를 분석합니다.
    *   스프레드, 수수료, 슬리피지, bid/ask 차이를 반영한 현실적인 체결 모델을 추가합니다.

### Phase 6.6: 전략 연구 및 검증 체계 고도화 (예정)
*   **목표:** 단일 백테스트 결과에 과최적화되지 않도록 연구 프로세스를 표준화합니다.
*   **계획:**
    *   월별 walk-forward 검증을 도입하여 in-sample 튜닝과 out-of-sample 검증을 분리합니다.
    *   전략별 파라미터(`min_adx`, `min_sl_atr`, Bollinger tolerance, risk_pct)를 config화하고 grid/random search를 수행합니다.
    *   성과 기준을 단순 PnL이 아니라 Profit Factor, MDD, 기대값, 연속 손실, 거래 빈도, 평균 보유 시간으로 평가합니다.
    *   “거래하지 않아서 피한 손실”과 “차단 때문에 놓친 수익”을 함께 분석하는 blocked-trade audit 리포트를 만듭니다.
    *   최소 표본 수 미달 전략은 실전 후보로 승격하지 않는 기준을 둡니다.

### Phase 7: RAG 자기학습 루프 완성 (예정)
*   **목표:** 청산 후 복기(`Lessons Learned`)가 다음 매매 판단에 실제로 반영되도록 기억 루프를 완성합니다.
*   **계획:**
    *   `Risk Reviewer`가 남긴 매매 일지(`trading_logs/`)를 ChromaDB 등 벡터 데이터베이스에 임베딩.
    *   `Chief Trader`가 과거의 유사한 차트 패턴이나 실패했던 매매 기록을 벡터 검색(RAG)하여 실수를 반복하지 않도록 기억력(Memory)을 부여합니다.
    *   복기 로그에 `symbol`, `timeframe`, `strategy`, `market_regime`, `result`, `pnl`, `exit_reason` 메타데이터를 구조화하여 검색 품질을 높입니다.
    *   RAG가 주입된 경우와 주입되지 않은 경우의 백테스트 결과를 비교하여 실제 개선 여부를 검증합니다.

### Phase 8: Sentiment Analyst 및 외부 컨텍스트 통합 (예정)
*   **목표:** 기술적 분석만으로 설명되지 않는 뉴스/거시 이벤트 리스크를 매매 판단에 반영합니다.
*   **계획:**
    *   `Sentiment Analyst` 노드(뉴스, 공포/탐욕 지수, 주요 경제 일정)를 활성화하고 LangGraph 파이프라인에 정식 편입합니다.
    *   고영향 이벤트 전후에는 신규 진입을 제한하거나 포지션 크기를 축소하는 정책을 백엔드 가드레일과 연결합니다.
    *   외부 API 장애 시에는 Sentiment 노드를 건너뛰되, 해당 결측 상태를 Chief Trader에게 명시적으로 전달합니다.

### Phase 9: 모니터링 대시보드 및 다중 자산 포트폴리오 (예정)
*   **목표:** 운영 상태를 사람이 빠르게 점검할 수 있게 만들고, 단일 종목을 넘어 포트폴리오 단위로 확장합니다.
*   **계획:**
    *   FastAPI 기반의 상태 조회 API와 React/Vue 대시보드를 구축합니다.
    *   현재 포지션, 추적 중인 ticket, 최근 AI 판단, 최근 복기, 일일 손익, 가드레일 차단 내역을 한 화면에서 확인합니다.
    *   Telegram/Discord/Email 알림으로 주문 체결, 청산, 복기 생성, 오류 상태를 전송합니다.
    *   EURUSD 단일 종목에서 벗어나 나스닥(US100), 금(XAUUSD), 비트코인(BTCUSD) 등 다중 자산 병렬 트레이딩 파이프라인 가동.
