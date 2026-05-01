---
name: Strategy Name
status: draft
strategy_type: trend_following | mean_reversion | breakout | pullback
registered_in: backend/config/strategies_config.json
validator: backend/features/trading/strategy_validators.py
minimum_risk_reward: 2.0
required_timeframes:
  - M15
  - M30
allowed_regimes:
  - Bullish
primary_timeframe: M15
confirmation_timeframes:
  - M30
indicators:
  - EMA20
  - EMA50
  - ATR14
---

# Strategy Name

## Runtime Contract

- 이 문서는 Strategist/Chief Trader가 읽는 전략 설명서입니다.
- 주문 가능 여부는 `backend/features/trading/strategy_validators.py`의 deterministic gate가 최종 판단합니다.
- 새 전략을 주문 가능 상태로 승격하려면 `docs/trading-strategies/`, `backend/config/strategies_config.json`, validator, 단위 테스트를 한 세트로 추가해야 합니다.
- LLM은 계산을 직접 추정하지 말고 Python이 제공한 indicator snapshot의 값을 근거로만 판단해야 합니다.

## 1. 전략 개요 (Overview)

- **종류:** 전략 유형
- **핵심 지표:** 사용 지표
- **철학:** 어떤 시장 구조에서 왜 이 전략이 유효한지 설명합니다.

## 2. 진입 조건 (Entry Rules)

### A. 롱(매수) 진입

1. 조건을 indicator snapshot 값으로 검증 가능하게 씁니다.
2. 필요한 상위 타임프레임 확인 조건을 씁니다.
3. 캔들 마감 기준인지, 다음 캔들 진입인지 명확히 씁니다.

### B. 숏(매도) 진입

1. 조건을 indicator snapshot 값으로 검증 가능하게 씁니다.
2. 필요한 상위 타임프레임 확인 조건을 씁니다.
3. 캔들 마감 기준인지, 다음 캔들 진입인지 명확히 씁니다.

## 3. 청산 조건 (Exit Rules)

- **손절가 (SL):** 어디에 두는지, ATR 최소 거리와 충돌하지 않는지 씁니다.
- **익절가 (TP):** 최소 손익비 또는 목표 지표를 씁니다.
- **실행 계약:** 현재 런타임은 단일 TP만 지원하므로, 필요하면 `minimum_risk_reward`와 `exit_profile`을 함께 정의합니다.
- **무효화:** 진입 후 어떤 조건이 깨지면 전략 가설이 틀렸다고 보는지 씁니다.

## 4. Deterministic Gate

Python validator가 반드시 다시 검산해야 하는 조건을 씁니다.

- 필수 지표 존재 여부
- 방향별 진입 조건
- 상위 타임프레임 충돌 조건
- ATR 기반 최소 SL 거리
- 과열/추격/횡보장 차단 조건

## 5. 위험 경고 (AI 가이드라인)

- 어떤 market regime에서는 금지되는지 씁니다.
- 뉴스, 이벤트, 스프레드, 변동성 조건을 씁니다.
- LLM이 HOLD해야 하는 애매한 조건을 씁니다.
