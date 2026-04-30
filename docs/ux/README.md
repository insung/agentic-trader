# UX Planning Index

이 디렉터리는 사람이 Agentic Trader를 수동으로 이해하고 조작할 수 있게 만드는 운영 UX 계획을 모읍니다.

`docs/mvp-implementation-plan.md`는 전체 프로젝트의 상위 로드맵이고, 이 디렉터리는 그중 운영 콘솔, 전략 워크벤치, 백테스트 랩, 의사결정 감사 화면의 세부 실행 계획입니다.

## 읽는 순서

새 AI 세션이 UX/API/대시보드 작업을 맡으면 아래 순서로 읽습니다.

1. `AGENTS.md`
2. `docs/mvp-implementation-plan.md`
3. `docs/ux/README.md`
4. `docs/ux/operations-ux-roadmap.md`
5. `docs/storage/sqlite-schema-reference.md`
6. `backend/config/strategies_config.json`
7. `backend/features/trading/strategy_validators.py`

## MVP와의 관계

- [ ] Phase 6.5는 UX보다 먼저 안정화해야 할 데이터 기반입니다.
  - 백테스트 run, trade, decision이 SQLite에 구조화되어 있어야 합니다.
  - LLM 응답 캐시와 deterministic replay는 빠른 반복 UX의 기반입니다.
- [ ] Phase 6.6은 Strategy Workbench와 Guardrail Center가 참조할 정책 기반입니다.
  - 전략별 파라미터, 최소 표본 수, blocked-trade audit 기준을 정합니다.
- [ ] Phase 9에서 `docs/ux/operations-ux-roadmap.md`를 따라 실제 API/UI를 구현합니다.
  - 먼저 읽기 전용 API를 만들고, 그 다음 최소 UI를 붙입니다.
  - Paper/Live 승격 UI는 마지막 단계입니다.

## 권장 구현 순서

- [ ] 1. `GET /api/v1/ops/strategies` 읽기 전용 API를 만듭니다.
  - 전략 문서 frontmatter, `strategies_config.json`, validator 지원 여부를 한 응답으로 묶습니다.
- [ ] 2. `GET /api/v1/backtests/runs`와 run 상세 조회 API를 만듭니다.
  - 최근 백테스트 결과를 UI 없이도 일관되게 볼 수 있게 합니다.
- [ ] 3. `GET /api/v1/backtests/runs/{run_id}/decisions`를 만듭니다.
  - Decision Audit의 데이터 기반을 만듭니다.
- [ ] 4. `GET /api/v1/ops/summary`를 만듭니다.
  - Board Console 첫 화면의 요약 데이터를 제공합니다.
- [ ] 5. 최소 UI를 붙입니다.
  - Board Console, Strategy Workbench, Backtest run 목록, Decision Audit 읽기 전용 화면부터 시작합니다.
- [ ] 6. Backtest Lab 실행 API/UI를 붙입니다.
  - 실행 기능은 읽기 전용 조회보다 위험도가 높으므로 뒤로 둡니다.
- [ ] 7. Guardrail Center와 strategy 승격 모델을 붙입니다.
  - `draft -> registered -> validated -> backtested -> paper_enabled -> live_enabled` 흐름을 UI에 반영합니다.
- [ ] 8. Telegram/Discord/Email 중 하나로 운영 알림을 붙입니다.

## 다음 AI 세션의 첫 작업 후보

가장 작은 첫 작업은 `GET /api/v1/ops/strategies`입니다.

완료 기준:

- [ ] `docs/trading-strategies/*.md`의 frontmatter를 읽습니다.
- [ ] `backend/config/strategies_config.json` 등록 여부를 표시합니다.
- [ ] `backend/features/trading/strategy_validators.py`가 해당 전략명을 지원하는지 표시합니다.
- [ ] 전략별 상태를 `draft`, `registered`, `validated` 중 하나로 계산합니다.
- [ ] 테스트를 추가합니다.
- [ ] `make test`를 실행합니다.

## 문서 목록

- [Operations UX Roadmap](./operations-ux-roadmap.md)
