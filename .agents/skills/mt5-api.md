---
name: mt5_api_interaction
description: 시장 데이터를 읽어오고 실질적인 체결 주문을 실행하는 백엔드 API 인터페이스 명세입니다.
version: 1.0.0
---
# MT5 API Interaction Skill

**목적:** AI 트레이더 에이전트가 시장 데이타를 읽어오고 실질적인 체결 주문을 실행하는 명세입니다.
_(참고: 현재는 브레인스토밍 구조이므로 Mockup 형태이거나 백엔드 호출의 표준 인터페이스를 정의합니다.)_

## 1. 아키텍처 원칙
에이전트 단에서 파이썬 `MetaTrader5` 라이브러리를 직접 호출하거나 컴파일하지 않습니다. 
대신, 24시간 가동되는 파이썬 기반의 "Trading Backend API" (e.g. FastAPI)를 통해 상호작용합니다. 이를 통해 에이전트는 순수하게 JSON 통신만을 담당합니다.

## 2. 가상의 백엔드 API 명세서 (Agent Interface)

### A. 현재 시장 상태 조회
- **엔드포인트:** `GET /api/v1/market/status?symbol={SYMBOL}&timeframe={TF}`
- **목적:** 현재 호가, 거래량, 스프레드, 주요 지표(RSI 등 백엔드에서 사전 계산) 반환.
- **동작:** 에이전트는 매매 판단 전에 항상 최신 캔들 상태를 이 엔드포인트로 확인해야 합니다.

### B. 주문 실행 명령
- **엔드포인트:** `POST /api/v1/order/execute`
- **Payload 예시:**
  ```json
  {
    "symbol": "EURUSD",
    "order_type": "BUY",
    "volume": 0.1,
    "sl": 1.05500,
    "tp": 1.07000,
    "reason": "MACD 다이버전스 확인 및 RSI 30 상승 돌파"
  }
  ```
- **제약 조건:** `sl`(Stop Loss) 필드는 필수이며, `reason` 필드를 통해 에이전트가 어떤 근거로 체결했는지 로그로 남겨야 합니다.

### C. 계좌 및 열린 포지션 조회
- **엔드포인트:** `GET /api/v1/account/positions`
- **목적:** 현재 증거금 유지도, 떠있는 수익/손실(Floating PnL), 현재 오픈된 계약수 확인. 에이전트는 추가 진입 시 기존 포지션과 역방향인지, 레버리지 한도 내인지를 체크하는데 활용합니다.
