# Trigger Scheduling Plan

이 문서는 `make trigger`를 사람이 직접 호출하는 방식에서, FastAPI 내부 스케줄과 별도 DB 저장을 통해 자동 트리거 이력을 관리하는 계획을 정리합니다.

목표는 다음과 같습니다.

- FastAPI `lifespan`에 스케줄러를 등록한다.
- 지정된 주기마다 `trigger` 워크플로우를 자동 실행한다.
- 각 트리거 실행의 입력/출력/상태를 별도 DB에 저장한다.
- 향후 UI에서 트리거 이력, 실행 결과, 차단 사유를 조회할 수 있게 한다.

## 1. 목표 범위

### 포함

- FastAPI 서버 시작 시 자동 스케줄 시작
- 서버 종료 시 스케줄 종료
- 트리거 실행 메타데이터 저장
- 실행 상태 저장
- 실패/차단/성공 이력 저장
- UI 조회용 API 설계

### 제외

- 지금 단계에서 복잡한 전략 자동 선택 로직 추가
- cron을 대체하는 외부 운영 문서 전면 교체
- UI 구현 자체
- 실시간 알림 시스템

## 2. 현재 상태

- `POST /api/v1/trade/trigger`는 1회 실행용이다.
- `make trigger`는 이 API를 수동 호출하는 래퍼다.
- `POSITION_RECONCILE_INTERVAL_SECONDS` 기반 reconcile loop는 이미 `lifespan`에 등록되어 있다.
- `MODE=paper` / `MODE=live`는 현재 수동 트리거 기반으로 동작한다.

즉, 스케줄 트리거는 아직 없다.

## 3. 구현 방향

### 3-1. FastAPI lifespan에 트리거 스케줄러를 등록

- 서버 시작 시 백그라운드 task를 하나 더 띄운다.
- reconcile loop와 별도로 trigger loop를 둔다.
- trigger loop는 심볼, 타임프레임, mode, 실행 간격을 읽어서 주기적으로 workflow를 호출한다.
- 서버 종료 시 task를 cancel 한다.

권장 방식:

- 처음에는 Python `asyncio` 기반의 단순 루프 사용
- 이후 필요하면 APScheduler 같은 전용 스케줄러로 교체

### 3-2. 별도 DB에 트리거 이력 저장

기존 trading log DB와 분리된 저장소를 둔다.

권장 테이블은 최소 4개다.

1. `trigger_runs`
2. `trigger_events`
3. `trigger_schedule_rules`
4. `trigger_execution_snapshots`

이 DB는 UI가 직접 읽는 source of truth가 된다.

#### trigger_runs

트리거 1회 실행을 기록한다.

필드 예시:

- `trigger_id`
- `rule_id`
- `workflow_run_id`
- `scheduled_at`
- `started_at`
- `finished_at`
- `duration_ms`
- `symbol`
- `timeframes_json`
- `mode`
- `strategy_override`
- `status`
- `workflow_status`
- `final_action`
- `error_message`
- `created_at`
- `updated_at`

권장 인덱스:

- `trigger_id` unique
- `status`
- `mode`
- `symbol`
- `scheduled_at`
- `finished_at`

#### trigger_events

트리거 실행 중 발생한 중간 이벤트를 기록한다.

필드 예시:

- `event_id`
- `trigger_id`
- `event_type`
- `node_name`
- `message`
- `payload_json`
- `created_at`

권장 event_type 값:

- `scheduled`
- `started`
- `market_snapshot_loaded`
- `tech_analysis_completed`
- `strategy_selected`
- `chief_trader_completed`
- `guardrail_rejected`
- `order_submitted`
- `order_failed`
- `order_acked`
- `reconcile_requested`
- `reconcile_completed`
- `finished`

권장 인덱스:

- `trigger_id`
- `event_type`
- `created_at`

#### trigger_schedule_rules

어떤 trigger를 언제 실행할지 정의한다.

필드 예시:

- `rule_id`
- `name`
- `enabled`
- `symbol`
- `timeframes_json`
- `mode`
- `strategy_override`
- `schedule_type`
- `cron_expression`
- `interval_seconds`
- `timezone`
- `market_hours_only`
- `last_triggered_at`
- `next_trigger_at`
- `created_at`
- `updated_at`

설명:

- `schedule_type`은 `interval` 또는 `cron` 중 하나로 시작한다.
- `cron_expression`은 cron 기반 실행에 사용한다.
- `interval_seconds`는 단순 주기 실행에 사용한다.
- `market_hours_only`는 종목별 장 운영 여부를 먼저 확인할지 나타낸다.

권장 인덱스:

- `enabled`
- `symbol`
- `next_trigger_at`

#### trigger_execution_snapshots

실행 당시의 입력/출력 payload를 원문에 가깝게 저장한다.

필드 예시:

- `snapshot_id`
- `trigger_id`
- `request_json`
- `initial_state_json`
- `final_state_json`
- `final_order_json`
- `decision_context_json`
- `guardrail_result_json`
- `strategy_snapshot_json`
- `created_at`

설명:

- `request_json`은 API 요청 원문이다.
- `initial_state_json`은 LangGraph 시작 상태다.
- `final_state_json`은 workflow 종료 상태다.
- `final_order_json`은 Chief Trader 출력이다.
- `decision_context_json`은 주문/판단 맥락이다.
- `guardrail_result_json`은 주문이 왜 통과/차단됐는지 설명한다.
- `strategy_snapshot_json`은 당시 주입된 전략 문서/registry 요약이다.

권장 인덱스:

- `trigger_id` unique 또는 indexed

### 3-3. 트리거와 실제 주문을 분리

자동 스케줄이 실행하는 것은 “트리거 이벤트”이고, 실제 주문 여부는 기존 LangGraph, Chief Trader, guardrail, validator가 결정한다.

즉:

- 스케줄러 = 언제 실행할지 결정
- LangGraph = 무엇을 할지 결정
- guardrail = 주문해도 되는지 최종 결정

## 4. 트리거 저장 시 필요한 항목

UI와 운영 로그를 위해 매 트리거마다 아래 항목을 남긴다.

- 식별자
  - `trigger_id`
  - `rule_id`
  - `workflow_run_id`

- 시간
  - `scheduled_at`
  - `started_at`
  - `finished_at`
  - `duration_ms`

- 입력
  - `symbol`
  - `timeframes`
  - `mode`
  - `strategy_override`

- 상태
  - `status`
  - `workflow_status`
  - `final_action`
  - `error_message`

- 판단 근거
  - `selected_strategy`
  - `selected_regime`
  - `market_snapshot`
  - `chief_trader_reasoning`
  - `guardrail_reason`

- 주문 결과
  - `entry_price`
  - `sl_price`
  - `tp_price`
  - `lot_size`
  - `order_result`

- 복기/후속
  - `reviewed_at`
  - `review_status`
  - `review_trade_id`

## 5. 스케줄 주기 설계

### 기본 원칙

- `M15` 전략은 15분 단위
- `M30` 전략은 30분 단위
- `H1` 전략은 1시간 단위
- trigger 시각은 캔들 마감 후 약간의 버퍼를 둔다

### 초기 구현 권장

- 하나의 scheduler loop가 모든 trigger rule을 읽는다.
- 각 rule은 `interval_seconds` 또는 `cron expression`으로 정의한다.
- 중복 실행 방지를 위해 동일 rule의 다음 실행은 이전 실행 완료 여부를 고려한다.
- 이미 running 상태인 rule은 중복 실행하지 않는다.
- `market_hours_only`가 켜진 rule은 장 운영 여부를 먼저 확인한다.

### 추천 실행 타이밍

- `M15` 전략: 캔들 마감 후 5~30초
- `M30` 전략: 캔들 마감 후 10~60초
- `H1` 전략: 캔들 마감 후 30~120초

이 버퍼는 브로커 데이터 지연과 서버 처리 지연을 흡수하기 위한 것이다.

## 6. 안전 장치

- 서버 시작 시 duplicate scheduler 등록을 막는다.
- 같은 rule이 겹쳐 실행되지 않도록 lock 또는 running flag를 둔다.
- MT5 미연결 상태에서는 live trigger를 자동 스킵하거나 paper로만 전환한다.
- trigger 실패는 DB에 반드시 기록한다.
- reconcile loop와 trigger loop는 독립적으로 실패 복구 가능해야 한다.
- scheduler가 죽으면 서버 시작 시 재생성한다.
- 동일 symbol에 열린 포지션이 있고 단일 포지션 정책이면 trigger를 건너뛸 수 있어야 한다.

## 7. 구현 순서

1. trigger DB 스키마 정의
2. scheduler loop 설계
3. lifespan 등록
4. trigger 실행 이력 저장
5. 조회 API 설계
6. UI에서 읽기 쉬운 요약 포맷 정의
7. 테스트 추가
8. paper 스케줄 smoke run
9. live 스케줄 smoke run

## 7-1. UI에서 보여줄 항목

향후 UI에서는 최소한 아래를 보여줘야 한다.

- 최근 trigger 실행 목록
- 오늘/이번 주/이번 달 실행 횟수
- status별 집계
- mode별 집계
- symbol/timeframe별 집계
- 마지막 successful trigger 시각
- 마지막 failed trigger 시각
- 마지막 order sent trigger 시각
- 마지막 guardrail reject 이유
- trigger 상세 타임라인
- trigger 클릭 시 request/final_state/final_order/guardrail raw JSON

추천 UI 화면:

- Trigger Dashboard
- Trigger Timeline
- Trigger Detail Drawer
- Schedule Rules Editor
- Live/Paper Status Panel

## 8. 완료 기준

- FastAPI 시작 시 스케줄러가 자동으로 뜬다.
- 종료 시 스케줄러가 안전하게 내려간다.
- trigger 실행마다 DB에 한 줄 이상 남는다.
- UI가 최근 실행/상태/결과를 조회할 수 있다.
- paper와 live를 분리해서 확인할 수 있다.
- 기존 manual `make trigger`는 디버그/수동 운영용으로 그대로 남는다.
- schedule rule을 추가/비활성화/삭제할 수 있다.
- 동일 trigger가 중복 실행되지 않는다.
- API 서버 재시작 후에도 schedule rule이 복구된다.

## 9. 현재 결론

이 단계의 목표는 `trigger`를 cron 대체 수준으로 자동화하는 것이 아니라, **트리거 실행 이력과 상태를 UI 친화적으로 보존하는 것**이다.

즉, 구현 우선순위는 다음과 같다.

1. FastAPI lifespan 스케줄러
2. 별도 trigger DB
3. 조회 API
4. UI

## 10. 현재 코드 기준 점검 결과

코드와 문서를 대조했을 때, 아래처럼 정리하는 것이 정확하다.

### 이미 구현된 것

- FastAPI `lifespan`에서 `scheduler.start()` / `scheduler.stop()`를 호출한다.
- `TriggerScheduler`가 백그라운드 루프로 동작한다.
- `trigger_runs`, `trigger_events`, `trigger_schedule_rules`, `trigger_execution_snapshots` 테이블이 있다.
- `POST /api/v1/triggers/rules`로 interval rule을 등록할 수 있다.
- `GET /api/v1/triggers/history`와 `GET /api/v1/triggers/rules`가 있다.
- `make trigger`는 여전히 수동 1회 실행 경로로 남아 있다.

### 아직 미완성인 것

- cron expression 기반 실행은 아직 실제로 사용되지 않는다.
  - 스키마에는 `cron_expression`이 있지만
  - API와 scheduler는 interval-only로 동작한다.
- 실패/차단 경로에서 `trigger_execution_snapshots`가 충분히 저장되지 않는다.
- `workflow_run_id`는 아직 사실상 비어 있다.
- `guardrail_result_json`은 성공 경로에서도 최소 정보만 저장한다.
- scheduler의 중복 실행 방지는 프로세스 로컬 lock에 의존한다.
- trigger rule CRUD는 생성/조회/토글까지만 있고, 삭제/세부 수정/next run 강제 갱신은 약하다.
- 테스트가 부족하다.

### 구현 확인 시 바로 잡아야 하는 오해

- `cleanup_trigger_history`는 이번 작업에서 새로 추가된 함수가 아니다.
  - 이미 `backend/features/trading/trigger_store.py`에 존재한다.
  - 따라서 “오래된 로그 삭제 기능을 새로 구현했다”는 표현은 부정확하다.
- 현재 시스템을 `production-ready`라고 부르는 것은 과장이다.
  - interval scheduler, DB 저장, 조회 API, snapshot 보강은 진전이다.
  - 그러나 cron 미구현, 단일 프로세스 락 의존, 테스트 부족 때문에 아직 운영 완성형은 아니다.
- 테스트 개수도 과장하면 안 된다.
  - 최근 trigger/execution 쪽 검증은 `7 passed`였다.
  - 전체 회귀는 `73 passed, 2 skipped`였다.

### 문서에 반드시 반영해야 하는 운영 전제

- 지금 자동 스케줄러는 **interval-based**로만 믿어야 한다.
- cron은 향후 확장 항목으로 적는다.
- 단일 프로세스 실행을 전제로 설계된 부분이 있으므로, 멀티 워커 운영은 별도 검증이 필요하다.

## 11. 지금 우리가 해야 할 일

이 계획을 실제 기능으로 굳히려면 다음 순서가 맞다.

### 1단계: 저장 안정화

가장 먼저 해야 할 일은 **모든 종료 경로가 DB에 일관되게 남도록 만드는 것**이다.

필수 작업:

- `guardrail_rejected` 분기에서도 snapshot 저장
- `order_failed` 분기에서도 snapshot 저장
- `failed` / `blocked` 상태의 `trigger_runs`에 공통 종료 메타데이터 저장
- `workflow_run_id` 또는 동등한 실행 식별자 채우기
- `guardrail_result_json`에 reject reason, validate result, risk info를 저장

이 단계가 먼저인 이유:

- UI가 가장 먼저 필요로 하는 것은 “왜 안 됐는가”이다.
- 현재는 성공/홀드보다 차단 이력의 정보 밀도가 부족하다.
- 실제 live 운영에서 가장 많이 보는 것은 주문 성공보다 차단/실패 원인이다.

현재 코드 기준으로는 이 단계가 대부분 반영되었다.
다만 유지보수 관점에서 다음을 계속 확인해야 한다.

- blocked / failed / exception 경로에서 snapshot이 항상 남는가
- `request_json`과 `final_state_json`이 비어 있지 않은가
- `workflow_run_id`가 run 간 충돌 없이 추적 가능한가
- `guardrail_result_json`이 단순 `success: true/false`를 넘어서 원인 분석에 충분한가

### 2단계: 테스트 추가

스케줄러는 백그라운드 task와 DB를 동시에 다루므로, 테스트가 없으면 회귀가 쉽게 생긴다.

필수 테스트:

- `trigger_store` 스키마 생성 테스트
- rule upsert / toggle / list 테스트
- `create_trigger_run` / `update_trigger_run` / `add_trigger_event` / `save_trigger_snapshot` 테스트
- `run_trading_workflow_async`가 HOLD / blocked / failed / success를 각각 남기는지 테스트
- scheduler가 실행 시간에 rule을 발견하고 trigger를 생성하는지 테스트
- `lifespan`이 scheduler start/stop을 호출하는지 테스트

권장 추가 테스트:

- `GET /api/v1/triggers/history`의 `status` / `symbol` 필터가 기대대로 동작하는지 테스트
- `GET /api/v1/triggers/{trigger_id}` / `events` / `snapshot`이 404와 성공 응답을 올바르게 구분하는지 테스트
- `cleanup_trigger_history`가 실제로 오래된 run / event / snapshot을 함께 지우는지 테스트
- rule toggle / delete가 DB 상태를 일관되게 바꾸는지 테스트

### 3단계: API를 UI 친화적으로 다듬기

현재 endpoint는 동작하지만, UI 관점에서 아직 단순하다.

개선 권장 사항:

- `GET /api/v1/triggers/history`에 `status`, `symbol`, `mode`, `rule_id` 필터 추가
- `GET /api/v1/triggers/rules`에 active/all 구분 추가
- `POST /api/v1/triggers/rules/{rule_id}/toggle` 대신 `PATCH` 계열로 정리
- trigger 상세 조회 endpoint 추가
- trigger timeline endpoint 추가
- raw snapshot endpoint 추가

### 4단계: cron 지원은 그 다음

cron은 계획에는 남기되, 실제 구현은 그 다음 단계가 맞다.

이유:

- 현재 interval-only로 이미 동작한다.
- cron은 parsing, timezone, market-hours, 중복 실행, 캔들 마감 버퍼를 추가로 설계해야 한다.
- cron을 먼저 넣으면 저장/조회/테스트가 약한 상태에서 복잡도만 올라간다.

즉, 지금 문서와 코드의 기준선은 다음과 같이 읽어야 한다.

- `interval_seconds` = 현재 실제 동작
- `cron_expression` = 향후 확장 가능성만 있는 필드
- 문서에 cron 예시를 넣을 경우 반드시 "향후 지원 예정"으로 표기해야 한다

### 5단계: UI는 trigger DB를 읽기만 하게 만든다

UI는 결정 로직을 가지면 안 된다.

UI가 읽어야 하는 것:

- 실행 목록
- rule 목록
- 실행 상세
- 차단/실패 이유
- raw snapshot

UI가 해서는 안 되는 것:

- 전략 선택
- 주문 판단
- guardrail 재계산

### 6단계: 운영 실험

문서상 자동화가 완성되기 전에 작은 범위로 운영 실험을 한다.

권장 실험 순서:

1. `MODE=paper` + interval rule 1개
2. 단일 symbol + 단일 timeframe
3. DB 이력/대시보드 확인
4. 차단 이유와 실제 전략 판단 비교
5. 그 다음에 `MODE=live` 데모 계좌 소규모 실행

## 12. 내가 추천하는 바로 다음 구현 순서

지금 시점에서 가장 효과적인 다음 작업은 아래 순서다.

1. `trigger_store`와 `trading_service`에서 실패/차단 경로의 snapshot 보강
2. `trigger_history` 조회 필터와 상세 API 추가
3. scheduler 중복 실행 및 rule 상태 테스트 추가
4. execution-guide에서 cron은 “향후 지원”으로 명시
5. paper smoke를 rule 기반으로 1개 돌려서 UI가 읽을 데이터가 실제로 남는지 확인
6. 그 다음 cron 지원 여부를 결정

## 13. 현재 다음 작업

지금 시점에서 가장 우선순위가 높은 작업은 아래 셋이다.

1. trigger 조회 API를 UI 친화적으로 정리
   - `history`, `detail`, `events`, `snapshot`의 응답 구조를 안정화
   - `status`, `symbol`, `rule_id`, `mode` 필터를 확장
2. trigger 저장 경로에 대한 회귀 테스트 보강
   - success / blocked / failed / exception 모두 검증
   - rule CRUD와 snapshot cleanup까지 포함
3. interval-only 운영 문서 고정
   - cron은 계획으로만 남기고 실제 운영 절차는 interval 기준으로만 적는다

이 세 가지가 끝나면 그때 cron 지원을 다시 검토하는 것이 맞다.
