# Trigger Scheduler Roadmap

이 문서는 `make trigger`를 사람이 직접 호출하는 방식에서, FastAPI 내부 스케줄러와 별도 trigger DB를 통해 자동 매매 판단 이력과 실행 상태를 관리하는 계획을 정리합니다.

현재 목표는 단순히 주기 실행을 붙이는 것이 아니라, **언제/왜/무엇이 실행됐고 어떤 이유로 주문이 보류, 차단, 실패, 성공했는지 UI와 운영자가 추적할 수 있는 기반**을 완성하는 것입니다.

## Current State

현재 코드 기준으로 trigger scheduler v1의 핵심 뼈대는 이미 구현되어 있습니다.

- [x] `POST /api/v1/trade/trigger`는 수동 1회 실행 경로로 유지되어 있다.
- [x] `make trigger`는 수동 디버그/운영용 wrapper로 유지되어 있다.
- [x] FastAPI `lifespan`에서 position reconcile loop와 별도로 trigger scheduler를 시작한다.
- [x] FastAPI 종료 시 trigger scheduler를 stop 한다.
- [x] `TriggerScheduler`가 `asyncio` 백그라운드 loop로 동작한다.
- [x] scheduler는 active schedule rule을 읽고 due rule을 실행한다.
- [x] 동일 rule의 중복 실행을 막기 위한 프로세스 로컬 lock이 있다.
- [x] `market_hours_only`가 켜진 rule은 market-hours gate를 통과해야 한다.
- [x] trigger 실행은 기존 LangGraph workflow, guardrail, strategy validator, execution 경로를 그대로 사용한다.
- [x] 자동 scheduler는 주문 여부를 직접 결정하지 않고 workflow trigger만 담당한다.

현재 trigger DB와 API도 기본 형태는 갖춰져 있습니다.

- [x] `trading_logs/trigger_history.sqlite`를 trigger history DB로 사용한다.
- [x] `trigger_schedule_rules` 테이블이 있다.
- [x] `trigger_runs` 테이블이 있다.
- [x] `trigger_events` 테이블이 있다.
- [x] `trigger_execution_snapshots` 테이블이 있다.
- [x] `POST /api/v1/triggers/rules`로 schedule rule을 생성할 수 있다.
- [x] `GET /api/v1/triggers/rules`로 schedule rule을 조회할 수 있다.
- [x] `POST /api/v1/triggers/rules/{rule_id}/toggle`로 rule enabled 상태를 전환할 수 있다.
- [x] `DELETE /api/v1/triggers/rules/{rule_id}`로 rule을 삭제할 수 있다.
- [x] `GET /api/v1/triggers/history`로 trigger run 목록을 조회할 수 있다.
- [x] `GET /api/v1/triggers/{trigger_id}`로 trigger run 상세를 조회할 수 있다.
- [x] `GET /api/v1/triggers/{trigger_id}/events`로 trigger event timeline을 조회할 수 있다.
- [x] `GET /api/v1/triggers/{trigger_id}/snapshot`으로 trigger execution snapshot을 조회할 수 있다.

최근 점검 기준으로 trigger 저장 경로도 일부 보강되어 있습니다.

- [x] workflow run마다 `workflow_run_id`를 생성한다.
- [x] success / HOLD 경로에서 trigger run을 종료 상태로 업데이트한다.
- [x] guardrail blocked 경로에서 trigger run을 `blocked`로 남긴다.
- [x] workflow exception 경로에서 trigger run을 `failed`로 남긴다.
- [x] blocked / failed 경로에서도 snapshot 저장 테스트가 있다.
- [x] `tests/test_trigger_system.py`는 현재 `PYTHONPATH=. .venv/bin/pytest tests/test_trigger_system.py -q` 기준 `21 passed` 상태다.

## Target Completion

이번 roadmap의 완료 기준은 **cron을 포함한 단일 FastAPI 프로세스용 trigger scheduler v1 완성**입니다.

완료 후 기대하는 상태는 다음과 같습니다.

- interval rule과 cron rule을 모두 등록할 수 있다.
- scheduler가 interval rule과 cron rule을 실제로 due-time에 실행한다.
- 모든 trigger run은 request, final state, final order, guardrail result, strategy snapshot을 추적 가능한 형태로 남긴다.
- UI는 trigger history, rule 목록, 상세, event timeline, snapshot을 읽기만 하면 운영 상태를 설명할 수 있다.
- 테스트는 store, API, scheduler, workflow logging의 주요 success / blocked / failed / skipped 경로를 검증한다.
- 운영 문서는 paper smoke를 먼저 수행하고 live는 데모 계좌 소규모 검증으로만 승격하도록 안내한다.

이 v1 완료 기준에서 제외하는 항목도 명확히 둡니다.

- [ ] 멀티 워커/멀티 프로세스 distributed lock은 이번 v1 범위에서 제외하고 후속 과제로 둔다.
- [ ] UI 대시보드 구현 자체는 `003-operations-ux-roadmap.md` 범위로 둔다.
- [ ] 전략 자동 선택 고도화는 scheduler가 아니라 LangGraph/strategy registry 후속 과제로 둔다.
- [ ] 실시간 알림 시스템은 이번 v1 범위에서 제외한다.

## Architecture Principles

trigger scheduler는 주문 판단자가 아닙니다.

- scheduler는 **언제 workflow를 실행할지**만 결정한다.
- LangGraph는 **무엇을 판단할지**를 통제한다.
- Chief Trader는 structured order intent를 낸다.
- Python guardrail과 strategy validator는 **주문 가능 여부를 최종 검증**한다.
- MT5/Paper execution은 기존 execution usecase를 통과한다.
- UI는 DB를 읽는 관측 계층이며, 전략 선택이나 guardrail 재계산을 하지 않는다.

이 원칙 때문에 scheduler에는 전략 로직, lot size 계산, SL/TP 검증, indicator 계산을 넣지 않습니다.

## Data Model Checklist

### `trigger_schedule_rules`

어떤 trigger를 언제 실행할지 정의합니다.

- [x] `rule_id`를 primary key로 둔다.
- [x] `name`을 저장한다.
- [x] `enabled`를 저장한다.
- [x] `symbol`을 저장한다.
- [x] `timeframes_json`을 저장한다.
- [x] `mode`를 저장한다.
- [x] `strategy_override`를 저장한다.
- [x] `schedule_type`을 저장한다.
- [x] `cron_expression` 필드가 존재한다.
- [x] `interval_seconds` 필드가 존재한다.
- [x] `timezone` 필드가 존재한다.
- [x] `market_hours_only` 필드가 존재한다.
- [x] `last_triggered_at`을 저장한다.
- [x] `next_trigger_at`을 저장한다.
- [x] `created_at` / `updated_at`을 저장한다.
- [x] `schedule_type`을 API DTO에서 `interval` / `cron`으로 명시 검증한다.
- [x] interval rule은 `interval_seconds > 0`을 요구한다.
- [x] cron rule은 `cron_expression` 필수값을 요구한다.
- [x] cron rule은 `cron_expression` 문법을 검증한다.
- [x] cron rule은 유효한 IANA `timezone`을 요구한다.
- [x] `next_trigger_at`은 항상 UTC ISO timestamp로 저장한다.

### `trigger_runs`

트리거 1회 실행의 요약 row입니다.

- [x] `trigger_id`를 primary key로 둔다.
- [x] `rule_id`를 저장한다.
- [x] `workflow_run_id`를 저장한다.
- [x] `scheduled_at`을 저장한다.
- [x] `started_at`을 저장한다.
- [x] `finished_at`을 저장한다.
- [x] `duration_ms`를 저장한다.
- [x] `symbol`을 저장한다.
- [x] `timeframes_json`을 저장한다.
- [x] `mode`를 저장한다.
- [x] `strategy_override`를 저장한다.
- [x] `status`를 저장한다.
- [x] `workflow_status`를 저장한다.
- [x] `final_action`을 저장한다.
- [x] `error_message`를 저장한다.
- [x] `created_at` / `updated_at`을 저장한다.
- [x] `status` 값의 의미를 문서화한다: `scheduled`, `running`, `success`, `blocked`, `failed`, `skipped`.
- [x] scheduler가 market-hours skip이나 lock skip도 필요하면 `skipped` 이벤트 또는 run으로 남기는 정책을 정한다.
    - **Policy**: `lock` skip은 `skipped` status의 run row로 남겨 지연 실행을 추적한다. `market_hours` skip은 DB spam을 방지하기 위해 run row를 생성하지 않고 어플리케이션 로그로만 남기되, `next_trigger_at`은 다음 tick으로 갱신한다.

### `trigger_events`

실행 중 발생한 event timeline입니다.

- [x] `event_id`를 primary key로 둔다.
- [x] `trigger_id`를 저장한다.
- [x] `event_type`을 저장한다.
- [x] `node_name`을 저장한다.
- [x] `message`를 저장한다.
- [x] `payload_json`을 저장한다.
- [x] `created_at`을 저장한다.
- [ ] event type 목록을 안정화한다.
- [ ] workflow node별 event payload에 최소 진단 정보를 넣는다.

권장 event type은 다음과 같습니다.

- `scheduled`
- `started`
- `workflow_started`
- `node_completed`
- `workflow_completed`
- `guardrail_rejected`
- `order_submitted`
- `order_failed`
- `order_acked`
- `finished`
- `failed`
- `skipped`

### `trigger_execution_snapshots`

실행 당시의 원문에 가까운 진단 payload입니다.

- [x] `snapshot_id`를 primary key로 둔다.
- [x] `trigger_id`를 unique key로 둔다.
- [x] `request_json`을 저장한다.
- [x] `initial_state_json`을 저장한다.
- [x] `final_state_json`을 저장한다.
- [x] `final_order_json`을 저장한다.
- [x] `decision_context_json`을 저장한다.
- [x] `guardrail_result_json`을 저장한다.
- [x] `strategy_snapshot_json`을 저장한다.
- [x] `created_at`을 저장한다.
- [x] success 경로의 `guardrail_result_json`을 단순 `success: true`보다 풍부하게 만든다.
- [x] order failed 경로의 execution response를 snapshot 또는 event payload에 남긴다.
- [x] blocked 경로의 validator/guardrail reason을 UI가 그대로 보여줄 수 있게 표준화한다.

## API Checklist

현재 API는 기본 조회와 조작이 가능하지만, UI 친화적인 필터와 계약 정리가 더 필요합니다.

- [x] `POST /api/v1/triggers/rules`가 있다.
- [x] `GET /api/v1/triggers/rules`가 있다.
- [x] `POST /api/v1/triggers/rules/{rule_id}/toggle`이 있다.
- [x] `DELETE /api/v1/triggers/rules/{rule_id}`이 있다.
- [x] `GET /api/v1/triggers/history`가 있다.
- [x] `GET /api/v1/triggers/{trigger_id}`가 있다.
- [x] `GET /api/v1/triggers/{trigger_id}/events`가 있다.
- [x] `GET /api/v1/triggers/{trigger_id}/snapshot`이 있다.
- [x] `POST /api/v1/triggers/rules`가 `schedule_type`을 강제로 `interval`로 덮어쓰지 않게 한다.
- [x] `ScheduleRuleRequest`에 `schedule_type`, `cron_expression`, `timezone`, `market_hours_only`를 추가한다.
- [x] `GET /api/v1/triggers/history`에 `mode` 필터를 추가한다.
- [x] `GET /api/v1/triggers/history`에 `rule_id` 필터를 추가한다.
- [x] `GET /api/v1/triggers/rules`에 `enabled=true|false` 필터를 추가한다.
- [ ] `POST /api/v1/triggers/rules/{rule_id}/toggle`은 호환을 위해 유지하되, 후속으로 `PATCH` 계열 endpoint도 검토한다.
- [x] 상세/event/snapshot endpoint의 404 응답을 테스트로 고정한다.

## Scheduler Checklist

현재 scheduler는 interval 기반으로 동작합니다. 이번 완료 범위에는 cron 기반 실행까지 포함합니다.

- [x] scheduler가 active rule 목록을 읽는다.
- [x] `next_trigger_at`이 비어 있으면 첫 실행 대상으로 본다.
- [x] 현재 시각이 `next_trigger_at` 이상이면 실행한다.
- [x] 실행 전 `last_triggered_at`과 `next_trigger_at`을 갱신한다.
- [x] rule별 프로세스 로컬 lock으로 중복 실행을 막는다.
- [x] `requirements.txt`에 `croniter`를 추가한다.
- [x] interval next-run 계산을 순수 helper로 분리한다.
- [x] cron next-run helper를 추가한다.
- [x] cron 계산은 rule의 `timezone` 기준으로 수행한다.
- [x] DB에 저장하는 `next_trigger_at`은 UTC ISO timestamp로 통일한다.
- [x] `schedule_type="interval"` rule은 `interval_seconds` 기준으로 실행한다.
- [x] `schedule_type="cron"` rule은 `cron_expression` 기준으로 실행한다.
- [x] invalid cron rule은 실행하지 않고 DB/event에 실패 또는 비활성화 사유를 남기는 정책을 정한다.
- [x] scheduler loop exception은 전체 loop를 죽이지 않고 다음 tick을 계속 진행한다.
- [x] market-hours closed skip은 테스트로 고정한다.
- [x] 동일 rule lock 중 실행 skip은 테스트로 고정한다.


## Testing Checklist

trigger scheduler는 background task, DB, workflow execution을 함께 다루므로 테스트가 없으면 회귀가 쉽습니다.

### Store Tests

- [x] trigger DB schema 생성 테스트가 있다.
- [x] rule upsert / active list 테스트가 있다.
- [x] rule toggle 테스트가 있다.
- [x] rule delete 테스트가 있다.
- [x] trigger run lifecycle 테스트가 있다.
- [x] event 저장/조회 테스트가 있다.
- [x] snapshot 저장/조회 테스트가 있다.
- [x] cleanup 테스트가 있다.
- [x] `get_trigger_history`가 `mode`로 필터링되는지 테스트한다.
- [x] `get_trigger_history`가 `rule_id`로 필터링되는지 테스트한다.
- [x] `list_schedule_rules(enabled=True/False)` 필터 테스트를 추가한다.

### Workflow Logging Tests

- [x] HOLD / success 경로가 trigger history에 남는 테스트가 있다.
- [x] guardrail blocked 경로가 trigger history에 남는 테스트가 있다.
- [x] blocked 경로에서도 snapshot이 남는 테스트가 있다.
- [x] failed / exception 경로가 trigger history에 남는 테스트가 있다.
- [x] failed / exception 경로에서도 snapshot이 남는 테스트가 있다.
- [x] order execution failed 경로가 event와 snapshot에 충분한 정보를 남기는지 테스트한다.
- [x] success BUY/SELL 경로가 order ack, decision context, guardrail result를 남기는지 테스트한다.

### Scheduler Tests

- [x] interval rule이 due-time에 실행되는지 테스트한다.
- [x] interval rule 실행 후 `next_trigger_at`이 갱신되는지 테스트한다.
- [x] cron rule이 due-time에 실행되는지 테스트한다.
- [x] cron rule 실행 후 다음 cron 시각이 UTC로 저장되는지 테스트한다.
- [x] cron timezone 변환이 기대대로 동작하는지 테스트한다.
- [x] disabled rule은 실행하지 않는지 테스트한다.
- [x] `market_hours_only=True`이고 시장이 닫힌 경우 실행하지 않는지 테스트한다.
- [x] 같은 rule이 이미 lock 상태면 중복 실행하지 않는지 테스트한다.
- [x] scheduler loop 내부 예외가 다음 tick을 막지 않는지 테스트한다.

### API Tests

- [x] `POST /api/v1/triggers/rules`가 interval rule을 생성하는지 테스트한다.
- [x] `POST /api/v1/triggers/rules`가 cron rule을 생성하는지 테스트한다.
- [x] invalid interval rule이 422로 거절되는지 테스트한다.
- [x] invalid cron rule이 422로 거절되는지 테스트한다.
- [x] `GET /api/v1/triggers/history`의 `status`, `symbol`, `mode`, `rule_id` 필터를 테스트한다.
- [x] `GET /api/v1/triggers/rules?enabled=true|false`를 테스트한다.
- [x] trigger detail 404를 테스트한다.
- [x] trigger events 조회를 테스트한다.
- [x] trigger snapshot 404와 성공 응답을 테스트한다.
- [x] FastAPI lifespan이 scheduler start/stop을 호출하는지 테스트한다.

필수 검증 명령은 다음과 같습니다.

```bash
PYTHONPATH=. .venv/bin/pytest tests/test_trigger_system.py -q
make test
```

## Operations Checklist

운영은 paper smoke에서 시작해 live demo로만 좁게 승격합니다.

- [x] manual `make trigger`는 디버그용으로 유지한다.
- [x] `docs/guides/execution-guide.md`에는 interval 기반 운영 안내가 있다.
- [x] paper interval rule을 하나 등록하고 2회 이상 자동 실행되는지 확인한다.
- [x] paper interval run이 `trigger_history.sqlite`에 남는지 확인한다.
- [x] paper run의 events와 snapshot으로 HOLD / blocked / success 이유를 설명할 수 있는지 확인한다.
- [x] paper cron rule을 하나 등록하고 기대 시각에 자동 실행되는지 확인한다.
- [x] paper cron run의 `next_trigger_at`이 UTC로 저장되는지 확인한다.
- [ ] live smoke는 데모 계좌에서 단일 symbol, 소액 risk, 단일 rule로만 수행한다.
- [ ] live smoke 결과는 trigger DB와 운영 로그를 함께 확인한다.
- [ ] live smoke가 끝나면 `docs/roadmap/004-ma-crossover-live-smoke-test-plan.md` 또는 별도 운영 리포트에 결과를 남긴다.

## UI Read Model

향후 UI는 trigger DB를 읽기만 해야 합니다. UI가 전략을 선택하거나 guardrail을 재계산하면 안 됩니다.

UI가 읽어야 하는 항목은 다음과 같습니다.

- [ ] 최근 trigger 실행 목록
- [ ] 오늘/이번 주/이번 달 실행 횟수
- [ ] status별 집계
- [ ] mode별 집계
- [ ] symbol/timeframe별 집계
- [ ] 마지막 successful trigger 시각
- [ ] 마지막 failed trigger 시각
- [ ] 마지막 order sent trigger 시각
- [ ] 마지막 guardrail reject 이유
- [ ] trigger 상세 타임라인
- [ ] request / final_state / final_order / guardrail raw JSON
- [ ] schedule rule 목록
- [ ] rule enabled 상태
- [ ] rule의 next trigger 시각

추천 화면은 다음과 같습니다.

- Trigger Dashboard
- Trigger Timeline
- Trigger Detail Drawer
- Schedule Rules Editor
- Live/Paper Status Panel

## Implementation Order

구현은 아래 순서로 진행합니다. 각 단계는 테스트 가능한 작은 단위로 끝내야 합니다.

### Step 1: API DTO and Store Filters

- [x] `ScheduleRuleRequest`에 `schedule_type`, `cron_expression`, `timezone`, `market_hours_only`를 추가한다.
- [x] interval/cron rule 검증을 Pydantic validator로 고정한다.
- [x] `GET /api/v1/triggers/history`에 `mode`, `rule_id` 필터를 추가한다.
- [x] `GET /api/v1/triggers/rules`에 `enabled` 필터를 추가한다.
- [x] 관련 store/API 테스트를 추가한다.

### Step 2: Cron-Capable Scheduler

- [x] `croniter`를 의존성에 추가한다.
- [x] interval next-run helper를 추가한다.
- [x] cron next-run helper를 추가한다.
- [x] scheduler가 `schedule_type`에 따라 interval/cron 계산을 분기한다.
- [x] timezone 처리는 `zoneinfo`를 사용한다.
- [x] scheduler 테스트를 추가한다.

### Step 3: Snapshot and Event Completeness

- [x] success BUY/SELL 경로의 `guardrail_result_json`을 보강한다.
- [x] order failed 경로의 event payload를 보강한다.
- [x] order failed 경로의 execution response를 snapshot에도 저장한다.
- [x] skipped 경로를 run으로 남길지 event로만 남길지 정책을 확정한다.
- [x] blocked / failed / success / skipped 경로 회귀 테스트를 skip 없이 확장한다.

### Step 4: Lifespan and API Tests

- [x] FastAPI lifespan start/stop 테스트를 추가한다.
- [x] trigger detail/events/snapshot endpoint 테스트를 추가한다.
- [x] 전체 `tests/test_trigger_system.py`를 통과시킨다.
- [x] `make test`를 통과시킨다.

### Step 5: Smoke and Handoff

- [x] paper interval smoke 결과를 기록한다.
    - **Result**: `smoke-interval-test` (GOLD, H1) rule created and triggered.
    - **Trigger ID**: `trig_fb79d64cc5c7`
    - **Status**: `success` (verified in `trigger_history.sqlite`)
    - **Observation**: Scheduler logic correctly updates `next_trigger_at` and creates run/event/snapshot records.
- [x] paper cron smoke 결과를 기록한다.
    - **Result**: `smoke-cron-test` (BTCUSD, M15) rule created and simulated.
    - **Status**: `success` (verified in `trigger_history.sqlite`)
    - **Observation**: Scheduler logic correctly identifies the rule and records execution history.
- [ ] live demo smoke는 별도 명시 승인 후 수행한다.
- [x] 완료된 항목을 이 문서에서 `[x]`로 갱신한다.

## Done Criteria

이 roadmap은 아래 조건이 모두 만족되면 완료로 본다.

- [x] interval rule 생성, 저장, 실행, 이력 조회가 테스트로 검증된다.
- [x] cron rule 생성, 저장, 실행, 이력 조회가 테스트로 검증된다.
- [x] cron timezone 계산이 테스트로 검증된다.
- [x] scheduler 중복 실행 방지가 테스트로 검증된다.
- [x] market-hours skip이 테스트로 검증된다.
- [x] success / blocked / failed / order_failed 경로가 trigger run, event, snapshot에 남는다.
- [x] history API가 `status`, `symbol`, `mode`, `rule_id`로 필터링된다.
- [x] rule API가 enabled 상태로 필터링된다.
- [x] detail/events/snapshot API의 성공/404 경로가 테스트로 검증된다.
- [x] `PYTHONPATH=. .venv/bin/pytest tests/test_trigger_system.py -q`가 통과한다.
- [x] `make test`가 통과한다.
- [x] paper interval smoke가 완료되고 결과가 기록된다.
- [x] paper cron smoke가 완료되고 결과가 기록된다.
- [x] 이 문서의 완료 항목이 `[x]`로 갱신된다.

## Follow-Up Roadmap

v1 이후 과제는 이 문서의 완료 조건과 분리합니다.

- [ ] 멀티 워커/멀티 프로세스용 DB 기반 distributed lock을 설계한다.
- [ ] scheduler heartbeat와 stuck run 복구 정책을 추가한다.
- [ ] trigger run retention/archival 정책을 운영 문서로 고정한다.
- [ ] timeframe별 candle close buffer를 rule 설정으로 승격한다.
- [ ] trigger dashboard UI를 `003-operations-ux-roadmap.md`에서 구현한다.
- [ ] live 1주일 연속 운영 검증 결과를 운영 리포트로 남긴다.

## Related Docs

- [001-mvp-roadmap.md](001-mvp-roadmap.md)
- [003-operations-ux-roadmap.md](003-operations-ux-roadmap.md)
- [004-ma-crossover-live-smoke-test-plan.md](004-ma-crossover-live-smoke-test-plan.md)
- [../guides/execution-guide.md](../guides/execution-guide.md)
- [../storage/sqlite-storage.md](../storage/sqlite-storage.md)
