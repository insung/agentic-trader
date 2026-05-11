---
name: Volatility Expansion Breakout (W-Bottom / M-Top)
status: paper_candidate
strategy_type: breakout
registered_in: backend/config/strategies_config.json
validator: backend/features/trading/strategy_validators.py
minimum_risk_reward: 2.0
required_timeframes:
  - M5
  - M15
allowed_symbols:
  - BTCUSD
allowed_regimes:
  - High Volatility
  - Bullish
  - Bearish
primary_timeframe: M5
confirmation_timeframes:
  - M15
indicators:
  - Bollinger Bands (20, 2)
  - ATR (14)
  - ADX (14)
  - EMA (20/50)
---

# Volatility Expansion Breakout

이 문서는 Strategist/Chief Trader가 읽는 runtime strategy knowledge입니다. 현재 승격 범위는 BTCUSD paper candidate에 한정하며, NAS100ft.r는 백테스트 실패로 제외합니다.

## 1. 전략 개요

VEB는 Bollinger Band 밖으로 1차 과열/과매도 후 2차 저점·고점이 밴드 안쪽에서 둔화되는 W-Bottom/M-Top 구조를 확인하고 neckline 돌파만 거래하는 변동성 확장 전략입니다.

핵심 원칙:

- LLM의 차트 패턴 추정을 신뢰하지 않습니다.
- Python validator가 W/M 구조, neckline, ADX/ATR momentum, Bollinger bandwidth expansion, SL/TP를 다시 계산합니다.
- 단일 TP만 사용하며 부분 익절은 구현하지 않습니다.

## 2. Long Entry: W-Bottom

1. M5 최근 30~60개 캔들에서 Bottom 1을 찾습니다.
   - Bottom 1: `low <= bb_lower20`
2. Bottom 1 이후 Bottom 2를 찾습니다.
   - Bottom 2: local low
   - `bottom2_low > bottom1_low`
   - `bottom2_low > bb_lower20`
3. Neckline을 계산합니다.
   - `neckline = max(high[bottom1_idx:bottom2_idx])`
4. 현재 M5 close가 neckline 위로 돌파해야 합니다.
5. M15 confirmation:
   - `ADX14 > 20`
   - ADX가 직전 값보다 상승 중
   - EMA 환경이 명백한 역방향이면 차단
6. M5 breakout candle range:
   - `(high - low) >= ATR14 * 1.5`
7. Bollinger bandwidth expansion:
   - 최근 bandwidth 분포 대비 현재 bandwidth가 충분히 확장되어야 합니다.

## 3. Short Entry: M-Top

1. M5 최근 30~60개 캔들에서 Top 1을 찾습니다.
   - Top 1: `high >= bb_upper20`
2. Top 1 이후 Top 2를 찾습니다.
   - Top 2: local high
   - `top2_high < top1_high`
   - `top2_high < bb_upper20`
3. Neckline을 계산합니다.
   - `neckline = min(low[top1_idx:top2_idx])`
4. 현재 M5 close가 neckline 아래로 이탈해야 합니다.
5. M15 confirmation과 bandwidth expansion 조건은 Long과 동일합니다.

## 4. SL / TP

Long:

- `SL = bottom2_low - (M5 ATR14 * 0.5)`
- `TP = entry + abs(entry - SL) * 2.0`

Short:

- `SL = top2_high + (M5 ATR14 * 0.5)`
- `TP = entry - abs(entry - SL) * 2.0`

## 5. Invalidation Scope

진입 후 M5 캔들 2개가 neckline 반대편에서 연속 마감하면 즉시 청산한다는 invalidation은 전략 아이디어에 포함됩니다. 현재 운영 경로에서는 `tracked_positions`의 `strategy_metadata.neckline`과 `invalidation_state`를 사용해 paper reconcile 단계에서 두 번 연속 breach를 감지해 조기 청산합니다. live close adapter는 아직 없으므로 live 자동 청산은 별도 후속 작업이 필요합니다.

## 6. Promotion Scope

- BTCUSD: paper candidate
- NAS100ft.r: excluded
- Live: blocked until paper forward test and post-entry invalidation support are verified
