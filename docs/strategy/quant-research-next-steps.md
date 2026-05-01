# Quant Research Next Steps

이 문서는 현재 quant research 결과를 바탕으로 다음에 무엇을 할지 정리합니다.

## 현재 결론

- `bollinger` 계열은 거래는 발생하지만 edge가 약합니다.
- `bollinger_mtf`는 방어력은 좋아졌지만 수익이 약합니다.
- `trend_pullback`은 폐기 후보입니다.
- `trend_pullback_reclaim`은 구조 개선은 있었지만 승격 기준을 넘지 못했습니다.
- `breakout`은 3개월에서는 그럴듯했지만 6개월에서 PF가 1 미만으로 내려가 실패했습니다.
- `ma_crossover`는 현재 가장 강한 승격 후보입니다.
- `macd`는 6개월 기준 PF가 1 미만이라 실패 baseline입니다.
- Buy & Hold와 No-trade benchmark는 비교 기준으로 추가되었습니다.
- Random benchmark는 비교 기준으로 추가되었습니다.

즉, 현재까지의 deterministic baseline 중에서는 **MA Crossover만 승격 후보로 남기고, 나머지는 보류 또는 실패 baseline**으로 보는 것이 맞습니다.

## 다음 단계

### 1. MA Crossover 승격 검증

MA Crossover는 현재까지 가장 안정적인 성과를 보였습니다. 이제 해야 할 일은 승격 전에 마지막 검증을 끝내는 것입니다.

- 월별 walk-forward 결과 확인
- 1~6개월 구간에서 성능 유지 여부 확인
- 승격 기준 문서와 validator 정합성 확인
- No-Trade Audit과 충돌 여부 확인

### 2. MACD는 실패 baseline으로 보류

MACD는 연구용 baseline으로는 남겨둘 수 있지만, 현재 결과만으로는 승격 대상이 아닙니다.

- 6개월 BTCUSD M15에서 PF가 1 미만
- 수익률이 음수
- 거래 수가 많지만 edge가 약함

### 3. Random benchmark는 비교 기준으로 고정

전략이 실제로 의미가 있는지 보려면 랜덤 baseline이 필요합니다.
이 baseline은 승격 후보가 아니라 해석 기준입니다.

### 4. 월별 walk-forward 검증 강화

같은 파라미터가 특정 달 한 번만 좋은지, 여러 달에서 유지되는지 확인합니다.

### 5. blocked-trade / no-trade audit

왜 거래가 없었는지, 왜 차단됐는지 분리해서 봅니다.

## 다음 실험 순서

1. MA Crossover의 월별 결과를 run_id 기준으로 재검증합니다.
2. `make quant-summary SUMMARY_MONTHLY=1`로 월별 결과를 봅니다.
3. 1~6개월 구간에서 같은 파라미터가 유지되는지 확인합니다.
4. MACD는 추가 실험보다 보류 대상으로 둡니다.
5. Random benchmark를 고정 비교 기준으로 유지합니다.
6. No-Trade Audit을 추가합니다.

## 현재 보류할 것

- breakout 미세조정
- 단일 월 최고값만 보고 승격하는 것
- 문서 없는 전략 추가
- validator 없는 전략 승격
- MACD를 더 미세하게 튜닝해서 승격시키는 것
- 여러 전략을 단순 합산해서 섞는 것
- Buy & Hold / No-trade benchmark를 더 확장 없이 전략으로 오해하는 것
- Random benchmark를 승격 후보로 오해하는 것

## 승격 기준

전략 승격은 다음을 만족해야 합니다.

- 비용/슬리피지 포함 PF가 1.20 이상
- MDD가 10% 이하
- 거래 수가 충분히 많음
- 월별로 일관성이 있음
- 문서, registry, validator, 테스트가 모두 존재함

## 현재 후보 요약

### 승격 후보

- MA Crossover
  - 현재까지 가장 좋은 균형
  - M15/M30에서 PF와 MDD가 모두 양호
  - 월별 결과가 일부 흔들리므로 추가 walk-forward 검증 필요

### 실패 또는 보류 후보

- MACD
  - 6개월 기준 PF < 1
  - 수익률 음수
  - 연구용 baseline으로만 유지
- Buy & Hold / No-trade
  - 전략 비교용 기준선
  - 승격 대상이 아니라 해석 기준
- Breakout
  - 3개월에서는 그럴듯했지만 6개월에서 무너짐
- Bollinger / Bollinger MTF / Trend Pullback / Trend Pullback Reclaim
  - 후보 생성과 연구용 분리에는 유효하지만 승격 기준 미달
