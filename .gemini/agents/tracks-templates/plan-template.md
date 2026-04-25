# Track Plan: {track_name}

**Context**: {이 작업이 필요한 배경 및 비즈니스/기술적 가치}

---

### 1. Architecture Boundaries
*변경 범위(Blast Radius)를 정의하여 예기치 않은 부작용을 방지합니다.*

| Category | Path | Responsibility / Impact |
| :--- | :--- | :--- |
| **Create** | `path/to/new_file` | 신규 기능/모듈의 역할 정의 |
| **Modify** | `path/to/existing` | 수정 대상 로직 및 영향도 분석 |
| **Test** | `path/to/test` | TDD 검증 시나리오 및 테스트 파일 |

### 2. Execution Roadmap (TDD Units)
*각 단계는 단일 테스트 파일 단위의 원자적 구현 단위로 분해합니다. 코딩 작업 시에만 todos/ 파일을 생성하며, 구조는 [Core Task / Context & Dialogue / Verification] 형식을 따릅니다.*

- [ ] **Step 1: {핵심 기능명} 구현** (`todos/1-task-name.md`)
  - [ ] Context: 사용자와 협의된 주요 구현 방향 및 제약 사항 기록
  - [ ] Core Task: 실패하는 테스트 작성 및 최소 구현 통과
  - [ ] Verification: 테스트 패스 및 코드 리뷰 준비
- [ ] **Step 2: {핵심 기능명} 확장 및 리팩토링**
- [ ] **Step 3: 최종 통합 및 문서화** (문서 작업은 plan.md 체크리스트로만 관리 가능)

### 3. Verification Strategy
- **Unit Tests**: {테스트 프레임워크 및 주요 검증 대상}
- **Integration**: {모듈 간 상호작용 검증 방법}
- **Manual Check**: {자동화하기 어려운 UI/UX 또는 복합 시나리오}

### 4. Discovered & Technical Debt
> 작업 중 발견된 이슈나 추후 개선이 필요한 사항은 `notes/discovered.md`에 기록하고 핵심만 여기 요약합니다.

---
