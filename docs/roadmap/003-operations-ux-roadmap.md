# Operations UX Roadmap

이 문서는 규칙, 전략, 백테스트, guardrail이 늘어나도 사람이 수동으로 이해하고 조작할 수 있게 만드는 운영 UX 계획입니다.

새 AI 세션은 이 문서를 읽으면 바로 작업을 시작할 수 있어야 합니다. 구현할 때도 root `AGENTS.md`의 원칙이 우선이며, LLM은 판단 보조이고 주문 가능 여부는 FastAPI/Python guardrail과 deterministic validator가 결정합니다.

상위 진행 순서와 첫 작업 후보는 `docs/ux/README.md`를 기준으로 확인합니다. 이 문서는 세부 체크리스트와 화면/API 요구사항을 관리합니다.

## 시작 전 확인 순서

- [ ] `AGENTS.md`를 읽고 safety/air-gap, LangGraph, deterministic validator 원칙을 확인합니다.
- [ ] `docs/roadmap/001-mvp-roadmap.md`에서 현재 phase와 미완료 항목을 확인합니다.
- [ ] `docs/ux/README.md`에서 UX 작업의 상위 진행 순서를 확인합니다.
- [ ] 이 문서의 체크박스 상태를 확인합니다.
- [ ] `backend/config/strategies_config.json`과 `docs/trading-strategies/`의 현재 등록 전략을 확인합니다.
- [ ] `backend/features/trading/strategy_validators.py`의 validator 조건을 확인합니다.
- [ ] `docs/storage/sqlite-schema-reference.md`에서 backtest/run/trade/decision 테이블을 확인합니다.
- [ ] `git status --short`로 사용자 변경이 있는지 확인합니다.

## UX 원칙

- [ ] 사람이 직접 만지는 표면은 하나로 모으고, 문서/JSON/Python/SQLite가 흩어져 보이지 않게 합니다.
- [ ] 위험한 변경은 바로 live에 반영하지 않고 `draft -> registered -> validated -> backtested -> paper_enabled -> live_enabled` 상태 승격을 거치게 합니다.
- [ ] Python validator와 guardrail은 최종 법입니다. UI는 이를 설명하고 파라미터화 가능한 값만 안전하게 노출합니다.
- [ ] LLM 판단과 Python 차단 사유를 같은 화면에서 보여줍니다.
- [ ] 백테스트 결과는 Markdown/PNG artifact가 아니라 SQLite source-of-truth에서 재구성합니다.
- [ ] 운영 UI는 마케팅 페이지가 아니라 조용하고 밀도 있는 업무 도구로 설계합니다.

## 대상 사용자

- Board 역할의 인간 운영자
- 전략을 추가/조정하는 연구자
- 백테스트 결과를 검토하고 Paper/Live 승격을 결정하는 운영자

## 정보 구조

### 1. Board Console

목표: 현재 봇이 무엇을 할 수 있고 무엇은 금지되어 있는지 한 화면에서 확인합니다.

- [ ] 현재 모드 표시: local, paper, live.
- [ ] MT5 연결 상태와 마지막 health check 표시.
- [ ] 활성 심볼, timeframe, risk pct 표시.
- [ ] 오늘의 주문 수, 일일 손익, 일일 손실 한도 소진율 표시.
- [ ] 현재 열린 포지션과 추적 ticket 표시.
- [ ] 최근 10개 decision의 `OPENED/HOLD/REJECTED/SKIP` 상태 표시.
- [ ] 최근 validator 차단 사유 Top 5 표시.
- [ ] 최근 백테스트 run 요약 표시.
- [ ] Paper/Live 가능 전략 수와 비활성 전략 수 표시.

필요 데이터:
- [ ] `trading_logs/trading_logs.sqlite`
- [ ] `backtests/data/market_data.sqlite`
- [ ] `/api/v1/health`
- [ ] 향후 운영 decision/execution 테이블

### 2. Strategy Workbench

목표: 전략 문서, frontmatter, config, validator, 테스트, 백테스트 결과를 하나의 전략 카드로 통합합니다.

- [ ] 전략 상태 모델 정의: `draft`, `registered`, `validated`, `backtested`, `paper_enabled`, `live_enabled`.
- [ ] `docs/trading-strategies/*.md` frontmatter를 읽어 전략 목록을 구성합니다.
- [ ] `backend/config/strategies_config.json` 등록 여부를 카드에 표시합니다.
- [ ] validator 지원 여부를 카드에 표시합니다.
- [ ] 관련 테스트 파일과 최근 테스트 결과를 카드에 표시합니다.
- [ ] 최근 백테스트 성과를 카드에 표시합니다: trades, net pnl, profit factor, max drawdown, rejected count.
- [ ] strategy name, frontmatter name, config name, validator matching이 어긋나면 경고합니다.
- [ ] strategy 문서를 UI에서 읽을 수 있게 표시합니다.
- [ ] 초기 버전에서는 UI 편집보다 읽기 전용 inspection을 우선합니다.

승격 규칙:
- [ ] `draft`: 문서만 있음.
- [ ] `registered`: `strategies_config.json`에 등록됨.
- [ ] `validated`: deterministic validator와 단위 테스트가 있음.
- [ ] `backtested`: 최근 백테스트 결과가 있고 최소 표본 기준을 충족함.
- [ ] `paper_enabled`: paper mode에서 실행 가능하도록 허용됨.
- [ ] `live_enabled`: 사람이 명시적으로 live 승격함.

### 3. Guardrail Center

목표: 안전 규칙을 사람이 이해하고 조정 가능한 파라미터와 코드 고정 규칙으로 구분합니다.

- [ ] 거래당 리스크 퍼센트 표시 및 환경 변수/config 출처 표시.
- [ ] 일일 손실 한도 표시.
- [ ] 일일 거래 횟수 제한 표시.
- [ ] 최소 risk/reward 표시.
- [ ] 최소 SL 거리 또는 ATR 기준 표시.
- [ ] 중복 포지션 차단 정책 표시.
- [ ] 수정 가능한 값과 코드 고정 규칙을 분리해 표시합니다.
- [ ] guardrail 변경은 Paper/Backtest 검증 전 live 반영을 막습니다.

후속 구현:
- [ ] `StrategyGateConfig`의 `min_adx`, `max_cross_age_bars`, `min_sl_atr`, Bollinger tolerance를 config화할지 결정합니다.
- [ ] config화한다면 기본값, 허용 범위, 변경 이력 저장 위치를 설계합니다.

### 4. Backtest Lab

목표: 사용자가 명령어를 외우지 않고 빠른 진단과 정식 검증을 실행하고 비교합니다.

- [ ] 입력 폼: symbol, timeframes, from, to, step, start_step, max_steps, risk_pct, no_review, log_level.
- [ ] 빠른 진단 preset 제공: `STEP=20`, `MAX_STEPS=10`, `NO_REVIEW=1`, `LOG_LEVEL=INFO`.
- [ ] 정식 검증 preset 제공: `MAX_STEPS` 없음, review 활성화.
- [ ] 실행 전 필요한 candles 존재 여부를 확인합니다.
- [ ] 실행 중 run status를 표시합니다: running, completed, interrupted, failed.
- [ ] 결과 요약 표시: final balance, net pnl, total trades, win rate, profit factor, max drawdown.
- [ ] decision 분포 표시: HOLD, REJECTED, OPENED, SKIP.
- [ ] validator 차단 사유 집계 표시.
- [ ] run 간 비교 화면을 추가합니다.

명령어 fallback:

```bash
make backtest-run \
  SYMBOL=BTCUSD \
  TIMEFRAMES=M15,M30 \
  FROM=2025-01-01 \
  TO=2025-01-31 \
  STEP=20 \
  MAX_STEPS=10 \
  NO_REVIEW=1 \
  LOG_LEVEL=INFO \
  RISK_PCT=0.005
```

### 5. Decision Audit

목표: 특정 판단에서 LLM이 무엇을 제안했고 Python이 왜 열거나 막았는지 재생합니다.

- [ ] decision timeline을 candle time 기준으로 표시합니다.
- [ ] Tech Analyst summary 표시.
- [ ] Strategist hypothesis 표시.
- [ ] Chief Trader final order intent 표시.
- [ ] indicator snapshot 표시.
- [ ] validator 통과/차단 결과 표시.
- [ ] 차단 사유를 사람이 읽을 수 있는 문장으로 표시합니다.
- [ ] 같은 시점의 candle chart와 entry/SL/TP 후보를 overlay합니다.
- [ ] HOLD decision도 "왜 거래하지 않았는지" 표시합니다.

필요 데이터:
- [ ] `backtest_decisions.indicator_snapshot_json`
- [ ] `backtest_decisions.final_order_json`
- [ ] `backtest_decisions.rejection_reason`
- [ ] `candles`
- [ ] 향후 운영 decision table

### 6. Alerts And Handoff

목표: 운영자가 놓치면 안 되는 상태만 알림으로 보냅니다.

- [ ] 주문 체결 알림.
- [ ] 포지션 청산 알림.
- [ ] Risk Reviewer 복기 생성 알림.
- [ ] MT5 연결 끊김 알림.
- [ ] daily loss limit 접근 알림.
- [ ] validator reject 급증 알림.
- [ ] 백테스트 completed/failed 알림.
- [ ] Telegram/Discord/Email 중 1개를 먼저 선택합니다.

## API 작업 항목

- [ ] `GET /api/v1/ops/summary`: Board Console 요약.
- [ ] `GET /api/v1/ops/strategies`: 전략 카드 목록.
- [ ] `GET /api/v1/ops/strategies/{name}`: 전략 상세, 문서, config, validator 상태.
- [ ] `GET /api/v1/ops/guardrails`: 현재 guardrail과 parameter source.
- [ ] `GET /api/v1/backtests/runs`: 최근 run 목록.
- [ ] `GET /api/v1/backtests/runs/{run_id}`: run 상세.
- [ ] `GET /api/v1/backtests/runs/{run_id}/decisions`: decision timeline.
- [ ] `GET /api/v1/backtests/runs/{run_id}/trades`: trade 목록.
- [ ] `POST /api/v1/backtests/runs`: 백테스트 실행 요청.

초기 구현 원칙:
- [ ] 먼저 읽기 전용 API를 만듭니다.
- [ ] write API는 Paper/Backtest 검증과 권한 모델이 생긴 뒤 추가합니다.
- [ ] SQLite 조회는 repo의 기존 store 모듈 패턴을 우선 따릅니다.

## Frontend 작업 항목

- [ ] 프론트엔드 스택 결정: FastAPI server-rendered admin page, React, Vue 중 하나.
- [ ] 첫 화면은 Board Console로 시작합니다.
- [ ] 좌측 내비게이션: Board, Strategies, Guardrails, Backtests, Decisions, Logs.
- [ ] 카드 안에 과한 설명문을 넣지 말고 상태와 수치를 우선합니다.
- [ ] 전략 목록은 표 또는 밀도 있는 카드 리스트로 구성합니다.
- [ ] 위험 상태는 색상과 아이콘으로 표시하되, 색상만으로 의미를 전달하지 않습니다.
- [ ] Backtest Lab은 폼, 실행 상태, 결과 테이블을 한 흐름으로 구성합니다.
- [ ] Decision Audit은 timeline + detail panel 구조를 사용합니다.
- [ ] 모바일보다 데스크톱 운영 화면을 우선합니다.

## 데이터 모델 점검 항목

- [ ] `backtest_runs`에 UI가 필요한 summary가 충분한지 확인합니다.
- [ ] `backtest_decisions`에 Tech/Strategist/Chief reasoning을 충분히 저장하는지 확인합니다.
- [ ] 운영/Paper decision table이 필요한지 설계합니다.
- [ ] strategy status를 저장할 별도 config/table이 필요한지 결정합니다.
- [ ] guardrail parameter history 저장 여부를 결정합니다.

## 구현 순서 제안

1. [ ] 읽기 전용 Strategy Workbench 검사 스크립트 또는 API를 만듭니다.
2. [ ] Board Console용 summary API를 만듭니다.
3. [ ] Backtest runs/decisions 조회 API를 만듭니다.
4. [ ] 최소 UI를 붙입니다.
5. [ ] Backtest Lab 실행 API를 붙입니다.
6. [ ] Guardrail Center를 읽기 전용으로 붙입니다.
7. [ ] strategy status 승격 모델을 추가합니다.
8. [ ] 알림 채널을 1개 붙입니다.

## 완료 기준

- [ ] 새 AI 세션이 이 문서만 보고 첫 API 또는 UI 작업을 시작할 수 있습니다.
- [ ] 사람이 전략별 상태를 문서/config/validator/test/backtest 관점에서 한 화면에 볼 수 있습니다.
- [ ] 사람이 최근 백테스트가 왜 수익/무수익/손실이었는지 decision 단위로 추적할 수 있습니다.
- [ ] 사람이 어떤 규칙이 live 주문을 막고 있는지 확인할 수 있습니다.
- [ ] 위험한 변경은 Paper/Backtest 검증 전 live로 승격되지 않습니다.
