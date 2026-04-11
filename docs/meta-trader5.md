# MetaTrader 5 (MT5) Python API Quickstart

이 문서는 `MetaTrader5` 파이썬 라이브러리를 사용하여 트레이딩 계좌와 연동하는 핵심 기능들을 요약합니다.

## 1. 설치 및 필수 조건

- **플랫폼:** `MetaTrader5` 라이브러리는 **Windows 환경**에서만 공식적으로 지원됩니다. MT5 데스크톱 터미널이 설치되어 있어야 합니다.
- **Linux/macOS:** Wine과 같은 에뮬레이터를 사용하여 MT5 터미널을 실행하는 환경에서 파이썬 스크립트를 구동해야 합니다.

```bash
pip install MetaTrader5
```

## 2. MT5 터미널 연결 및 해제

가장 먼저 `initialize()` 함수를 호출하여 로컬에 설치된 MT5 터미널과 IPC 통신을 시작합니다.

```python
import MetaTrader5 as mt5

# MT5 터미널에 연결
if not mt5.initialize():
    print(f"initialize() failed, error code = {mt5.last_error()}")
    quit()

print("MetaTrader 5 connection successful")

# 작업 완료 후 연결 종료
# mt5.shutdown()
```

## 3. 계좌 정보 조회

`account_info()` 함수를 통해 현재 잔고, 레버리지 등 주요 계좌 정보를 확인할 수 있습니다.

```python
# 현재 계좌 정보 가져오기
account_info = mt5.account_info()
if account_info is not None:
    print(f"Login: {account_info.login}")
    print(f"Balance: {account_info.balance}")
    print(f"Leverage: {account_info.leverage}")
```

## 4. 시장 데이터 (시세) 조회

### 현재가 (Tick) 정보

`symbol_info_tick()` 함수로 특정 심볼의 현재 매수/매도 호가를 얻습니다.

```python
tick = mt5.symbol_info_tick("EURUSD")
if tick is not None:
    print(f"EURUSD | Ask: {tick.ask}, Bid: {tick.bid}")
```

### 과거 데이터 (OHLCV 캔들)

`copy_rates_from_pos()` 함수를 사용하면 특정 시점부터 지정된 개수의 봉 데이터를 가져올 수 있어, 이동평균선 등 기술적 지표 계산의 기반이 됩니다.

```python
import pandas as pd
from datetime import datetime

# 현재 시점부터 EURUSD 1시간봉 100개 요청
rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_H1, 0, 100)

# Pandas DataFrame으로 변환하여 분석 용이성 확보
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')

print(df.tail()) # 최근 5개 캔들 데이터 출력
```

## 5. 주문 실행 (매수/매도)

`order_send()` 함수에 약속된 형식의 `request` 딕셔너리를 전달하여 주문을 넣습니다.

- **안전장치:** 손실제한(`sl`) 및 이익실현(`tp`) 가격을 설정하는 것이 매우 중요합니다.
- **주문 유형:** 시장가(`ORDER_TYPE_BUY`, `ORDER_TYPE_SELL`), 지정가 등 다양한 주문 방식이 있습니다.

```python
symbol = "EURUSD"
lot_size = 0.1
point = mt5.symbol_info(symbol).point
price = mt5.symbol_info_tick(symbol).ask

# 시장가 매수 주문 예시
request = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": symbol,
    "volume": lot_size,
    "type": mt5.ORDER_TYPE_BUY,
    "price": price,
    "sl": price - 100 * point,  # 현재가보다 100포인트 아래에 손절 설정
    "tp": price + 100 * point,  # 현재가보다 100포인트 위에 익절 설정
    "magic": 123456, # 매매 전략을 구분하는 고유 번호
    "comment": "ai-trader-test",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_IOC,
}

# 주문 전송
result = mt5.order_send(request)
if result.retcode != mt5.TRADE_RETCODE_DONE:
    print(f"Order failed, retcode={result.retcode}")
else:
    print(f"Order executed, ticket ID: {result.order}")
```

이 문서는 AI 에이전트가 트레이딩을 수행하기 위해 필요한 최소한의 핵심 기능 위주로 정리되었습니다. 전체 API 문서는 MQL5 공식 커뮤니티를 참조하세요.
