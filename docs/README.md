# Docs Index

이 문서는 Agentic Trader의 전체 문서 지도이자 새 문서를 어디에 둘지 결정하는 placement table입니다. 문서 생성/이동 규칙의 SSOT는 `.agents/rules/document-rule.md`입니다.

## Placement Table

| 만들 문서 | 위치 | 예시 |
| --- | --- | --- |
| 현재 상태, 다음 목표, phase, 구현 계획 | `docs/roadmap/` | `001-mvp-roadmap.md` |
| 사람이 따라 하는 실행 절차 | `docs/guides/` | `execution-guide.md` |
| 실험 결과, quant 비교, 보류 이유 | `docs/research/` | `quant-research-next-steps.md` |
| 전략 작성/등록/승격 방법론 | `docs/strategy/` | `strategy-addition-mechanism.md` |
| LLM 런타임에 주입되는 공식 전략 설명서 | `docs/trading-strategies/` | `ma_crossover.md` |
| DB, schema, replayable data reference | `docs/storage/` | `sqlite-schema-reference.md` |
| 시스템 철학, 아키텍처, workflow reference | `docs/architecture/` | `system-execution-flow.md` |

새 문서를 만들거나 이동하면 이 파일의 링크를 함께 갱신합니다. root `docs/*.md`에는 새 문서를 만들지 않습니다. 예외는 이 파일뿐입니다.

## Architecture

- [Vision and Philosophy](./architecture/vision-and-philosophy.md)
- [System Execution Flow](./architecture/system-execution-flow.md)
- [Trading Execution Flow](./architecture/trading-execution-flow.md)
- [External Log Delivery](./architecture/external-log-delivery.md)
- [Agent Workflow Design](./architecture/agent-workflow-design.md)
- [Safety Guardrails](./architecture/safety-guardrails.md)
- [AI Trading Reference](./architecture/ai-trading-reference.md)

## Guides

- [Execution Guide](./guides/execution-guide.md)
- [Live Operation Runbook](./guides/live-operation-runbook.md)
- [Testing Guide](./guides/testing-guide.md)
- [MetaTrader 5 Notes](./guides/meta-trader5.md)
- [Backtesting Guide](./guides/backtesting-guide.md) - 실행 절차, `RISK_PCT`, 빠른 진단 실행, JSONL 관측 로그

## Storage

- [SQLite Storage Guide](./storage/sqlite-storage.md)
- [SQLite Schema Reference](./storage/sqlite-schema-reference.md)
- [Replayable Trading Data](./storage/replayable-trading-data.md)

## Strategy

- [Trading Strategy Guide](./strategy/trading-strategy.md)
- [MTF Strategy Guide](./strategy/mtf-strategy-guide.md)
- [Strategy Addition Mechanism](./strategy/strategy-addition-mechanism.md)
- [Strategy Document Template](./strategy/strategy-document-template.md)
- [Runtime Strategy Documents](./trading-strategies/)

## Research

- [Strategy Research Pivot](./research/strategy-research-pivot.md)
- [Quant Research Next Steps](./research/quant-research-next-steps.md)
- [RSI Trend Pullback Research](./research/rsi_trend_pullback_0503.md)

## Roadmap

- [001 MVP Roadmap](./roadmap/001-mvp-roadmap.md)
- [002 Trigger Scheduler Roadmap](./roadmap/002-trigger-scheduler-roadmap.md)
- [003 Operations UX Roadmap](./roadmap/003-operations-ux-roadmap.md)
- [004 MA Crossover Live Smoke Test Plan](./roadmap/004-ma-crossover-live-smoke-test-plan.md)
- [005 Live Execution Observability Roadmap](./roadmap/005-live-execution-observability-roadmap.md)

## UX

- [UX Planning Index](./ux/README.md)
