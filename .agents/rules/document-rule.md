---
trigger: always_on
---

# Agentic Trader Documentation Rule

이 문서는 Agentic Trader 저장소의 문서 생성, 이동, 갱신 규칙 SSOT입니다. 새 AI 세션이 문서를 만들거나 정리할 때는 `AGENTS.md`, `.agents/rules/project-rule.md`와 함께 이 파일을 읽고 따릅니다.

## 1. Documentation Roles

Root `README.md`
: 프로젝트 설명, 설치/실행 사용법, 핵심 문서 링크만 둡니다. 상세 로드맵, 연구 결론, 긴 운영 절차를 계속 누적하지 않습니다.

`AGENTS.md`
: 새 AI 세션이 반드시 지켜야 하는 프로젝트 원칙과 규칙 파일 경로를 짧게 명시합니다. 세부 문서 배치 규칙은 이 파일에 둡니다.

`docs/README.md`
: 사람이 읽는 전체 문서 지도와 "새 문서 어디에 둘지" 결정표입니다. 새 문서를 만들거나 이동하면 이 색인을 함께 갱신합니다.

## 2. Placement Rules

새 문서는 아래 기준으로 배치합니다. root `docs/*.md`에는 새 문서를 만들지 않습니다. 예외는 `docs/README.md`뿐입니다.

```text
docs/
├── README.md                 # 문서 지도와 placement table
├── architecture/             # 시스템 설계, 철학, 실행 흐름 reference
├── guides/                   # 사람이 그대로 따라 하는 실행 절차
├── roadmap/                  # 현재 상태, 다음 목표, 단계별 계획
├── research/                 # 실험 결과, 전략 비교, 보류 이유
├── storage/                  # DB/schema/data reference
├── strategy/                 # 전략 작성/등록/승격 방법론
└── trading-strategies/       # LangGraph 런타임이 읽는 전략 지식
```

배치 기준:

- 앞으로 할 일, phase, 구현 계획, live smoke 계획은 `docs/roadmap/`에 둡니다.
- 사용자가 명령어를 따라 실행하는 절차는 `docs/guides/`에 둡니다.
- 백테스트/quant 결과, 전략 비교, 실험 결론, 보류 이유는 `docs/research/`에 둡니다.
- 전략을 어떻게 작성/등록/승격할지에 대한 방법론은 `docs/strategy/`에 둡니다.
- LLM 런타임에 주입되는 공식 전략 설명서만 `docs/trading-strategies/`에 둡니다.
- DB 테이블, 저장소 원칙, schema reference는 `docs/storage/`에 둡니다.
- 설계 철학, 시스템 흐름, agent workflow는 `docs/architecture/`에 둡니다.

## 3. Roadmap Numbering

`docs/roadmap/` 파일은 읽는 순서를 알 수 있도록 세 자리 prefix를 붙입니다.

예:

```text
001-mvp-roadmap.md
002-trigger-scheduler-roadmap.md
003-operations-ux-roadmap.md
004-ma-crossover-live-smoke-test-plan.md
```

규칙:

- 번호는 사람이 읽을 순서입니다. 시간순 commit 번호가 아닙니다.
- 새 roadmap을 추가할 때는 기존 순서를 고려해 다음 번호를 사용합니다.
- 번호를 바꾸면 `docs/README.md`와 모든 문서 링크를 함께 갱신합니다.
- roadmap 문서는 "현재 상태", "다음 작업", "완료 기준" 위주로 유지합니다.

## 4. Document Size and Shape

- 문서는 기본적으로 100~180줄 안쪽을 목표로 합니다.
- 200줄을 넘으면 분리를 검토합니다.
- 긴 명령 절차는 `docs/guides/`로 분리합니다.
- 긴 실험 근거와 결과는 `docs/research/`로 분리합니다.
- 로드맵에는 상세 로그를 쌓지 말고, 결론과 다음 행동만 남깁니다.
- 새 문서의 시작에는 가능하면 목적을 1~3문장으로 적습니다.

권장 구조:

```markdown
# Title

이 문서가 답하는 질문을 짧게 적습니다.

## Current State

현재 사실과 제약을 적습니다.

## Next Actions

다음 작업을 적습니다.

## Done Criteria

완료 기준을 적습니다.

## Related Docs

관련 문서를 링크합니다.
```

## 5. Runtime Strategy Documents

`docs/trading-strategies/`는 일반 문서 폴더가 아니라 LangGraph가 읽는 runtime strategy knowledge base입니다.

규칙:

- 이 폴더는 코드 패키지로 옮기지 않습니다.
- 전략 문서를 이동하려면 `backend/workflows/nodes.py`, `backend/config/strategies_config.json`, agent prompt, 문서 링크를 함께 갱신해야 합니다.
- 새 runtime 전략은 반드시 `backend/config/strategies_config.json` 등록, deterministic validator, 테스트와 한 세트로 다룹니다.
- 연구용 baseline 설명은 `docs/research/` 또는 `docs/strategy/`에 두고, 주문 가능한 전략 설명서만 `docs/trading-strategies/`에 둡니다.

## 6. Update Discipline

문서를 만들거나 이동할 때:

1. `docs/README.md` 색인을 갱신합니다.
2. 기존 경로 참조를 `rg`로 찾고 링크를 갱신합니다.
3. 코드가 문서 경로를 직접 참조하는지 확인합니다.
4. 문서-only 변경이면 선행 실패 테스트는 생략할 수 있지만, 최종 응답에 생략 사유와 링크 검증 결과를 남깁니다.
5. 코드 참조를 바꿨다면 관련 테스트 또는 `make test`를 실행합니다.

