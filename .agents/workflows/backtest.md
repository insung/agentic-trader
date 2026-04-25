---
description: 과거 데이터를 활용한 전략 검증(백테스팅) 및 리포트 생성 워크플로우
---
# Agentic Trader: Backtesting Workflow (/backtest)

이 워크플로우는 과거 시장 데이터를 수집하고, 이를 활용해 LangGraph 에이전트 파이프라인의 성능을 검증한 뒤 시각적 리포트를 생성하는 절차를 안내합니다.

## 사전 조건
- Wine 환경에서 MT5 터미널이 구동 가능해야 합니다. (데이터 수집 시 필요)
- `gemini-2.5-flash` 모델의 API 키가 설정되어 있어야 합니다.

## 1. 과거 데이터 수집 (Fetch History)
백테스트에 사용할 과거 캔들 데이터를 MT5에서 내려받습니다.
- **명령어**: `make backtest-fetch SYMBOL=종목 [TIMEFRAME=H1] [FROM=YYYY-MM-DD] [TO=YYYY-MM-DD] [DAYS=일수]`
- **사용 예시**:
    - 최근 30일치 1시간봉: `make backtest-fetch SYMBOL=EURUSD DAYS=30`
    - 특정 기간 15분봉: `make backtest-fetch SYMBOL=BTCUSD FROM=2024-01-01 TO=2024-01-31 TIMEFRAME=M15`
- **결과**: `backtests/data/` 디렉토리에 `{SYMBOL}_{TIMEFRAME}_{START}_{END}.csv` 파일이 생성됩니다.

## 2. 백테스트 실행 (Run Backtest)
내려받은 CSV 데이터를 사용하여 시뮬레이션을 수행합니다. 에이전트들이 각 시점마다 시장을 분석하고 매매 여부를 결정합니다.
- **명령어**: `make backtest-run DATA=파일경로`
- **예시**: `make backtest-run DATA=backtests/data/EURUSD_H1_30d_20260425.csv`
- **옵션**: 
    - `SYMBOL=종목`: (선택) 리포트에 표시될 종목명
    - 기본적으로 5캔들마다 한 번씩 에이전트가 판단합니다.

## 3. 리포트 확인 (Review Results)
백테스트가 완료되면 통계 요약과 차트가 포함된 리포트가 자동으로 생성됩니다.

- **리포트 위치**: `docs/trading_logs/backtest_results/`
- **파일 확인**: 생성된 `.md` 파일을 열어 승률, PnL, MDD 및 차트 이미지를 확인합니다.
- **타점 분석**: 차트의 화살표(매수/매도)와 에이전트의 추론(Reasoning) 로그를 대조하며 전략의 유효성을 판단합니다.

## 4. 데이터 정리 (Optional)
테스트용 데이터와 결과 파일들을 모두 삭제하려면 다음 명령어를 사용합니다.
- **명령어**: `make backtest-clean`

---
> [!TIP]
> **비용 절감**: `run_backtest.py`는 `gemini-2.5-flash`를 사용하므로 비용이 매우 저렴하지만, 너무 많은 데이터를 한꺼번에 돌리기보다는 7~14일 단위로 먼저 테스트해보는 것을 권장합니다.
