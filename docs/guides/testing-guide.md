# Testing Guide

Agentic Trader의 테스트는 MT5가 없는 Linux native Python 환경에서도 안전하게 실행될 수 있어야 합니다. MT5/Wine이 필요한 검증은 별도 운영 절차로 분리합니다.

## Prerequisites

1. `.venv` 가상 환경이 준비되어 있어야 합니다.
2. 처음 실행하는 환경에서는 의존성을 설치합니다.

```bash
make install
```

## Standard Test Command

모든 코드 변경 후 기본 검증 명령은 다음 하나입니다.

```bash
make test
```

성공 기준:

- 모든 단위/통합 테스트가 통과합니다.
- MT5 패키지가 없는 native Linux 환경에서는 MT5 연결 테스트가 skip될 수 있습니다.
- Guardrail, validator, LangGraph routing, LLM node mock, position tracking 테스트가 깨지지 않아야 합니다.

## TDD Gate

코드 변경은 root `AGENTS.md`의 TDD gate를 따릅니다.

1. 실패 테스트를 먼저 작성하거나 기존 테스트로 실패 조건을 재현합니다.
2. 실패를 확인합니다.
3. 최소 구현으로 테스트를 통과시킵니다.
4. `make test`를 실행합니다.
5. 실행한 테스트 명령과 결과를 handoff에 남깁니다.

문서 정리, 파일 이동, CI 설정처럼 테스트 선행이 의미 없는 변경은 예외 사유를 기록합니다.

## What To Test By Change Type

- **Guardrail / order execution:** `tests/test_guardrails.py`, `tests/test_execution_interceptor.py`
- **Strategy validator:** `tests/test_strategy_validators.py`
- **LangGraph routing:** `tests/test_filter_routing.py`, `tests/test_end_to_end.py`
- **LLM node behavior:** `tests/test_nodes_llm.py`, `tests/test_retry_logic.py`
- **Position tracking / reviews:** `tests/test_position_tracker.py`
- **Backtest persistence / observability:** `tests/test_backtest_store.py`, `tests/test_backtest_observability.py`, `tests/test_sqlite_backtest_loader.py`
- **CLI/API payload contract:** `tests/test_trade_cli.py`

## Backtest Observability Checks

백테스트 속도나 수익률 분석용 로깅을 변경할 때는 다음 항목을 확인합니다.

```bash
make test
```

중점 확인:

- `MAX_STEPS` 또는 `--max-steps`가 실제 LangGraph 호출 수를 제한해야 합니다.
- `START_STEP` 또는 `--start-step`이 처음 N개 판단 지점을 건너뛰어야 합니다.
- `NO_REVIEW=1` 또는 `--no-review`가 청산 후 Risk Reviewer LLM 호출을 생략해야 합니다.
- `LOG_LEVEL` 또는 `--log-level`이 지정 레벨보다 낮은 JSONL 이벤트를 제외해야 합니다.
- JSONL 로그에는 `backtest_start`, `node_complete`, `decision_recorded`, `step_complete`, `backtest_complete` 같은 핵심 이벤트가 남아야 합니다.
- 로그에는 전체 prompt/OHLCV 원문을 반복 저장하지 말고, `run_id`, `step`, `candle_time`, `elapsed_ms`, `status`, `rejection_reason`, `trade_id`처럼 분석 가능한 작은 필드를 남깁니다.
- 생성 로그는 `backtests/` 아래에 있어야 하며 Git에 추적하지 않습니다.

## CI

GitHub Actions runs `make test` on push and pull request via `.github/workflows/test.yml`.

## Troubleshooting

- `MetaTrader5` import failure on Linux native Python is expected unless running through Wine Python.
- If `make test` cannot find project modules, verify `PYTHONPATH=.` is set through the Makefile.
- If a test writes generated state, ensure generated data stays under ignored paths such as `trading_logs/`, `backtests/`, or pytest cache directories.
