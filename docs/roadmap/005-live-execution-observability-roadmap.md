# Live Execution Observability Roadmap

이 문서는 live mode 주문 실행이 실제 MT5 체결로 이어졌는지 검증할 수 있도록, execution result 판정과 trigger event/snapshot logging을 강화하는 계획입니다.

현재 발견된 문제는 `mode: live` 실행에서 `final_action=BUY`, `status=success`, `order_acked`가 남았지만, 실제 MT5에는 체결 내역이 보이지 않고 event payload에는 `ticket=0`, `executed_price=0.0`이 남은 것입니다. 이 상태를 성공으로 기록하면 운영자가 실제 주문 여부를 판단할 수 없습니다.

## Mandatory Rule For Worker AI

이 문서를 보고 작업하는 AI는 **절대로 이 문서의 체크박스를 `[x]`로 바꾸지 않습니다.**

- [x] 작업 AI는 이 문서의 체크박스를 수정하지 않는다.
- [x] 작업 AI는 구현과 테스트 결과만 최종 보고한다.
- [x] 체크 여부는 사람이 검토하거나 별도 검증 AI가 코드, DB, 테스트 결과를 확인한 뒤 갱신한다.
- [x] 작업 AI가 완료했다고 주장해도, 검증 전에는 어떤 항목도 완료로 간주하지 않는다.

## Goal

live execution의 성공/실패 판정을 실제 MT5 응답 기준으로 엄격하게 만들고, 운영자가 trigger detail/events/snapshot만 보고 아래 질문에 답할 수 있게 합니다.

- [x] 주문 요청이 MT5로 실제 전송됐는가?
- [x] MT5가 어떤 원본 응답을 반환했는가?
- [x] order ticket, deal ticket, executed price가 유효한가?
- [x] 실패했다면 MT5 retcode/comment 기준 실패 사유가 무엇인가?
- [x] Python guardrail, strategy validator, risk lot 계산은 어떤 값을 사용했는가?
- [x] DB에는 성공으로 보이지만 MT5에는 체결이 없는 상태가 다시 발생하지 않는가?

## Non-Goals

이번 작업은 live execution observability와 성공 판정 보강에 집중합니다.

- [x] 새 전략을 추가하지 않는다.
- [x] MA Crossover validator 조건을 완화하지 않는다.
- [x] LLM prompt를 수정해 BUY/SELL 빈도를 높이지 않는다.
- [x] scheduler interval/cron 로직을 다시 설계하지 않는다.
- [x] UI dashboard를 구현하지 않는다.
- [x] 실제 live 주문을 자동 테스트에서 실행하지 않는다.
- [x] 사람이 명시적으로 승인하기 전에는 live smoke를 다시 수행하지 않는다.

## Current Evidence

최근 live cron rule에서 아래와 같은 기록이 확인됐습니다.

- [x] `rule_id=843d9f4a-e1ec-4c39-a62d-a11cdde0b8f0`이 `mode=live`로 실행됐다.
- [x] 일부 run이 `final_action=BUY`, `status=success`로 기록됐다.
- [x] 해당 run의 event에는 `order_acked`가 남았다.
- [x] event payload에는 `ticket=0`, `executed_price=0.0`, `success=true`가 남았다.
- [x] MT5 Trade/History 탭에는 실제 체결 내역이 보이지 않았다.

이 문서의 작업 완료 후에는 `ticket=0` 또는 `executed_price=0.0`인 live execution이 성공으로 기록되면 안 됩니다.

## Desired Success Criteria

완료 후 live execution 성공 조건은 아래처럼 엄격해야 합니다.

- [x] live order result는 MT5 raw response를 보존한다.
- [x] MT5 retcode가 성공 계열이 아니면 failed 처리한다.
- [x] `order`, `deal`, `ticket` 중 유효한 식별자가 없으면 failed 처리한다.
- [x] `executed_price <= 0`이면 failed 처리한다.
- [x] 실패 시 `trigger_runs.status`는 `failed` 또는 `blocked` 중 정책에 맞게 기록된다.
- [x] 실패 시 `trigger_events`에 `order_failed`가 남는다.
- [x] 실패 시 `trigger_execution_snapshots.guardrail_result_json` 또는 `decision_context_json`에 원본 실행 응답과 판정 이유가 남는다.
- [x] 성공 시에만 `order_acked`가 남는다.
- [x] 성공 시에만 `track_open_position()`이 호출된다.
- [x] 사람이 `GET /api/v1/triggers/{trigger_id}/events`와 `/snapshot`만 보고 실제 체결 여부를 판단할 수 있다.

## Step 1: Read Existing Live Execution Contract

목표: 현재 live execution 결과가 어떤 shape으로 반환되는지 확인합니다. 이 단계에서는 코드를 수정하지 않습니다.

- [x] `backend/services/trading_service.py`의 live execution 분기를 읽는다.
- [x] `backend/features/trading/usecase.py`의 `TradeExecutionUseCase.execute_trade()`를 읽는다.
- [x] `backend/features/trading/adapters/mt5_execution.py`의 `MT5Client` 실행 메서드를 읽는다.
- [x] `backend/core/state_models.py`의 `OrderResult` 모델을 읽는다.
- [x] 현재 `OrderResult.success`가 어떤 조건으로 결정되는지 확인한다.
- [x] 현재 MT5 raw response가 어디에서 사라지는지 확인한다.
- [x] `ticket=0`, `executed_price=0.0`이 success로 기록되는 경로를 설명한다.
- [x] 이 단계 결과를 작업 보고에 남기되, 체크박스는 수정하지 않는다.

검증 명령:

```bash
rg -n "class OrderResult|OrderResult|execute_trade|order_send|retcode|ticket|executed_price|raw_response" backend
```

## Step 2: Define Live Execution Result Shape

목표: live/paper 공통으로 사람이 읽을 수 있는 execution detail shape을 정의합니다.

- [x] live execution detail에 포함할 필드를 정한다.
- [x] `mode`를 포함한다.
- [x] `symbol`을 포함한다.
- [x] `action`을 포함한다.
- [x] `requested_lot`을 포함한다.
- [x] `requested_entry_price`를 포함한다.
- [x] `requested_sl`을 포함한다.
- [x] `requested_tp`를 포함한다.
- [x] `risk_pct`를 포함한다.
- [x] `safe_lot`을 포함한다.
- [x] `mt5_retcode`를 포함한다.
- [x] `mt5_comment`를 포함한다.
- [x] `mt5_order`를 포함한다.
- [x] `mt5_deal`을 포함한다.
- [x] `mt5_price`를 포함한다.
- [x] `mt5_request_id`를 포함한다.
- [x] `raw_response`를 포함한다.
- [x] `success`를 포함한다.
- [x] `failure_reason`을 포함한다.
- [x] paper execution에도 가능한 범위에서 같은 key shape을 맞춘다.
- [x] 이 shape은 event payload와 snapshot에 같은 의미로 저장되게 한다.

권장 shape:

```json
{
  "mode": "live",
  "symbol": "BTCUSD",
  "action": "BUY",
  "requested_lot": 0.01,
  "requested_entry_price": 78347.07,
  "requested_sl": 78000.0,
  "requested_tp": 79000.0,
  "risk_pct": 0.001,
  "safe_lot": 0.01,
  "mt5_retcode": 10009,
  "mt5_comment": "Request executed",
  "mt5_order": 123456,
  "mt5_deal": 123457,
  "mt5_price": 78350.0,
  "mt5_request_id": 42,
  "raw_response": {},
  "success": true,
  "failure_reason": null
}
```

## Step 3: Tighten MT5 Success Predicate

목표: live execution이 성공인지 판단하는 순수 helper를 추가합니다.

- [x] MT5 live result 성공 판정 helper를 추가한다.
- [x] helper는 가능하면 pure function으로 둔다.
- [x] helper는 MT5 성공 retcode만 성공 후보로 인정한다.
- [x] helper는 `order`, `deal`, `ticket` 중 하나 이상이 양수인지 확인한다.
- [x] helper는 `executed_price` 또는 MT5 price가 양수인지 확인한다.
- [x] helper는 실패 시 사람이 읽을 수 있는 `failure_reason`을 반환한다.
- [x] helper는 `ticket=0`인 결과를 실패로 판정한다.
- [x] helper는 `executed_price=0.0`인 결과를 실패로 판정한다.
- [x] helper 단위 테스트를 추가한다.

테스트 케이스:

- [x] 성공 retcode + 유효 ticket + 유효 price는 success.
- [x] 성공 retcode + `ticket=0`은 failure.
- [x] 성공 retcode + `executed_price=0.0`은 failure.
- [x] 실패 retcode는 failure.
- [x] raw response가 누락되어도 failure reason이 남는다.

권장 테스트 명령:

```bash
env PYTHONPATH=. .venv/bin/pytest tests/test_execution_interceptor.py -q
env PYTHONPATH=. .venv/bin/pytest tests/test_trigger_system.py -q -k "order_failed or live"
```

## Step 4: Preserve MT5 Raw Response

목표: MT5 adapter/usecase에서 받은 원본 응답을 trigger event와 snapshot까지 전달합니다.

- [x] `MT5Client`가 가능한 원본 MT5 응답 필드를 보존하는지 확인한다.
- [x] `TradeExecutionUseCase.execute_trade()`가 raw response를 버리지 않게 한다.
- [x] `OrderResult`에 raw response를 담을 필드가 있는지 확인한다.
- [x] 필요하면 `OrderResult`에 `raw_response` 또는 `execution_details` 필드를 추가한다.
- [x] live execution result를 `trading_service.py`에서 structured execution detail로 변환한다.
- [x] MT5 retcode/comment/order/deal/price/request_id를 event payload에 저장한다.
- [x] 동일 payload를 snapshot의 `guardrail_result.execution_details` 또는 별도 일관된 위치에 저장한다.
- [x] 실패한 live execution도 raw response가 snapshot에 남는지 테스트한다.
- [x] 성공한 live execution도 raw response가 snapshot에 남는지 테스트한다.

주의:

- [x] raw response가 Pydantic/JSON 직렬화 가능한지 확인한다.
- [x] MT5 객체가 tuple/namedtuple이면 dict로 변환한다.
- [x] 민감 정보가 있다면 계정 비밀번호/token은 저장하지 않는다.

## Step 5: Fix Trading Service Success/Failure Recording

목표: live execution 결과가 불확실하면 성공으로 기록하지 않습니다.

- [x] `mode == "live"` 분기에서 엄격한 success predicate를 사용한다.
- [x] live 실패 시 `order_acked`를 남기지 않는다.
- [x] live 실패 시 `order_failed` event를 남긴다.
- [x] live 실패 시 `trigger_runs.status="failed"`로 남긴다.
- [x] live 실패 시 `error_message`에 failure reason을 남긴다.
- [x] live 실패 시 snapshot에 execution details를 남긴다.
- [x] live 성공 시에만 `order_acked` event를 남긴다.
- [x] live 성공 시에만 `track_open_position()`을 호출한다.
- [x] paper execution 기존 동작이 깨지지 않는지 테스트한다.

회귀 테스트:

- [x] paper success는 기존처럼 success로 남는다.
- [x] paper order failure는 `order_failed`와 snapshot execution detail을 남긴다.
- [x] live ticket 0 result는 failed로 남는다.
- [x] live price 0 result는 failed로 남는다.
- [x] live valid ticket/price result만 success로 남는다.
- [x] live failure에서는 `track_open_position()`이 호출되지 않는다.
- [x] live success에서는 `track_open_position()`이 호출된다.

## Step 6: Add API-Level Inspection Tests

목표: 운영자가 API만 보고 live execution 결과를 판단할 수 있음을 테스트합니다.

- [x] failed live execution의 `/events`에 `order_failed`가 있는지 테스트한다.
- [x] failed live execution의 `/snapshot`에 `execution_details.raw_response`가 있는지 테스트한다.
- [x] failed live execution의 `/snapshot`에 `failure_reason`이 있는지 테스트한다.
- [x] success live execution의 `/events`에 `order_acked`가 있는지 테스트한다.
- [x] success live execution의 `/snapshot`에 ticket/deal/price가 있는지 테스트한다.
- [x] `/history`에서 `status=failed`, `mode=live`, `symbol=BTCUSD` 필터로 조회되는지 테스트한다.

권장 테스트 명령:

```bash
env PYTHONPATH=. .venv/bin/pytest tests/test_trigger_system.py -q -k "live or snapshot or events"
```

## Step 7: Update Documentation Before Live Retry

목표: 다시 live smoke를 하기 전에 성공 판정 기준을 문서화합니다.

- [x] `docs/roadmap/004-ma-crossover-live-smoke-test-plan.md`에 체결 성공 판정 기준을 추가한다.
- [x] `ticket=0`은 성공으로 보지 않는다고 명시한다.
- [x] `executed_price=0.0`은 성공으로 보지 않는다고 명시한다.
- [x] MT5 Trade/History 탭 확인을 필수 단계로 명시한다.
- [x] `events`에서 `order_acked` payload를 확인하는 절차를 추가한다.
- [x] `snapshot`에서 execution details를 확인하는 절차를 추가한다.
- [x] live smoke 중 rule을 enable한 뒤 1회 실행 후 disable하는 절차를 유지한다.
- [x] 이 문서의 체크박스는 수정하지 않는다.

## Step 8: Add Structured Debug Logging

목표: 운영자가 로그만 따라가도 "왜 매매를 하지 않았는지", "어디서 매매가 막혔는지", "MT5 주문이 실제로 어떻게 응답했는지"를 추적할 수 있게 합니다.

- [x] `print()` 기반 런타임 로그를 `logging`으로 교체한다.
- [x] 새 코드에는 `print()`를 추가하지 않는다.
- [x] 기존 workflow/scheduler/trading service의 주요 `print()`를 logger로 전환한다.
- [x] logger name은 모듈 경로 기준으로 사용한다: `logging.getLogger(__name__)`.
- [x] 모든 live execution 로그에는 `trigger_id`를 포함한다.
- [x] 모든 live execution 로그에는 `workflow_run_id`를 포함한다.
- [x] 모든 scheduler 로그에는 `rule_id`를 포함한다.
- [x] 모든 주문 판단 로그에는 `symbol`, `mode`, `strategy_override`를 포함한다.
- [x] 모든 주문 판단 로그에는 최종 `action`을 포함한다.
- [x] 모든 차단 로그에는 `blocked_stage`를 포함한다.
- [x] 모든 실패 로그에는 `failure_reason`을 포함한다.
- [x] MT5 주문 요청 직전 structured log를 남긴다.
- [x] MT5 원본 응답 직후 structured log를 남긴다.
- [x] success predicate 판정 결과 structured log를 남긴다.
- [x] guardrail reject structured log를 남긴다.
- [x] strategy validator reject structured log를 남긴다.
- [x] risk lot 계산 structured log를 남긴다.
- [x] HOLD/WAIT 결정 structured log를 남긴다.
- [x] scheduler skip structured log를 남긴다: `lock_skip`, `market_hours_skip`, `not_due`.
- [x] 민감 정보는 로그에 남기지 않는다: password, token, API key.
- [x] account login/server는 운영 식별용으로 허용하되, 필요 시 masking 정책을 문서화한다.
- [x] 테스트에서 `caplog`로 핵심 로그가 남는지 검증한다.

권장 로그 event 이름:

- [x] `trigger.scheduler.rule_due`
- [x] `trigger.scheduler.rule_skipped`
- [x] `trigger.workflow.started`
- [x] `trigger.workflow.node_completed`
- [x] `trigger.workflow.completed`
- [x] `trigger.decision.hold`
- [x] `trigger.guardrail.rejected`
- [x] `trigger.strategy_validator.rejected`
- [x] `trigger.risk_lot.calculated`
- [x] `trigger.execution.requested`
- [x] `trigger.execution.mt5_response`
- [x] `trigger.execution.success_predicate`
- [x] `trigger.execution.acked`
- [x] `trigger.execution.failed`
- [x] `trigger.snapshot.saved`

## Step 9: Log Agent Outputs Without Hidden Reasoning

목표: 각 LLM agent가 어떤 결론을 냈는지 추적하되, 숨은 chain-of-thought를 저장하지 않습니다.

- [x] Tech Analyst의 structured output summary를 log/event/snapshot에 남긴다.
- [x] Strategist의 `selected_strategy`, `action`, `confidence`, 공개 reasoning 필드를 남긴다.
- [x] Chief Trader의 `action`, `entry`, `sl`, `tp`, `target_rr`, 공개 reasoning 필드를 남긴다.
- [x] LLM raw hidden reasoning이나 내부 chain-of-thought를 저장하지 않는다.
- [x] LLM prompt 전체를 기본 로그에 남기지 않는다.
- [ ] 필요한 경우 prompt hash 또는 prompt version만 남긴다.
- [ ] agent output은 너무 길면 요약본과 원본 snapshot 저장 위치를 분리한다.
- [x] trigger event payload에는 사람이 빠르게 볼 수 있는 요약을 남긴다.
- [x] trigger snapshot에는 상세 structured output을 남긴다.

### Step 9 Follow-up Rules

아래 두 항목은 트리거를 실제로 돌려서 검증할 수 있는 후속 규칙입니다.

- [ ] prompt hash/version 정책: agent prompt 원문은 저장하지 않고, `prompt_version` 또는 `prompt_hash`만 event/snapshot 메타데이터에 남긴다.
- [ ] output split 정책: 짧은 agent output은 event payload에 요약으로 남기고, 긴 structured output은 snapshot에만 상세로 남긴다.
- [ ] 검증 시에는 event payload에서 `prompt_version` 또는 `prompt_hash`가 있는지 확인한다.
- [ ] 검증 시에는 snapshot에서 상세 structured output과 요약본의 분리 여부를 확인한다.
- [ ] 검증 시에는 prompt 원문이나 hidden reasoning이 저장되지 않았는지 확인한다.
- [ ] 검증은 실제 live smoke가 아니라 mock trigger / paper trigger로 먼저 수행한다.

## Step 10: Design External Log Delivery

목표: 추후 Discord 같은 메신저로 주요 운영 이벤트를 흘려보낼 수 있는 구조를 마련합니다.

초기 구현은 app code가 Discord에 직접 의존하지 않는 형태가 좋습니다. Python은 structured log를 남기고, log shipper가 외부 sink로 전달하는 구조를 우선 검토합니다.

- [x] Python app은 structured JSON log를 stdout 또는 파일로 남긴다.
- [x] log schema에 `event`, `level`, `trigger_id`, `workflow_run_id`, `rule_id`, `symbol`, `mode`, `status`, `failure_reason`을 포함한다.
- [x] Discord 전송은 app core가 아니라 별도 adapter/sink로 분리한다.
- [x] Discord는 raw TCP가 아니라 webhook HTTP 전송을 기본 후보로 둔다.
- [x] Vector.dev, Fluent Bit, 또는 별도 lightweight notifier 중 하나를 선택한다.
- [x] warning/error/order_submitted/order_failed/order_acked 같은 중요 event만 알림 대상으로 둔다.
- [x] node_completed 같은 noisy event는 Discord 기본 전송에서 제외한다.
- [x] 알림 rate limit과 중복 억제 정책을 둔다.
- [x] 민감 정보 masking을 sink 직전에도 적용한다.
- [x] Discord 전송 실패가 trading workflow를 실패시키지 않게 한다.
- [x] 알림 sink는 테스트에서 mock 처리한다.

권장 1차 구조:

```text
FastAPI / scheduler / trading_service
  -> structured logging(JSON)
  -> local file or stdout
  -> log shipper(Vector.dev or notifier process)
  -> Discord webhook
```

주의:

- [x] "vector로 로그를 쌓는다"는 표현은 vector database가 아니라 log shipper인 Vector.dev 같은 도구를 의미하는지 명확히 한다.
- [x] Discord는 TCP sink가 아니라 webhook HTTP sink가 현실적이다.
- [x] 운영 알림과 장기 검색용 로그 저장은 분리한다.

## Step 11: Verification Commands

목표: 구현이 끝난 뒤 작업 AI가 실행해야 하는 검증 명령을 고정합니다.

- [x] targeted execution tests를 실행한다.
- [x] trigger system tests를 실행한다.
- [x] full test suite를 실행한다.
- [x] 테스트 결과를 최종 보고에 그대로 적는다.
- [x] 테스트 실패가 있으면 체크 완료를 주장하지 않는다.

필수 명령:

```bash
env PYTHONPATH=. .venv/bin/pytest tests/test_execution_interceptor.py -q
env PYTHONPATH=. .venv/bin/pytest tests/test_trigger_system.py -q
make test
```

## Step 12: Manual Review Checklist For Us

아래 항목은 작업 AI가 아니라 우리가 확인하고 체크합니다.

- [x] 작업 AI가 이 문서 체크박스를 수정하지 않았는지 확인한다.
- [x] `ticket=0`, `executed_price=0.0` live result가 failed로 남는지 확인한다.
- [x] valid live mock result가 success로 남는지 테스트로 확인한다.
- [x] `/events` payload가 운영자가 읽을 수 있을 만큼 충분한지 확인한다.
- [x] `/snapshot` execution details가 raw response를 포함하는지 확인한다.
- [x] `track_open_position()`이 실패 주문에서 호출되지 않는지 확인한다.
- [x] `docs/roadmap/004-ma-crossover-live-smoke-test-plan.md`가 새 성공 기준을 설명하는지 확인한다.
- [x] runtime `print()`가 logger로 교체됐는지 확인한다.
- [x] HOLD, blocked, failed, order_failed, order_acked 흐름을 로그만 보고 설명할 수 있는지 확인한다.
- [x] agent structured output이 event/snapshot에 남고 hidden reasoning은 저장되지 않는지 확인한다.
- [x] Discord/webhook 전송 설계가 core trading path와 분리되어 있는지 확인한다.
- [x] `make test` 결과를 확인한다.
- [x] 검증 후 필요한 항목만 이 문서에서 `[x]`로 갱신한다.

## Step 13: Live Smoke Retry Gate

아래 조건이 모두 충족되기 전에는 live smoke를 다시 진행하지 않습니다.

- [x] live execution success predicate가 엄격해졌다.
- [x] MT5 raw response가 event와 snapshot에 남는다.
- [x] ticket 0 / price 0 회귀 테스트가 있다.
- [x] failed live execution이 success로 표시되지 않는다.
- [x] 주요 live decision/execution 흐름이 structured log로 남는다.
- [x] Discord 같은 외부 알림은 최소 설계가 끝났거나, 이번 범위 밖이면 명시적으로 보류됐다.
- [x] `make test`가 통과한다.
- [ ] 사람이 live demo smoke 재시도를 명시 승인한다.

승인 후 live smoke는 `docs/roadmap/004-ma-crossover-live-smoke-test-plan.md` 기준으로 진행합니다.

## Related Docs

- [002-trigger-scheduler-roadmap.md](002-trigger-scheduler-roadmap.md)
- [004-ma-crossover-live-smoke-test-plan.md](004-ma-crossover-live-smoke-test-plan.md)
- [../architecture/trading-execution-flow.md](../architecture/trading-execution-flow.md)
- [../guides/live-operation-runbook.md](../guides/live-operation-runbook.md)
- [../storage/sqlite-storage.md](../storage/sqlite-storage.md)
