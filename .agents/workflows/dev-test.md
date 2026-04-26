---
description: TDD 기반 코드 변경 및 pytest 검증 워크플로우
---
# Agentic Trader: Development & Test Workflow

이 워크플로우는 코드를 수정하거나 새로운 기능을 추가할 때 적용하는 표준 검증 절차입니다. 프로젝트 공통 규칙은 root `AGENTS.md`를 우선합니다.

## 1. 컨텍스트 확인
작업 전 아래 문서를 읽고 현재 상태를 확인합니다.

Run: `git status --short`

필수 참조:
- `AGENTS.md`
- `README.md`
- `docs/mvp-implementation-plan.md`
- 변경 영역과 관련된 테스트 파일

## 2. 실패 테스트 먼저 작성
기능 변경, 버그 수정, guardrail/validator/order/state 변경은 먼저 실패하는 테스트를 작성하거나 기존 테스트로 실패를 재현합니다.

문서 변경, dead-file 정리, ignore/CI 같은 메타 변경처럼 테스트 선행이 의미 없는 경우에는 최종 보고에 예외 사유를 남깁니다.

## 3. 최소 구현
테스트를 통과시키는 최소 변경을 적용합니다.

주의:
- LLM이 직접 주문/지표/리스크 계산을 담당하게 만들지 않습니다.
- 새 전략은 `docs/trading-strategies/`, `backend/config/strategies_config.json`, `backend/features/trading/strategy_validators.py`를 함께 고려합니다.
- 과도한 범용 추상화보다 `backend/features/<domain>` 수직 슬라이스와 Pydantic state를 우선합니다.

## 4. 전체 검증
Run: `make test`

실패하면 원인을 분석하고 테스트 또는 구현을 수정한 뒤 다시 실행합니다.

## 5. Handoff
최종 보고에는 아래를 포함합니다.

- 수정/삭제/추가한 주요 파일
- 실행한 테스트 명령과 결과
- TDD 선행 테스트를 생략했다면 그 이유
- 다음 세션이 알아야 할 보류 사항
