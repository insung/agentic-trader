# 시스템 테스트 및 실행 가이드 (Testing & Execution Guide)

이 문서는 Agentic Trader 시스템의 개별 모듈 및 전체 파이프라인(End-to-End)이 정상적으로 작동하는지 확인하기 위한 테스트 절차를 안내합니다.

## 📋 사전 준비 사항 (Prerequisites)
1. **MetaTrader 5 실행:** Wine 환경에서 MT5 터미널이 실행 중이어야 합니다.
2. **자동 매매 허용:** MT5의 `[도구] -> [옵션] -> [전문가 조언자]` 탭에서 **"알고리즘 매매 허용"**이 체크되어 있어야 합니다.
3. **가상 환경 활성화:** `.venv` 가상 환경이 설정되어 있고 필요한 패키지가 설치되어 있어야 합니다.
4. **의존성 설치:** 처음 실행하는 환경에서는 `make install`을 먼저 실행합니다. `make test`는 `pytest`가 설치되어 있어야 합니다.

---

## 🚀 1단계: 전체 테스트 및 MT5 연결 확인
파이썬 백엔드의 단위 테스트를 실행합니다. MT5 패키지가 없는 네이티브 Linux 환경에서는 MT5 연결 테스트가 skip될 수 있으며, Wine 환경에서는 실제 연결까지 확인합니다.

```bash
make test
```
*   **성공 시:** 전체 테스트가 통과합니다.
*   **MT5 연결 테스트 실패 시:** MT5 터미널이 켜져 있는지, 환경 변수(`MT5_PATH`)가 올바른지 확인하십시오.

---

## 🚀 2단계: 백엔드 서버(FastAPI) 가동
트레이딩 오케스트레이터(LangGraph)를 제어하는 API 서버를 실행합니다.

```bash
# Native Python 서버 실행 (MT5 미연결, API/문서/일부 테스트용)
make run

# MT5 연동 트레이딩 테스트용
make run-wine
```
서버가 성공적으로 시작되면 기본적으로 `http://127.0.0.1:8001`에서 요청을 대기합니다. 포트를 바꾸려면 `make run PORT=8002`처럼 실행합니다.
실제 시장 데이터 조회와 live 주문 테스트는 MT5 패키지가 로드되는 Wine Python 환경(`make run-wine`)에서 수행해야 합니다.

---

## 🚀 3단계: 트레이딩 파이프라인 트리거 (실전 테스트)
새로운 터미널을 열어 `curl` 명령어로 특정 종목에 대한 분석 및 매매 루프를 강제로 시작시킵니다.

```bash
# EURUSD 종목에 대해 트레이딩 루프 시작
make trigger SYMBOL=EURUSD TIMEFRAMES=M5 MODE=paper
```

직접 `curl`을 사용할 경우 `timeframes`는 문자열이 아니라 JSON 배열이어야 합니다.

```bash
curl -X POST http://localhost:8001/api/v1/trade/trigger \
     -H "Content-Type: application/json" \
     -d '{"symbol": "EURUSD", "timeframes": ["M5"], "mode": "paper"}'
```

---

## 🚀 4단계: 실행 로그 및 결과 모니터링
서버 터미널의 로그를 통해 다음 단계가 정상적으로 수행되는지 확인합니다.

1.  **Data Fetch:** MT5에서 실제 시장 데이터 수집 여부
2.  **Tech Analysis:** 기술 분석가의 횡보장 판단 여부 (횡보 시 여기서 종료)
3.  **Strategy Hypothesis:** 전략가의 매매 가설 수립
4.  **Chief Trader Decision:** 최종 BUY/SELL/WAIT 결정
5.  **Guardrails Check:** 리스크 관리 규칙 통과 여부 및 랏(Lot) 수 재계산
6.  **Execution:** 주문 전송 시도
7.  **Position Tracking:** 주문 성공 시 `trading_logs/tracked_positions.json`에 열린 포지션 기록
8.  **Post-Close Review:** 포지션이 청산된 뒤에만 `trading_logs/review_*.md` 생성

### 4-1. 청산 동기화 및 복기 생성
서버에는 자동 reconcile 루프가 있으며 기본 30초마다 추적 중인 포지션의 청산 여부를 확인합니다. 간격은 서버 실행 전에 `POSITION_RECONCILE_INTERVAL_SECONDS` 환경 변수로 조절할 수 있습니다.

수동으로 즉시 확인하려면 다음 명령을 사용합니다.

```bash
make reconcile
```

또는 직접 API를 호출합니다.

```bash
curl -X POST http://localhost:8001/api/v1/trade/reconcile
```

응답의 `reviewed_count`가 1 이상이면 청산된 포지션에 대해 Risk Reviewer가 실행된 것입니다. 복기 파일은 `trading_logs/review_*.md`에 저장됩니다.

실전/Paper 운영 중 컴퓨터 재시작, VPS 운영, MT5에서 매매 현황을 확인하는 절차는 [Live/Paper Operation Runbook](./live-operation-runbook.md)을 참고하십시오.

---

## 🚀 5단계: 백테스팅 (Agentic Backtesting)

과거 데이터를 사용하여 전략의 수익성을 시뮬레이션하고 상세 리포트를 생성합니다. 단순한 룰 기반 백테스트가 아닌, **AI 에이전트들의 시간을 과거 특정 시점으로 되돌려 실전과 똑같이 고민하고 매매하게 만드는 시뮬레이션**입니다.

### 백테스트 작동 원리 (Position-Based Logic)
1. **과거 차트 자르기 (Window Slicing):** 현재 시점을 기준으로 과거 100개의 캔들만 잘라 AI에게 제공합니다. AI는 미래를 볼 수 없습니다.
2. **실시간 API 가로채기 (Mocking):** 백테스터가 실시간 MT5 함수(`fetch_ohlcv`, `get_current_price`)를 가로채어 과거 캔들의 종가를 실시간 가격인 것처럼 속여 반환합니다.
3. **포지션 보유:** Chief Trader가 BUY/SELL을 내면 설정된 거래당 리스크 룰이 적용되고, 백테스터는 즉시 미래 전체를 훑어 결과를 확정하지 않습니다. 열린 포지션을 상태로 보유합니다.
4. **청산 판정:** 이후 Step들이 진행되면서 새로 지난 캔들의 high/low가 SL 또는 TP에 닿았는지 확인합니다. 청산되면 PnL을 잔고에 반영하고 그때 Risk Reviewer가 복기를 작성합니다.
5. **종료 처리:** 백테스트 종료 시점까지 열린 포지션이 남아 있으면 마지막 캔들 종가로 `BACKTEST_END` 청산 처리하고 복기합니다.

### 백테스트 파라미터 이해 (Steps vs Candles)
백테스트 로그에 나오는 `step 2/245`와 같은 지표는 다음과 같은 로직으로 계산됩니다:
- **Lookback Window (100 Candles):** AI가 시장 상황을 판단하려면 최소한의 과거 데이터가 필요합니다. 따라서 CSV 데이터의 **첫 100개 캔들**은 분석용 컨텍스트로만 사용하고 매매는 수행하지 않습니다. (실매매에서도 항상 최근 100개 캔들을 가져옵니다.)
- **Step Interval (5 Candles):** 모든 캔들마다 AI를 호출하면 비용이 과다하므로, 기본적으로 **5캔들마다 한 번씩** 판단을 내립니다.
- **계산식:** `(총 캔들 수 - 100) / 5 = 총 Step 수`
- **포지션 보유 중 Step:** 열린 포지션이 있으면 새 AI 판단을 실행하지 않고, 해당 Step까지 경과한 캔들로 기존 포지션의 SL/TP만 확인합니다.
- **설정 변경:** 기본 Step Interval은 5캔들이며, 실행 시 `make backtest-run ... STEP=10`처럼 조절할 수 있습니다.

### 백테스트 속도 튜닝
백테스트는 각 Step마다 LangGraph와 LLM을 호출하므로, 기간이 길거나 `STEP`이 작을수록 오래 걸립니다. 빠른 실험에서는 데이터 기간을 짧게 잡고 `STEP`을 크게 설정한 뒤, 괜찮은 후보만 더 촘촘하게 검증합니다.

권장 워크플로우:
- **빠른 디버깅:** 3~7일 데이터, `STEP=20`
- **전략 감 잡기:** 2주 데이터, `STEP=10`
- **검증용:** 1개월 이상, `STEP=5`
- **최종 검증:** 여러 달을 월별 CSV로 나눠 실행

예시:
```bash
# 1주일치 데이터만 수집
make backtest-fetch SYMBOL=BTCUSD FROM=2025-01-01 TO=2025-01-07 TIMEFRAMES=M15,M30

# M15 기준 20캔들마다 한 번, 즉 약 5시간마다 AI 판단
make backtest-run \
  DATA=backtests/data/BTCUSD_20250101-20250107_M15.csv,backtests/data/BTCUSD_20250101-20250107_M30.csv \
  SYMBOL=BTCUSD \
  TIMEFRAMES=M15,M30 \
  STEP=20 \
  RISK_PCT=0.005
```

`STEP`을 키우면 속도는 빨라지지만 중간 신호를 놓칠 수 있습니다. 따라서 `STEP=20` 결과는 전략 후보를 거르는 용도로 쓰고, 최종 판단은 `STEP=5` 또는 더 짧은 기간의 `STEP=5` 재검증으로 확인합니다.

### 5-1. 과거 데이터 수집
MT5 터미널이 실행 중인 상태에서 Wine Python을 통해 데이터를 수집합니다.
```bash
make backtest-fetch SYMBOL=BTCUSD FROM=2024-01-01 TO=2024-01-31 TIMEFRAMES=M5
```
- 데이터는 `backtests/data/` 디렉토리에 저장됩니다.
- 파일명은 `SYMBOL_YYYYMMDD-YYYYMMDD_TIMEFRAME.csv` 형식입니다. 예: `BTCUSD_20240101-20240131_M5.csv`.

### 5-2. 백테스트 실행 및 리포트 생성
수집된 CSV 파일을 지정하여 백테스트를 실행합니다. `make` 명령어에 파라미터를 전달할 때는 `변수명=값` 형태를 사용해야 합니다.
```bash
# 기본 실행 방법 (DATA 변수 필수)
make backtest-run DATA=backtests/data/BTCUSD_20240101-20240131_M5.csv

# 종목과 타임프레임을 명시적으로 주입하는 방법
make backtest-run DATA=backtests/data/BTCUSD_20240101-20240131_M5.csv SYMBOL=BTCUSD TIMEFRAMES=M5
```
- 완료 후 자동으로 차트와 마크다운 리포트가 생성됩니다.
- 청산된 거래가 있으면 `trading_logs/review_*.md`도 생성됩니다. HOLD/WAIT 또는 포지션 미진입 Step은 복기 파일을 만들지 않습니다.

### 5-3. 백테스트 매매 전략 변경 (Dynamic Strategy Injection)
Agentic Trader는 전략을 파이썬 코드로 하드코딩하지 않습니다. 전략을 변경하려면 다음 단계를 따르세요.
1. **문서 작성:** `docs/trading-strategies/`에 새로운 전략을 마크다운 파일(예: `my_strategy.md`)로 작성합니다.
2. **레지스트리 등록:** `backend/config/strategies_config.json`을 열고 전략 문서와 허용할 시장 상태(`allowed_regimes`)를 매핑합니다.
3. **자동 적용:** 백테스트 실행 시 Tech Analyst가 판독한 시장 상태에 맞춰 해당 마크다운 전략이 자동으로 주입됩니다.

### 5-4. 결과 확인
생성된 리포트는 다음 경로에서 확인할 수 있습니다.
- **마크다운 리포트**: `backtests/reports/backtest_EURUSD_YYYYMMDD.md`
- **시각화 차트**: `backtests/reports/chart_EURUSD_YYYYMMDD.png`
- **원본 결과 JSON**: `backtests/results/backtest_EURUSD_YYYYMMDD_HHMMSS.json`
- **청산 후 복기 로그**: `trading_logs/review_*.md`
- **실전/Paper 추적 상태**: `trading_logs/tracked_positions.json`, `trading_logs/reviewed_trades.json`

### 5-5. Lessons Learned 해석 기준
`Lessons Learned`는 더 이상 Step별 판단 로그가 아닙니다. 다음 조건을 만족할 때만 생성됩니다.

- 백테스트: 열린 포지션이 `TP_HIT`, `SL_HIT`, 또는 `BACKTEST_END`로 닫힌 경우
- Paper: `reconcile`이 현재 가격 기준 TP/SL 도달을 확인한 경우
- Live: `reconcile`이 MT5 open positions/history를 통해 추적 ticket의 청산을 확인한 경우

따라서 주문 직후 `review_*.md`가 바로 생기지 않는 것이 정상입니다. 포지션이 열려 있는 동안에는 `tracked_positions.json`에 상태가 남아 있어야 합니다.

---

> **주의:** 실제 주문 전송 시 반드시 데모 계좌(Demo Account)에서 먼저 충분히 테스트하십시오.
