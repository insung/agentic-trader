# RSI Trend Pullback Checklist

전략 아이디어는 타당합니다. 분류로는 trend pullback continuation이고, 기존 MA Crossover 계열보다 한 단계 더 “눌림목 진입”에 가깝습니다. 다만 승격하려면 조건을 더 명확히 해야 합니다.

핵심 판단:
- ADX > 25 + EMA20 > EMA50는 추세 필터로 적절합니다.
- RSI < 45를 최근 눌림목 기준으로 쓰는 것도 가능합니다.
- 현재 RSI > 50로 반등 확인을 넣은 것도 논리적으로 맞습니다.
- 대신 SELL 대칭 규칙을 반드시 정의해야 합니다.
- 이 전략은 현재 backend/features/trading/strategy_validators.py에 없는 타입이므로, 새 validator가 필요합니다.

주의할 점:
- 최근 3캔들 이내 RSI < 45와 현재 RSI > 50은 타당하지만, 종목/타임프레임에 따라 너무 빡빡하거나 너무 느슨할 수 있습니다.
- 가능하면 RSI cross back above 45/50 같은 “회복 시점”을 명시하는 편이 좋습니다.
- SL/TP, 최소 RR, 금지 장세, 상위 타임프레임 확인까지 정해야 주문 가능 전략이 됩니다.

## RSI Trend Pullback 체크리스트

### 1. 전략 정의
- [x] 전략명을 확정한다.
- [x] 전략 유형을 `pullback` 또는 `trend_following`으로 분류한다.
- [x] 이 전략이 어떤 시장에서 유효한지 한 문장으로 정의한다.
- [x] BUY/SELL 대칭 규칙을 모두 정의한다.

### 2. 진입 규칙
- [x] BUY 진입 조건을 명확히 적는다.
- [x] SELL 진입 조건을 명확히 적는다.
- [x] 추세 조건을 정의한다: `EMA20 > EMA50` 또는 `EMA20 < EMA50`
- [x] 강도 조건을 정의한다: `ADX14 > 25`
- [x] 눌림목 조건을 정의한다: 최근 3캔들 이내 RSI 반응
- [x] 반등 확인 조건을 정의한다: 현재 RSI 회복 여부
- [x] 현재 종가가 EMA20 위/아래인지 확인한다.
- [x] 캔들 종가 기준인지, 실시간 기준인지 정한다.

### 3. 청산 규칙
- [x] SL 기준을 정의한다.
- [x] TP 기준을 정의한다.
- [x] 최소 손익비를 정한다.
- [x] 무효화 조건을 정의한다.
- [x] 기존 포지션과 충돌하는 경우의 처리 방식을 정한다.

### 4. Validator 설계
- [x] `backend/features/trading/strategy_validators.py`에 새 gate를 추가한다.
- [x] 필수 indicator snapshot 존재 여부를 검증한다.
- [x] BUY/SELL 방향별 조건을 분리한다.
- [x] ADX 조건을 검증한다.
- [x] EMA20/EMA50 방향성을 검증한다.
- [x] RSI pullback 및 rebound 조건을 검증한다.
- [x] ATR 기반 최소 SL 거리도 검증한다.
- [x] 추세 충돌이나 과열 진입은 차단한다.

### 5. 문서/등록
- [x] `docs/trading-strategies/`에 전략 문서를 작성한다.
- [x] `backend/config/strategies_config.json`에 등록한다.
- [x] `docs/strategy/strategy-document-template.md` 형식에 맞춘다.
- [x] `docs/README.md` 색인을 갱신한다. (불필요 확인 완료)

### 6. 테스트
- [x] BUY 성공 케이스 테스트를 만든다.
- [ ] SELL 성공 케이스 테스트를 만든다.
- [ ] ADX 부족 차단 테스트를 만든다.
- [ ] EMA 방향 불일치 차단 테스트를 만든다.
- [ ] RSI pullback 없음 차단 테스트를 만든다.
- [ ] RSI 반등 없음 차단 테스트를 만든다.
- [ ] ATR/SL 거리 부족 차단 테스트를 만든다.
- [x] `make test`를 통과시킨다.

### 7. 연구/승격
- [ ] `make quant-run`으로 baseline을 만든다.
- [ ] 비용/슬리피지 포함 결과를 본다.
- [ ] `paper`로 먼저 검증한다.
- [ ] 데모 `MODE=live`는 단일 canary로 확인한다.
- [ ] 통과 후에만 실전 승격 여부를 판단한다.
