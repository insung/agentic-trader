# Gemini / Google Antigravity Compatibility

이 파일은 Gemini CLI와 Google Antigravity 호환을 위한 얇은 오버레이입니다.

## Required Behavior

1. 먼저 root `AGENTS.md`를 읽고 그 규칙을 프로젝트의 SSOT로 따릅니다.
2. 이 파일에 `AGENTS.md`와 충돌하는 규칙을 추가하지 않습니다.
3. 도구별 로컬 설정은 저장소에 공유하지 않습니다. 필요한 경우 개인 환경에서만 설정합니다.

## Project Reminder

- LLM은 매매 orchestrator가 아닙니다. FastAPI와 LangGraph가 제어 흐름을 통제합니다.
- 주문/지표/리스크 검증은 Python deterministic gate가 담당합니다.
- `.agents/agents/*.md`는 Gemini CLI agent가 아니라 LangGraph 런타임용 system prompt template입니다.
