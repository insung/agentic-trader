---
name: track-writing-plans
description: "다중 단계 작업에 대한 설계안(Spec)이나 요구사항이 있을 때, 실제 코드를 작성하기 전에 세부 구현 계획을 수립하기 위해 사용합니다."
disable-model-invocation: true
---

# 구현 계획 작성하기 (Track-Writing-Plans)

## 개요 (Overview)

엔지니어가 우리 코드베이스에 대한 컨텍스트가 전혀 없고 약간은 부족한 감각을 가졌다고 가정하고, 포괄적이고 정밀한 구현 계획을 작성합니다. 각 작업을 위해 어떤 파일을 수정해야 하는지, 필요한 코드, 테스트, 참고해야 할 문서, 그리고 어떻게 테스트할지 등 알아야 할 모든 것을 문서화합니다. 전체 계획을 작게 쪼갠 'Bite-sized' Task 단위로 제공해야 합니다. DRY(Don't Repeat Yourself), YAGNI(You Aren't Gonna Need It), TDD(Test-Driven Development), 잦은 커밋(Frequent commits) 원칙을 준수하세요.

엔지니어가 숙련된 개발자이긴 하지만, 우리의 도구 모음이나 도메인 문제에 대해서는 거의 모른다고 가정하세요. 좋은 테스트 설계 방법도 잘 모른다고 가정하세요.

**시작 시 알림:** "구현 계획을 수립하기 위해 `track-writing-plans` 스킬을 사용합니다." (I'm using the track-writing-plans skill to create the implementation plan.)

**저장 경로:** `~/.track/{project_name}/plans/YYYY-MM-DD-<feature-name>.md`
- (현재 작업 경로명을 기반으로 `{project_name}` 추출)

## 스코프 점검 (Scope Check)

... [나머지 내용은 동일]
