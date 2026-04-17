# 시스템 테스트 및 실행 가이드 (Testing & Execution Guide)

이 문서는 Agentic Trader 시스템의 개별 모듈 및 전체 파이프라인(End-to-End)이 정상적으로 작동하는지 확인하기 위한 테스트 절차를 안내합니다.

## 📋 사전 준비 사항 (Prerequisites)
1. **MetaTrader 5 실행:** Wine 환경에서 MT5 터미널이 실행 중이어야 합니다.
2. **자동 매매 허용:** MT5의 `[도구] -> [옵션] -> [전문가 조언자]` 탭에서 **"알고리즘 매매 허용"**이 체크되어 있어야 합니다.
3. **가상 환경 활성화:** `.venv` 가상 환경이 설정되어 있고 필요한 패키지가 설치되어 있어야 합니다.

---

## 🚀 1단계: MT5 API 연결 테스트
파이썬 백엔드가 Wine 내부의 MT5 터미널과 통신할 수 있는지 확인합니다.

```bash
# 프로젝트 루트 디렉토리에서 실행
PYTHONPATH=. .venv/bin/python tests/test_mt5_connection.py
```
*   **성공 시:** `MT5 initialized successfully` 메시지가 출력됩니다.
*   **실패 시:** MT5 터미널이 켜져 있는지, 환경 변수(`MT5_PATH`)가 올바른지 확인하십시오.

---

## 🚀 2단계: 백엔드 서버(FastAPI) 가동
트레이딩 오케스트레이터(LangGraph)를 제어하는 API 서버를 실행합니다.

```bash
# 서버 실행 (로그 확인을 위해 터미널 창 유지)
PYTHONPATH=. .venv/bin/python backend/main.py
```
서버가 성공적으로 시작되면 `http://0.0.0.0:8000`에서 요청을 대기합니다.

---

## 🚀 3단계: 트레이딩 파이프라인 트리거 (실전 테스트)
새로운 터미널을 열어 `curl` 명령어로 특정 종목에 대한 분석 및 매매 루프를 강제로 시작시킵니다.

```bash
# EURUSD 종목에 대해 트레이딩 루프 시작
curl -X POST http://localhost:8000/api/v1/trade/trigger \
     -H "Content-Type: application/json" \
     -d '{"symbol": "EURUSD"}'
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

---

## 🛡️ 모의 투자(Paper Trading)와 실전 주문 전환
현재 시스템은 안전을 위해 기본적으로 **모의 주문(`execute_mock_order`)**을 실행하도록 설정되어 있습니다.

### 실제 계좌에 주문을 넣으려면:
`backend/main.py` 파일의 `run_trading_workflow` 함수 하단에서 주문 실행 부분을 다음과 같이 수정하십시오.

*   **가상 주문 (기본값):**
    ```python
    execute_mock_order(symbol, action, safe_lot_size, sl, tp, entry_price)
    ```
*   **실제 주문 전송:**
    ```python
    send_market_order(symbol, action, safe_lot_size, sl, tp)
    ```

> **주의:** 실제 주문 전송 시 반드시 데모 계좌(Demo Account)에서 먼저 충분히 테스트하십시오.
