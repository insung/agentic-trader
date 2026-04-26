# Agentic Trader

AI(LLM)를 두뇌로 활용하여 해외선물 및 주식을 자율적으로 거래하는 시스템입니다. LangGraph 기반 멀티 에이전트가 매매 판단을 내리고, Python 백엔드가 주문 실행, 포지션 추적, 리스크 가드레일, 청산 후 복기를 담당합니다.

## 핵심 특징 (Key Features)
*   **LangGraph 기반 오케스트레이션:** 제어 흐름(Control Flow)을 LLM의 자율성에 맡기지 않고, 파이썬 기반의 상태 머신(LangGraph)으로 강제하여 환각을 방지하고 파이프라인의 안정성을 100% 보장합니다.
*   **Fault-Tolerant & Efficient:** LLM API 실패 시 자동 재시도(Tenacity) 및 횡보장 조기 종료(Short-circuit) 라우팅을 통해 안정성과 비용 효율성을 동시에 잡았습니다.
*   **Backend-First Architecture (FastAPI):** 외부 금융 API(MT5) 연동, 보조지표 연산(pandas-ta), 계좌 정보 주입 및 하드코딩된 절대 안전 규칙(Guardrails)은 모두 파이썬 백엔드가 담당하며, AI는 정제된 데이터를 받아 '판단'만 내립니다.
*   **Deterministic Strategy Gates:** LLM이 고른 전략은 주문 직전 Python validator가 다시 검산합니다. EMA/ADX 교차, 볼린저 반전, ATR 기반 최소 SL 거리, 최소 손익비가 실제 계산값으로 확인되지 않으면 주문은 차단됩니다.
*   **Post-Close Reflexion Loop:** 단일 프롬프트가 아닌, 기술 분석가 -> 전략가 -> 트레이더 -> 청산 후 복기 서기로 이어지는 다중 페르소나 협업 구조를 사용합니다. `Lessons Learned`는 주문 직후가 아니라 포지션이 TP/SL/종료 조건으로 닫힌 뒤 생성됩니다.
*   **Knowledge-Based Reasoning:** `docs/trading-strategies/`에 저장된 전문 전략 지식 베이스를 동적으로 주입하여 전략적 일관성을 유지합니다.
*   **Position-Based Agentic Backtesting:** 실제 에이전트 파이프라인을 그대로 사용하되, 진입 후 열린 포지션을 유지하다가 청산 시점에 PnL과 복기를 기록합니다.

프로젝트의 장기 방향과 설계 철학은 [docs/vision-and-philosophy.md](docs/vision-and-philosophy.md)를 참고하십시오.

## Quick Start (개발 및 테스트)

이 프로젝트는 터미널 명령어를 간소화하기 위해 `Makefile`을 제공합니다.

1.  **의존성 설치:**
    ```bash
    make install
    ```
2.  **안전한 테스트 실행 (MT5 미연결 상태에서도 동작):**
    ```bash
    make test
    ```
3.  **FastAPI 서버 실행:**
    ```bash
    make run
    # MT5 연동이 필요한 경우:
    make run-wine
    ```
4.  **백테스팅 실행 (과거 데이터 기반 전략 검증):**
    ```bash
    make backtest-fetch SYMBOL=EURUSD DAYS=30
    make backtest-run DATA=backtests/data/EURUSD_20250101-20250131_M15.csv,backtests/data/EURUSD_20250101-20250131_M30.csv SYMBOL=EURUSD TIMEFRAMES=M15,M30 RISK_PCT=0.005
    ```
5.  **수동으로 AI 매매 파이프라인 1사이클 트리거 (서버 구동 중):**
    ```bash
    make trigger SYMBOL=EURUSD TIMEFRAMES=M15,M30 MODE=paper
    # 또는 대화형 운영 도구:
    make cli
    ```
6.  **추적 중인 포지션 청산 여부 수동 동기화:**
    ```bash
    make reconcile
    ```

자세한 테스트 절차는 [docs/testing-guide.md](docs/testing-guide.md), 실행/백테스트 절차는 [docs/execution-guide.md](docs/execution-guide.md)를 참고하십시오.

## 💻 로컬 환경 세팅 가이드 (Linux/Wine)
MetaTrader 5는 공식적으로 Windows만 지원하므로, Linux 환경에서는 Wine을 사용해야 합니다. 

1. **[MQL5 공식 가이드](https://www.mql5.com/en/articles/625?utm_source=www.metatrader5.com&utm_campaign=download.mt5.linux)** : MetaTrader 5 on Linux 을 참고하여 메타트레이더5를 설치합니다.
2. **계정 로그인 및 자동 매매 허용:** MT5 설치 후 데모 계정으로 로그인하고, `[도구] -> [옵션] -> [전문가 조언자(Expert Advisors)]` 탭에서 **"자동 매매 허용 (Allow algorithmic trading)"**을 반드시 체크해야 합니다.

## 📌 프로젝트 구조 원칙
1.  **로직의 분리:** 복잡한 연산과 통제는 파이썬(FastAPI, LangGraph)이, 시장 상황에 대한 정성적 추론과 전략 매핑은 LLM(Prompt)이 담당합니다.
2.  **`.agents/` 의 역할 변화:** 더 이상 CLI 에이전트의 실행 스크립트가 아닌, 파이썬 오케스트레이터가 LLM API를 호출할 때 주입할 **'시스템 프롬프트 템플릿(System Prompt Templates)'** 저장소로 활용됩니다.
3.  **복기 타이밍:** `trading_logs/review_*.md`는 주문 실행 로그가 아니라 청산 완료 거래의 사후 복기입니다. 실전/Paper에서는 `trading_logs/tracked_positions.json`으로 열린 포지션을 추적하고, reconcile 루프가 청산을 감지한 뒤 복기를 생성합니다.

## Backtest-Driven Tuning
최근 BTCUSD 백테스트 손실 분석을 반영하여, 기본 백테스트 리스크는 거래당 `0.5%`(`RISK_PCT=0.005`)로 낮췄습니다. 실전/Paper 워크플로우도 `RISK_PER_TRADE_PCT` 환경 변수로 동일하게 조정할 수 있습니다.

백테스트 리포트에는 이제 차트 기준 분봉, 의사결정 타임프레임, 파이프라인 호출 간격, 거래당 리스크 한도가 기록됩니다. 차트는 첫 번째 타임프레임을 기준으로 그리고, 나머지 타임프레임은 의사결정 보조 데이터로 쓰입니다.

과거 데이터 CSV 파일명은 `SYMBOL_YYYYMMDD-YYYYMMDD_TIMEFRAME.csv` 형식을 사용합니다. 예: `BTCUSD_20250101-20250131_M15.csv`.

## 🗺️ 향후 실행 로드맵 (Action Plan)
프로젝트의 상세한 단계별 실행 로드맵 및 MVP 구현 체크리스트는 별도의 문서로 분리하여 관리합니다.
현재 `Phase 1`이 성공적으로 완료되었으며, 남은 구현 계획은 아래 문서를 참고하십시오.

👉 **[docs/mvp-implementation-plan.md](docs/mvp-implementation-plan.md) 참조**
