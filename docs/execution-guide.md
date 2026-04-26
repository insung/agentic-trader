# Execution Guide

이 문서는 Agentic Trader를 로컬에서 실행하고, Paper/Live 트레이딩 파이프라인을 구동하는 절차를 정리합니다. 테스트 절차는 [testing-guide.md](./testing-guide.md), 백테스트 절차는 [backtesting-guide.md](./backtesting-guide.md)를 참고하십시오.

## Prerequisites

1. **MetaTrader 5:** 실제 시장 데이터와 live 주문 검증에는 Wine 환경의 MT5 터미널이 필요합니다.
2. **Algorithmic trading:** MT5의 `[도구] -> [옵션] -> [전문가 조언자]`에서 알고리즘 매매를 허용해야 합니다.
3. **Dependencies:** 처음 실행하는 환경에서는 `make install`을 실행합니다.
4. **API key:** LLM 노드가 실제 호출되는 실행에는 Google GenAI API 키가 필요합니다.

## Start Backend

```bash
# Native Python 서버 실행 (MT5 미연결, API/문서/일부 점검용)
make run

# MT5 연동 트레이딩 실행용
make run-wine
```

기본 API 주소는 `http://127.0.0.1:8001`입니다. 포트를 바꾸려면 `PORT=8002`를 지정합니다.

```bash
make run PORT=8002
```

## Trigger Trading Pipeline

현재 기본 전략 설정은 `M15,M30` 타임프레임 조합을 사용합니다.

```bash
make trigger SYMBOL=EURUSD TIMEFRAMES=M15,M30 MODE=paper
```

직접 API를 호출할 경우 `timeframes`는 문자열이 아니라 JSON 배열이어야 합니다.

```bash
curl -X POST http://localhost:8001/api/v1/trade/trigger \
  -H "Content-Type: application/json" \
  -d '{"symbol": "EURUSD", "timeframes": ["M15", "M30"], "mode": "paper"}'
```

대화형 CLI를 사용할 수도 있습니다.

```bash
make cli
# 내부 실행 경로: python tools/trade_cli.py --port 8001
```

CLI는 심볼, 타임프레임, paper/live 모드를 선택하고 `/api/v1/trade/trigger`로 요청을 보냅니다. 전략은 CLI에서 직접 고르지 않고, Tech Analyst가 판정한 market regime과 `backend/config/strategies_config.json`에 따라 자동 주입됩니다.

## Monitor Runtime

서버 로그에서 다음 흐름을 확인합니다.

1. Data Fetch: MT5 또는 mock 데이터 수집
2. Tech Analysis: 시장 상태와 `trade_worthy` 판정
3. Strategy Hypothesis: market regime 기반 전략 가설
4. Chief Trader Decision: BUY/SELL/HOLD 결정
5. Guardrails and Strategy Gate: SL/TP, risk/reward, ATR, EMA/ADX/Bollinger 조건 검증
6. Execution: Paper 또는 live 주문 전송
7. Position Tracking: 로컬 파일과 `trading_logs/trading_logs.sqlite`에 열린 포지션 기록
8. Post-Close Review: 청산 후 `trading_logs/review_*.md` 및 SQLite `trade_reviews` 기록

## Reconcile Closed Positions

서버에는 기본 30초 간격의 자동 reconcile 루프가 있습니다. 간격은 서버 실행 전 환경 변수로 조절합니다.

```bash
POSITION_RECONCILE_INTERVAL_SECONDS=10 make run-wine
```

즉시 동기화하려면 다음 명령을 사용합니다.

```bash
make reconcile
```

또는 직접 API를 호출합니다.

```bash
curl -X POST http://localhost:8001/api/v1/trade/reconcile
```

`reviewed_count`가 1 이상이면 청산된 포지션에 대해 Risk Reviewer가 실행된 것입니다. 실전/Paper 운영 절차는 [live-operation-runbook.md](./live-operation-runbook.md)를 참고하십시오.

## Agentic Backtesting

백테스트는 실제 LangGraph agent pipeline을 과거 데이터 위에서 실행합니다. 단순 룰 백테스트가 아니라 각 step에서 LLM 판단, Python guardrail, deterministic strategy gate를 함께 검증합니다.

실행 체크리스트, `make backtest-fetch`, `make backtest-run`, `RISK_PCT`, 여러 달 기간 조회, 결과 확인 방법은 [backtesting-guide.md](./backtesting-guide.md)를 기준 문서로 관리합니다. SQLite 저장소 구조와 조회 쿼리는 [sqlite-storage.md](./sqlite-storage.md)를 참고하십시오.

## Strategy Changes

전략은 Python 코드로 직접 하드코딩하지 않습니다.

1. `docs/trading-strategies/`에 전략 문서를 작성합니다.
2. `backend/config/strategies_config.json`에 allowed regime과 required timeframes를 등록합니다.
3. 주문 가능한 전략이라면 `backend/features/trading/strategy_validators.py`에 deterministic gate를 추가합니다.
4. 관련 테스트를 추가하고 `make test`를 통과시킵니다.

## Safety Note

Live mode는 실제 주문을 전송할 수 있습니다. 충분한 Paper/Demo 검증 없이 live mode를 사용하지 마십시오.
