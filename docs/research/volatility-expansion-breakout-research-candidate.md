---
name: Volatility Expansion Breakout (W-Bottom / M-Top)
status: promoted_to_btc_paper_candidate
strategy_type: breakout
runtime_registry: btc_only_registered
validator: backend/features/trading/strategy_validators.py
quant_research: backend/features/trading/research/quant_research.py
minimum_risk_reward: 2.0
required_timeframes:
  - M5
  - M15
indicators:
  - Bollinger Bands (20, 2)
  - ATR (14)
  - ADX (14)
  - EMA (20/50)
---

# Volatility Expansion Breakout Research Candidate

이 문서는 VEB의 연구 기록입니다. 3회 백테스트 순회 후 BTCUSD 한정 paper candidate로 승격했으며, NAS100ft.r와 live 승격은 보류합니다. runtime 규칙 문서는 `docs/trading-strategies/volatility_expansion_breakout.md`입니다.

## 1. 전략 개요

고변동성 상품은 에너지를 응축한 뒤 특정 방향으로 강하게 발산하는 구간이 있습니다. VEB는 막연한 돌파 추격이 아니라, Bollinger Band 밖으로 1차 과열/과매도 후 2차 저점·고점이 밴드 안쪽에서 둔화되는 W-Bottom/M-Top 구조를 확인하고 neckline 돌파만 거래하는 전략 후보입니다.

핵심 원칙:

- LLM의 차트 패턴 추정을 신뢰하지 않습니다.
- Python validator가 W/M 구조, neckline, ADX/ATR momentum, SL/TP를 다시 계산합니다.
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
5. M15 confirmation:
   - `ADX14 > 20`
   - ADX가 직전 값보다 상승 중
   - EMA 환경이 명백한 역방향이면 차단
6. M5 breakout candle range:
   - `(high - low) >= ATR14 * 1.5`

## 4. SL / TP

Long:

- `SL = bottom2_low - (M5 ATR14 * 0.5)`
- `TP = entry + abs(entry - SL) * 2.0`

Short:

- `SL = top2_high + (M5 ATR14 * 0.5)`
- `TP = entry - abs(entry - SL) * 2.0`

## 5. Invalidation Scope

전략 아이디어에는 진입 후 M5 캔들 2개가 neckline 반대편에서 연속 마감하면 즉시 청산한다는 invalidation이 포함됩니다. 다만 현재 validator는 주문 직전 setup 검증만 담당하므로, 이 사후 청산 규칙은 position/reconcile 운영 경로의 별도 작업으로 다룹니다.

## 6. Current Promotion Status

- Research baseline: 유지
- Deterministic validator: 구현됨, bandwidth expansion filter 추가
- Runtime registry: BTCUSD 한정 등록
- Paper promotion: BTCUSD candidate
- Live promotion: 보류
- NAS100ft.r: 현 조건으로 제외/보류

승격 근거와 3회 순회 결과는 track audit에 기록합니다. Live 승격은 paper forward test와 post-entry invalidation 지원 후 다시 판단합니다.
