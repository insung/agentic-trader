---
name: Moving Average Crossover
status: runtime
strategy_type: trend_following
registered_in: backend/config/strategies_config.json
validator: backend/features/trading/strategy_validators.py
required_timeframes:
  - M15
  - M30
allowed_regimes:
  - Bullish
  - Bearish
primary_timeframe: M15
confirmation_timeframes:
  - M30
indicators:
  - EMA20
  - EMA50
  - ADX14
  - ATR14
  - Bollinger Bands 20/2
  - RSI14
---

# Moving Average Crossover (이동평균선 교차 전략)

## Current Status

- 이 문서는 현재 `ma_crossover` 연구용 baseline과 실전/페이퍼 승격 후보를 함께 설명합니다.
- 현재 deterministic validator와 quant baseline은 구현되어 있습니다.
- 다만 paper/live 승격은 아직 끝나지 않았습니다.
- 승격 여부는 월별 walk-forward, No-Trade Audit, validator 통과 여부를 함께 보고 판단합니다.
- 최근 6개월 BTCUSD M15/M30 quant 결과는 강했지만, 이 문서는 그 결과를 "승격 후보"로만 취급합니다.

## Runtime Contract

- 이 문서는 Strategist/Chief Trader가 읽는 전략 설명서입니다.
- 주문 가능 여부는 `backend/features/trading/strategy_validators.py`의 deterministic gate가 최종 판단합니다.
- 새로 추가하거나 수정한 조건은 `backend/config/strategies_config.json`, validator, 단위 테스트와 함께 맞춰야 합니다.
- LLM은 계산을 직접 추정하지 말고 Python이 제공한 indicator snapshot의 값을 근거로만 판단해야 합니다.
- 연구용 quant baseline에서 사용한 핵심 조건은 M15 진입 + M30 confirmation, recent cross age, ADX14, ATR14 기반 SL/TP입니다.

## 1. 전략 개요 (Overview)
- **종류:** 추세 추종 매매 (Trend Following)
- **핵심 지표:** 단기 EMA(지수 이동평균선 20), 장기 EMA(지수 이동평균선 50)
- **철학:** 추세가 명확히 형성된 시장에서, 단기 이동평균선이 장기 이동평균선을 돌파하는 교차(Crossover) 시점을 포착하여 추세의 초입에 진입합니다. 횡보장에서는 사용하지 않습니다.

## 2. 진입 조건 (Entry Rules)

### A. 롱(매수) 진입: 골든 크로스
1.  **EMA 20이 EMA 50 위로 교차 (Golden Cross):** 단기 평균이 장기 평균을 상향 돌파하면 상승 추세 전환 신호입니다.
2.  **가격 위치 확인:** 현재 캔들이 EMA 20 위에 위치해야 합니다.
3.  **추세 보조 확인:** ADX(Average Directional Index)가 25 이상이면 추세 강도가 충분하다고 판단합니다.
4.  **트리거:** 교차가 확인된 캔들이 마감된 이후, 다음 캔들의 시가에서 진입합니다. (캔들 마감 전 섣부른 진입 금지)
5.  **상위 타임프레임 확인:** M30이 M15와 같은 방향으로 정렬되어 있어야 합니다.
6.  **추격 진입 차단:** 최근 교차가 너무 오래된 경우는 진입하지 않습니다.

### B. 숏(매도) 진입: 데드 크로스
1.  **EMA 20이 EMA 50 아래로 교차 (Dead Cross):** 단기 평균이 장기 평균을 하향 돌파하면 하락 추세 전환 신호입니다.
2.  **가격 위치 확인:** 현재 캔들이 EMA 20 아래에 위치해야 합니다.
3.  **추세 보조 확인:** ADX가 25 이상이어야 합니다.
4.  **트리거:** 교차가 확인된 캔들이 마감된 이후, 다음 캔들의 시가에서 진입합니다.
5.  **상위 타임프레임 확인:** M30이 M15와 같은 하락 방향으로 정렬되어 있어야 합니다.
6.  **추격 진입 차단:** 최근 교차가 너무 오래된 경우는 진입하지 않습니다.

## 3. 청산 조건 (Exit Rules)
- **손절가 (SL):** 진입 시점의 EMA 50 가격. EMA 50을 이탈하면 추세가 꺾인 것으로 판단합니다.
- **1차 익절가 (TP1):** 진입가 기준 SL 거리의 2배 (1:2 R/R). 비중의 50% 청산.
- **2차 익절가 (TP2):** 진입가 기준 SL 거리의 3배 (1:3 R/R). 잔여 비중 전량 청산.
- **트레일링 스탑:** 1차 익절 달성 후, 나머지 비중의 SL을 진입가(손익분기점)로 이동합니다.

## 4. Deterministic Gate

Python validator는 최소한 아래 조건을 다시 검산합니다.

- SL 거리는 ATR14 기준 최소 거리 이상이어야 합니다.
- ADX14는 추세 강도 최소값 이상이어야 합니다.
- BUY는 EMA20 > EMA50, close > EMA20, 최근 bullish cross가 필요합니다.
- SELL은 EMA20 < EMA50, close < EMA20, 최근 bearish cross가 필요합니다.
- bullish/bearish cross는 정해진 `max_cross_age_bars` 안에 있어야 합니다.
- 상위 타임프레임이 반대 방향이면 차단합니다.
- 볼린저 밴드와 RSI 기준으로 이미 과열/추격 진입이면 차단합니다.

## 5. Quant Research Notes

이 전략은 `make quant-run QUANT_STRATEGY=ma_crossover`로 연구용 검증이 가능합니다.

현재 연구용 baseline에서 자주 쓰는 입력은 아래와 같습니다.

- `MA_ADX_MINS=25,30`
- `MA_MAX_CROSS_AGE_BARS=3,6`
- `FILTER_TIMEFRAME=M30`
- `ATR_STOP_MULTIPLIER=1.0`
- `RR=1.3,1.5,2.0`

최근 6개월 BTCUSD M15/M30 구간에서는 이 baseline이 다른 deterministic baseline보다 강했습니다.
다만 paper/live 승격은 quant 결과만으로 하지 않으며, validator와 No-Trade Audit까지 함께 확인합니다.

## 6. 위험 경고 (AI 가이드라인)
- **횡보장 금지:** Market Regime이 "Ranging"일 때 이 전략을 사용하면 이동평균선이 자주 교차하여 연속 손절(Whipsaw)이 발생합니다.
- **뉴스 이벤트:** 고용지표, 금리 결정 등 주요 경제 이벤트 직전/직후에는 이동평균선 교차가 노이즈일 수 있으므로 진입을 보류합니다.
- **다이버전스:** EMA 교차와 MACD/RSI 다이버전스가 동시에 발생하면 신뢰도가 높아집니다. 반대로 교차만 발생하고 보조지표가 반대 신호를 보이면 진입을 보류합니다.
