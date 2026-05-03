# External Log Delivery

이 문서는 Agentic Trader의 structured runtime log를 Discord 같은 외부 알림 채널로 전달하기 위한 설계입니다. 목표는 trading core가 외부 메신저에 직접 의존하지 않으면서, 운영자가 중요한 실행 실패와 체결 이벤트를 빠르게 확인할 수 있게 하는 것입니다.

## Current State

현재 Python runtime은 `logging`을 사용해 `event`, `trigger_id`, `workflow_run_id`, `rule_id`, `symbol`, `mode`, `failure_reason` 같은 구조화 필드를 남깁니다. 이 로그는 trigger events/snapshots와 함께 live execution 문제를 추적하는 1차 관측 자료입니다.

아직 외부 알림 전송기는 구현하지 않습니다. 이 단계에서는 core trading path와 알림 전달 경계를 먼저 고정합니다.

## Design Decision

1차 후보는 **lightweight notifier process**입니다.

선택 이유:

- 현재 저장소 규모에서는 Vector.dev나 Fluent Bit보다 작은 Python notifier가 운영/테스트 비용이 낮습니다.
- Discord webhook 호출을 app core에서 분리하기 쉽습니다.
- 실패해도 trading workflow를 중단시키지 않는 독립 프로세스로 둘 수 있습니다.
- 이후 로그량이 늘면 Vector.dev 또는 Fluent Bit로 교체할 수 있습니다.

장기적으로는 아래 구조를 허용합니다.

```text
FastAPI / scheduler / trading_service
  -> structured JSON logs
  -> stdout or local log file
  -> lightweight notifier process
  -> Discord webhook HTTP
```

## Log Source

Python app은 structured JSON log를 stdout 또는 파일로 남깁니다.

권장 1차 설정:

- local dev: stdout
- live/demo operation: rotating local file plus stdout
- long-term storage: 별도 로그 저장소 또는 SQLite event/snapshot과 분리

app code는 Discord URL, webhook retry, rate limit, message formatting을 알지 않습니다.

## Log Schema

외부 전송 후보 로그는 최소한 아래 필드를 가집니다.

```json
{
  "timestamp": "2026-05-03T00:00:00Z",
  "level": "ERROR",
  "event": "trigger.execution.failed",
  "trigger_id": "trig_xxx",
  "workflow_run_id": "run_xxx",
  "rule_id": "rule_xxx",
  "symbol": "BTCUSD",
  "mode": "live",
  "status": "failed",
  "failure_reason": "Invalid ticket ID: 0",
  "message": "LIVE Order FAILED"
}
```

Optional fields:

- `strategy_override`
- `final_action`
- `blocked_stage`
- `ticket`
- `mt5_retcode`
- `mt5_comment`
- `duration_ms`

Sensitive fields such as password, token, API key, private webhook URL, and account credentials must not be emitted. If account login/server is needed for operation, mask it before external delivery.

## Alert Events

Default Discord alerts should include only high-signal events:

- `trigger.execution.requested`
- `trigger.execution.acked`
- `trigger.execution.failed`
- `trigger.guardrail.rejected`
- `trigger.strategy_validator.rejected`
- `trigger.scheduler.rule_skipped` when `skip_reason=lock_skip`
- `trigger.workflow.failed`
- `CRITICAL` or `ERROR` logs from runtime services

Default Discord alerts should exclude noisy events:

- `trigger.workflow.node_completed`
- `trigger.scheduler.rule_skipped` when `skip_reason=not_due`
- normal `trigger.workflow.started`
- normal `trigger.workflow.completed`
- low-level debug logs

## Discord Transport

Discord delivery uses webhook HTTP, not raw TCP.

The notifier owns:

- webhook URL loading from environment or secret store
- message formatting
- retry with bounded backoff
- rate limiting
- duplicate suppression
- delivery error logging

The trading app owns only:

- structured logging
- trigger events
- snapshots

Discord delivery failure must never fail a trading workflow.

## Rate Limit And Deduplication

1차 정책:

- 동일 `event + trigger_id + failure_reason`은 5분 안에 한 번만 보냅니다.
- `order_failed`, `order_acked`, `workflow.failed`는 즉시 보냅니다.
- repeated `lock_skip`은 rule별로 10분에 한 번만 보냅니다.
- Discord 429 응답은 notifier가 backoff 후 재시도하고, 최종 실패는 local log에만 남깁니다.

## Masking Policy

Sink 직전 masking을 한 번 더 적용합니다.

Mask keys:

- `password`
- `token`
- `api_key`
- `secret`
- `webhook`
- `authorization`

Account fields:

- `account_login`: 기본값 masking, 예: `12****89`
- `account_server`: 운영 식별이 필요하면 허용, broker credential과 함께 저장하지 않음

## Test Strategy

외부 알림 구현 시 테스트는 webhook을 실제 호출하지 않습니다.

- notifier input log parsing test
- event filtering test
- masking test
- deduplication test
- Discord webhook client mock test
- delivery failure does not raise into trading workflow test

## Non-Goals

- app core에서 Discord webhook을 직접 호출하지 않습니다.
- raw TCP로 Discord에 전송하지 않습니다.
- vector database를 로그 전달 도구로 사용하지 않습니다.
- LLM hidden reasoning이나 full prompt를 외부 알림으로 보내지 않습니다.

## Related Docs

- [Live Execution Observability Roadmap](../roadmap/005-live-execution-observability-roadmap.md)
- [Trading Execution Flow](./trading-execution-flow.md)
- [Live Operation Runbook](../guides/live-operation-runbook.md)
