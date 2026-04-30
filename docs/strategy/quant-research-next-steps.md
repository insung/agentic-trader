# Quant Research Next Steps

이 문서는 현재 quant research 결과를 바탕으로 다음에 무엇을 할지 정리합니다.

## 현재 결론

- `bollinger` 계열은 거래는 발생하지만 edge가 약합니다.
- `bollinger_mtf`는 방어력은 좋아졌지만 수익이 약합니다.
- `trend_pullback`은 폐기 후보입니다.
- `trend_pullback_reclaim`은 구조 개선은 있었지만 승격 기준을 넘지 못했습니다.
- `breakout`은 3개월에서는 그럴듯했지만 6개월에서 PF가 1 미만으로 내려가 실패했습니다.

즉, 현재까지의 deterministic baseline은 **실전 승격 후보를 아직 만들지 못했습니다.**

## 다음 단계

### 1. MA Crossover baseline 추가

현재 quant baseline 목록에는 LLM 없이 동작하는 MA Crossover가 없습니다.

이 전략을 추가해서 다음을 비교합니다.

- Buy & Hold
- Bollinger
- Bollinger MTF
- Trend Pullback Reclaim
- Breakout
- MA Crossover

### 2. Buy & Hold benchmark 추가

전략이 실제로 의미가 있는지 보려면 단순 benchmark가 필요합니다.

### 3. Random/no-trade benchmark 추가

최소 기준선이 있어야 전략 성과를 해석할 수 있습니다.

### 4. 월별 walk-forward 검증 강화

같은 파라미터가 특정 달 한 번만 좋은지, 여러 달에서 유지되는지 확인합니다.

### 5. blocked-trade / no-trade audit

왜 거래가 없었는지, 왜 차단됐는지 분리해서 봅니다.

## 다음 실험 순서

1. 1~6개월 quant run을 돌립니다.
2. `make quant-summary SUMMARY_MONTHLY=1`로 월별 결과를 봅니다.
3. 좋은 달만 고른 과최적화를 피합니다.
4. MA Crossover baseline을 추가합니다.
5. 다시 quant summary를 비교합니다.

## 현재 보류할 것

- breakout 미세조정
- 단일 월 최고값만 보고 승격하는 것
- 문서 없는 전략 추가
- validator 없는 전략 승격

## 승격 기준

전략 승격은 다음을 만족해야 합니다.

- 비용/슬리피지 포함 PF가 1.20 이상
- MDD가 10% 이하
- 거래 수가 충분히 많음
- 월별로 일관성이 있음
- 문서, registry, validator, 테스트가 모두 존재함

