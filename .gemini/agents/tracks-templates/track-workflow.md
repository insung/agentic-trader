# Track Management Protocol (v2.0)

AI 에이전트가 작업 트랙을 생성·관리·완료하는 표준 엔지니어링 프로토콜.

## Rule 1: Phase Management (7단계 생명주기)
모든 트랙은 아래 7단계를 순차적으로 수행한다. 에이전트는 채팅 응답 최상단에 아래 형식의 **Status Header**를 반드시 노출한다. (현재 진행 중인 단계에만 🚀 표시)

```markdown
---
TRACK: {트랙명}
GOAL:  {목표 요약}
PHASE: Brainstorming > Planning > Initializing > [ 🚀 CURRENT_PHASE ] > Review > Testing > Finalizing
---
```

1. **Brainstorming**: 요구사항 분석 및 설계(Spec) 수립
2. **Planning**: TDD 기반의 상세 구현 계획(`plan.md`) 및 원자적 단위(`todos/`) 분해 (Progress Bar의 기준)
3. **Initializing Track**: 트랙 디렉토리 초기화 및 현황판 등록
4. **Implementation**: TDD 사이클 반복을 통한 기능 구현
5. **Review**: 영향도 분석 및 **(권장)안이 포함된 선택지 기반 Grill-me 인터뷰**
6. **Testing**: 통합 테스트 및 최종 품질 검증
7. **Finalizing**: Closure Report 작성 및 지식 자산화 (LESSONS.md 업데이트)

## Rule 2: Single Source of Truth (SSOT)
- **plan.md**: 현재 작업의 모든 설계와 구현 단계를 담은 마스터 설계도.
- **audit.md**: 모든 기술적 의사결정의 맥락과 근거를 기록하는 블랙박스 로그. (User Instruction 원본 보존 필수)
- **todos/**: 원자적 구현 단위를 관리하며, 반드시 **`todo-template.md`** 형식을 따르고 모든 항목에 체크박스(`- [ ]`)를 포함해야 한다.
- **LESSONS.md**: 프로젝트 전체의 지혜가 담긴 오답 노트로, 리뷰 단계의 1순위 참조 대상.

## Rule 3: Global Persistence
- 트랙 데이터는 프로젝트 폴더를 오염시키지 않도록 사용자 홈 디렉토리(`~/.track/{project_name}/`) 하위에서 관리한다.
- 경로 구조: `YYYY-MM/{DD_HHMM_track_name}/`

## Rule 4: Review & Grill-me Protocol
- 구현 완료 직후 승인을 요청하지 않는다.
- `LESSONS.md` 로드 실패 시 조용히 건너뛰고 `audit.md`에 기록한다.
- **Grill-me Selection**: 엣지 케이스에 대해 2~3가지 해결 대안(Option A, B, C)을 제시하며, 반드시 **(권장)** 안을 포함하여 사용자의 의사결정을 돕는다.

## Rule 5: Knowledge Assetization (트랙 종료)
- 모든 체크리스트 완료 후 다음을 수행한다:
  1. `closure-report.md` 작성 (성공 요인, 시행착오 기록)
  2. `LESSONS.md`에 이번 트랙의 핵심 교훈을 3줄 이내로 업데이트
  3. **사용자의 최종 승인을 확인한 후**, 전역 `{YYYY-MM}-status.md`의 작업한 트랙을 `✅ 완료`로 변경

## Negative Constraints (금지 조항)
- [DANGER] 계획되지 않은 임의의 코드 수정을 절대 금지한다.
- [DANGER] 실패하는 테스트 케이스 없이 구현 코드를 먼저 작성하지 마라.
- [DANGER] `audit.md`에 기록되지 않은 중요한 설계 변경을 금지한다.
