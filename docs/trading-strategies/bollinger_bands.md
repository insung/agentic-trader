---
name: Bollinger Bands Reversion
status: runtime
strategy_type: mean_reversion
registered_in: backend/config/strategies_config.json
validator: backend/features/trading/strategy_validators.py
required_timeframes:
  - M15
  - M30
allowed_regimes:
  - Ranging
  - High Volatility
primary_timeframe: M15
confirmation_timeframes:
  - M30
indicators:
  - Bollinger Bands 20/2
  - EMA20
  - EMA50
  - RSI14
  - ATR14
---

# Bollinger Bands Reversion (볼린저 밴드 반전 전략)

## Runtime Contract

- 이 문서는 Strategist/Chief Trader가 읽는 전략 설명서입니다.
- 주문 가능 여부는 `backend/features/trading/strategy_validators.py`의 deterministic gate가 최종 판단합니다.
- 새로 추가하거나 수정한 조건은 `backend/config/strategies_config.json`, validator, 단위 테스트와 함께 맞춰야 합니다.
- LLM은 계산을 직접 추정하지 말고 Python이 제공한 indicator snapshot의 값을 근거로만 판단해야 합니다.

## 1. 전략 개요 (Overview)
- **종류:** 역추세 반전 매매 (Reversal)
- **핵심 지표:** 볼린저 밴드 (20일 단순 이동평균선, 표준편차 2)
- **철학:** 단순한 밴드 이탈(역추세) 매매는 강한 추세장(밴드 워킹)에서 큰 손실을 유발하므로, 가격이 밴드를 이탈한 후 만들어내는 **'더블 탑(Double Top)'** 또는 **'더블 바텀(Double Bottom)'** 패턴과 **'캔들의 꼬리'**를 결합하여 승률이 극대화된 타점에서만 진입합니다.

## 2. 진입 조건 (Entry Rules)

### A. 롱(매수) 진입: 더블 바텀 패턴
1.  **첫 번째 저점:** 캔들이 **하단 밴드를 이탈**하며 형성되어야 합니다.
2.  **두 번째 저점:** 
    *   첫 번째 저점보다 높거나 낮은 것은 중요하지 않습니다.
    *   **하단 밴드 안쪽에서 형성**되거나, 아주 약하게 이탈해야 신뢰도가 높습니다.
3.  **트리거 (진입 타이밍):** 두 번째 저점에서 지지받는 캔들 패턴(긴 아래 꼬리 캔들 또는 이전 음봉을 덮는 강한 장대양봉)이 마감될 때 진입합니다.

### B. 숏(매도) 진입: 더블 탑 패턴
1.  **첫 번째 고점:** 캔들이 **상단 밴드를 돌파**하며 형성되어야 합니다.
2.  **두 번째 고점:** **상단 밴드를 돌파하지 못하고 안쪽에서 저항**받을 때 신뢰도가 높습니다.
3.  **트리거 (진입 타이밍):** 두 번째 고점에서 상승세가 꺾이는 캔들 패턴(긴 윗 꼬리 캔들 또는 이전 양봉을 덮는 장대음봉/작은 음봉 연속)이 마감될 때 진입합니다.

## 3. 청산 조건 (Exit Rules)
- **손절가 (SL):** 진입의 근거가 된 두 번째 고점/저점의 직전 꼬리 끝부분.
- **1차 익절가 (TP1):** 볼린저 밴드 중심선 (20 SMA) 도달 시 비중의 절반 청산.
- **2차 익절가 (TP2):** 반대편 밴드 (롱 진입 시 상단 밴드, 숏 진입 시 하단 밴드) 도달 시 전량 청산.

## 4. Deterministic Gate

Python validator는 최소한 아래 조건을 다시 검산합니다.

- SL 거리는 ATR14 기준 최소 거리 이상이어야 합니다.
- 최근 관측 구간 안에서 밴드 이탈 또는 밴드 근접 극단값이 있어야 합니다.
- BUY는 하단 밴드 극단값 이후 반전 캔들, 저점에서 충분히 벗어난 종가, 강한 하락 추세 부재가 필요합니다.
- SELL은 상단 밴드 극단값 이후 반전 캔들, 고점에서 충분히 밀린 종가, 강한 상승 추세 부재가 필요합니다.
- EMA20/EMA50와 RSI14는 역추세 진입이 추세장 밴드 워킹에 맞서는지 확인하는 필터로 사용합니다.

## 5. 위험 경고 (AI 가이드라인)
- **밴드 스퀴즈(수렴):** 밴드폭이 매우 좁아진 상태에서 캔들이 밴드를 이탈하는 것은 '강한 추세의 시작'일 확률이 높으므로, 이 전략(역추세 반전)을 사용해서는 안 됩니다.
- **밴드 워킹:** 캔들이 상단/하단 밴드를 타고 계속 흘러가는 구간에서는 반전 패턴이 나오기 전까지 절대 섣불리 진입하지 않고 관망(Hold)합니다.
