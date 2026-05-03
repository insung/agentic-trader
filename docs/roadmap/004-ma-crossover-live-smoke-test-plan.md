# MA Crossover Live Smoke Test Plan

이 문서는 `Moving Average Crossover` 전략을 MT5 demo 계좌의 `MODE=live` 경로로 한 번 검증하기 위한 운영 계획입니다. 목표는 수익 검증이 아니라 live 주문 경로, guardrail, trigger logging, position tracking, reconcile이 함께 동작하는지 확인하는 것입니다.

## Current State

- 현재 runtime 등록 전략은 `Moving Average Crossover`와 `Bollinger Bands Reversion`입니다.
- 연구 문서 기준으로 live smoke 후보는 `Moving Average Crossover`입니다.
- `Bollinger` 계열은 연구/비교 baseline으로 남기고 live smoke 대상에서는 제외합니다.
- 현재 `trading_logs/trigger_history.sqlite`에는 live 실행 이력이 남아 있지 않습니다.
- 현재 서버 내 scheduler는 cron이 아니라 `interval_seconds` 기반 rule만 신뢰합니다.

## Preconditions

- MT5가 Wine 환경에서 실행 중이어야 합니다.
- MT5 계정은 demo 계좌를 사용합니다.
- MT5에서 algorithmic trading이 허용되어 있어야 합니다.
- 백엔드는 MT5 연동 경로로 실행합니다.

```bash
make run-wine
```

서버 상태를 확인합니다.

```bash
curl http://127.0.0.1:8001/api/v1/health
```

`mt5_available: true` 상태를 확인한 뒤 진행합니다.

## Schedule Rule

초기 live smoke rule은 아래 값으로 생성합니다.

- `symbol`: `BTCUSD`
- `timeframes`: `["M15", "M30"]`
- `mode`: `live`
- `strategy_override`: `Moving Average Crossover`
- `interval_seconds`: `900`
- `market_hours_only`: `false` 또는 BTCUSD broker 운영 시간 정책 확인 후 적용
- `enabled`: 처음에는 `false`로 생성하고, 준비가 끝난 뒤 한 번만 `true`로 전환합니다.

운영 리스크는 매우 작게 시작합니다.

```bash
RISK_PER_TRADE_PCT=0.001 make run-wine
```

## Execution Procedure

1. `make reconcile`로 기존 추적 포지션이 없는지 확인합니다.
2. MT5 Trade 탭에서 열린 포지션이 없는지 확인합니다.
3. live smoke schedule rule을 생성합니다.
4. rule을 enable하고 1회 실행을 기다립니다.
5. **1회 실행 확인 즉시 rule을 disable합니다.**
6. API를 통해 결과를 정밀하게 감시합니다:
   - `/api/v1/triggers/{trigger_id}/events`를 조회하여 `order_acked` 또는 `order_failed` 페이로드를 확인합니다.
   - `/api/v1/triggers/{trigger_id}/snapshot`을 조회하여 `guardrail_result.execution_details`와 `raw_response`를 확인합니다.
7. MT5 터미널의 Trade/History 탭을 직접 확인하여 서버 기록과 터미널 상태가 일치하는지 대조합니다.
8. `HOLD` 또는 `blocked`이면 차단/보류 사유가 snapshot에 남았는지 확인합니다.
9. 주문이 체결되면 MT5 ticket, SL, TP와 `trading_logs/tracked_positions.json`, `trading_logs/trading_logs.sqlite` 기록이 일치하는지 확인합니다.
10. 포지션 청산 후 `make reconcile` 또는 자동 reconcile로 Risk Reviewer 복기가 생성되는지 확인합니다.

## Done Criteria

- live mode trigger run이 `trading_logs/trigger_history.sqlite`에 남습니다.
- request, final state, final order, guardrail result snapshot이 비어 있지 않습니다.
- **성공 판정 기준 (Hardened):**
  - `ticket`이 0보다 커야 합니다.
  - `executed_price`가 0.0보다 커야 합니다.
  - MT5 `retcode`가 성공(10009 또는 10008)이어야 합니다.
  - 위 조건 중 하나라도 누락되면 `success`로 간주하지 않으며 `order_failed`로 기록되어야 합니다.
- `HOLD`, `blocked`, `failed`, `success` 중 어떤 결과든 사람이 원인을 추적할 수 있는 `raw_response`가 포함되어야 합니다.
- 체결된 경우 MT5 포지션과 로컬 추적 상태가 같은 ticket과 가격 정보를 가집니다.
- 청산된 경우 `trading_logs/review_*.md`와 SQLite `trade_reviews`에 복기가 남습니다.

## Related Docs

- [MVP Roadmap](./001-mvp-roadmap.md)
- [Trigger Scheduler Roadmap](./002-trigger-scheduler-roadmap.md)
- [Execution Guide](../guides/execution-guide.md)
- [Live Operation Runbook](../guides/live-operation-runbook.md)
- [MA Crossover Strategy](../trading-strategies/ma_crossover.md)

