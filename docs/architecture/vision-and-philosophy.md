# Vision and Philosophy

Agentic Trader의 장기 비전은 **감정에 휘둘리지 않고, 스스로 검증하며, 안전 규칙을 절대 우회하지 않는 자율형 AI 트레이딩 시스템**을 구축하는 것입니다.

이 프로젝트는 LLM을 전능한 자동매매 봇으로 쓰지 않습니다. LLM은 시장 상태를 해석하고 전략 가설을 세우는 reasoning engine이고, 실제 제어 흐름과 안전 판단은 Python backend가 담당합니다.

## Long-term Vision

1. **Zero-Human Hedge Fund**
   - Tech Analyst, Strategist, Chief Trader, Risk Reviewer 같은 역할 기반 AI 직원들이 협업합니다.
   - 인간은 세부 매매 지시자가 아니라 원칙, 예산, 리스크 한도를 정하는 Board 역할을 합니다.

2. **Self-improving trading memory**
   - 주문 직후가 아니라 포지션 청산 후에만 복기를 생성합니다.
   - 복기, 백테스트 결과, validator 차단 사유를 구조화하여 다음 판단의 검색 가능한 기억으로 사용합니다.

3. **Strategy research over signal chasing**
   - 단일 매매 성공보다 반복 가능한 전략 검증 체계를 우선합니다.
   - walk-forward, out-of-sample, 비용/슬리피지 반영, blocked-trade audit으로 전략을 승격시킵니다.

4. **Multi-tool AI compatibility**
   - Codex, Gemini CLI, Google Antigravity 같은 도구를 사용할 수 있지만 프로젝트 원칙은 root `AGENTS.md`에 통합합니다.
   - 도구별 에이전트 파일을 늘리기보다, 공통 규칙과 Python deterministic workflow를 유지합니다.

## Engineering Philosophy

1. **Safety and air-gap first**
   - 어떤 AI 모델도 MT5나 거래소 API에 직접 접근할 수 없습니다.
   - 모든 주문은 FastAPI/Python backend를 통과하며, guardrail 위반 시 즉시 차단됩니다.

2. **Data and logic separation**
   - LLM에게 지표 계산, lot size 계산, 손익비 계산을 맡기지 않습니다.
   - OHLCV 가공, EMA/ADX/ATR/Bollinger/RSI 계산, SL/TP 검증은 Python이 결정적으로 수행합니다.

3. **Code-driven control flow**
   - 워크플로우 순서와 라우팅은 LangGraph가 강제합니다.
   - CLI 에이전트나 범용 스킬 체계가 자율적으로 매매 플로우를 진행하지 않습니다.

4. **Philosophy of Paperclip, engine of LangGraph**
   - Paperclip류 프레임워크의 조직형 에이전트 철학은 차용합니다.
   - 하지만 트레이딩 도메인의 지연 시간, 비용, 안전성 요구 때문에 엔진은 Python LangGraph로 유지합니다.

5. **AI-native vertical slices**
   - 과도한 Clean Architecture 레이어링보다 기능 단위 응집과 명확한 Pydantic 데이터 계약을 우선합니다.
   - 미래 AI 세션이 파일 경계를 쉽게 이해하고 테스트로 검증할 수 있어야 합니다.

## Non-negotiables

- LLM 판단은 항상 structured output으로 받고 Python validator가 검증합니다.
- validator가 없는 전략은 실전/Paper 주문으로 승격하지 않습니다.
- 모든 코드 변경은 TDD gate와 `make test` 검증을 거칩니다.
- 프로젝트 방향과 운영 규칙의 SSOT는 `AGENTS.md`입니다.
