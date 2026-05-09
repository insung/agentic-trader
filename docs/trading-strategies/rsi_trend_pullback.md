---
name: RSI Trend Pullback
status: active
strategy_type: pullback
registered_in: backend/config/strategies_config.json
validator: backend/features/trading/strategy_validators.py
minimum_risk_reward: 2.0
required_timeframes:
  - M15
  - H1
primary_timeframe: M15
confirmation_timeframes:
  - H1
indicators:
  - EMA20
  - EMA50
  - ADX14
  - RSI14
  - ATR14
---

# RSI Trend Pullback

## Runtime Contract

- 이 문서는 Strategist/Chief Trader가 읽는 전략 설명서입니다.
- 주문 가능 여부는 `backend/features/trading/strategy_validators.py`의 deterministic gate가 최종 판단합니다.
- 새 전략을 주문 가능 상태로 승격하려면 `docs/trading-strategies/`, `backend/config/strategies_config.json`, validator, 단위 테스트를 한 세트로 추가해야 합니다.
- LLM은 계산을 직접 추정하지 말고 Python이 제공한 indicator snapshot의 값을 근거로만 판단해야 합니다.

## 1. 전략 개요 (Overview)

- **종류:** pullback
- **핵심 지표:** EMA20, EMA50, ADX14, RSI14, ATR14
- **철학:** 시장에 뚜렷한 추세(ADX > 25, 정배열/역배열)가 형성된 상태에서, 단기적인 가격 조정을 RSI로 포착(RSI 50 하향 돌파 후 회복)하여 추세 지속성에 베팅하는 눌림목 진입 전략입니다. 노이즈를 걸러내기 위해 캔들의 몸통 비율(Body Quality)과 상위 타임프레임(Confirmation Timeframe)의 추세 일치 여부를 함께 확인합니다.

## 2. 진입 조건 (Entry Rules)

### A. 롱(매수) 진입

1. **추세 확인:** 주 진입(Primary) 및 상위 확인(Confirmation) 타임프레임 모두에서 `EMA20 > EMA50` 이며, 현재 종가가 `EMA20` 위에 있어야 합니다.
2. **추세 강도:** 주 진입 타임프레임에서 `ADX14 > 25` 이어야 합니다.
3. **눌림목 확인:** 최근 3캔들 이내에 주 진입 타임프레임 `RSI14 < 50` 이력(pullback)이 존재해야 합니다.
4. **반등 품질:** 현재 캔들의 종가가 시가보다 높아야 하며(양봉), 전체 캔들 길이 대비 몸통(Body)의 비율이 최소 30% 이상이어야 합니다.

### B. 숏(매도) 진입

1. **추세 확인:** 주 진입 및 상위 확인 타임프레임 모두에서 `EMA20 < EMA50` 이며, 현재 종가가 `EMA20` 아래에 있어야 합니다.
2. **추세 강도:** 주 진입 타임프레임에서 `ADX14 > 25` 이어야 합니다.
3. **눌림목 확인:** 최근 3캔들 이내에 주 진입 타임프레임 `RSI14 > 50` 이력(pullback)이 존재해야 합니다.
4. **반등 품질:** 현재 캔들의 종가가 시가보다 낮아야 하며(음봉), 전체 캔들 길이 대비 몸통(Body)의 비율이 최소 30% 이상이어야 합니다.

## 3. 청산 조건 (Exit Rules)

- **손절가 (SL):** 
  - 기본적으로 최근 스윙 Low/High에 배치하되, Validator에 의해 ATR 기반의 최소 이격 거리(예: 1.0 ATR)로 강제 교정(Override)됩니다.
  - 방향성에 맞지 않거나 지나치게 타이트한 SL은 시스템이 안전한 값으로 덮어씌웁니다.
- **익절가 (TP):** 최소 손익비(Risk:Reward) 2.0 이상을 목표로 설정합니다. 교정된 SL 기준으로도 RR 2.0을 만족해야 주문이 최종 승인됩니다.
- **무효화:** 상위 확인 타임프레임의 추세가 반전되거나, 진입 후 주 진입 타임프레임 종가가 EMA50을 강하게 돌파하는 경우 전략 무효화로 간주합니다.

## 4. Deterministic Gate

Python validator가 반드시 다시 검산해야 하는 조건은 다음과 같습니다:

- 주 진입(Primary) 및 상위 확인(Confirmation) 타임프레임의 지표 스냅샷이 모두 존재하는지 확인
- 상위 확인 타임프레임의 EMA20/EMA50 방향성이 주 진입 방향성과 일치하는지 확인 (상위 타임프레임 충돌 차단)
- 진입 방향에 따른 `EMA20 > EMA50` (롱) 또는 `EMA20 < EMA50` (숏) 검증
- 추세 강도 `ADX14 > 25` 검증
- 최근 3캔들 내 `RSI14` 눌림목 이력 검증 및 현재 캔들 몸통 비율(Body > 30%) 검증
- ATR 기반 최소 SL 이격 거리 교정 및 손익비(RR >= 2.0) 재계산 확인

## 5. 위험 경고 (AI 가이드라인)

- 횡보장(Ranging)이나 변동성이 극심하여 방향성을 알 수 없는 장세(ADX < 25)에서는 진입이 전면 차단되므로 HOLD를 권장합니다.
- 캔들의 윗꼬리나 밑꼬리가 비정상적으로 긴 도지(Doji) 캔들에서는 '가짜 반등'일 가능성이 높으므로 몸통(Body) 비율을 반드시 확인합니다.
- 중요한 거시 경제 지표 발표 전후 등 스프레드가 비정상적으로 벌어지거나 변동성이 예측 불가능한 시점에는 진입을 피해야 합니다.
