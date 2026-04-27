# Live/Paper Operation Runbook

이 문서는 MT5 데모 계좌 또는 실전 계좌에 연결해 봇을 운영할 때 확인해야 할 절차를 정리합니다.

## VPS란 무엇인가

VPS는 Virtual Private Server의 약자로, 클라우드에서 빌리는 항상 켜져 있는 원격 컴퓨터입니다. AWS, Azure, Google Cloud, Vultr, Hetzner 같은 서비스에서 월 단위로 빌려 사용할 수 있습니다.

트레이딩 봇을 내 노트북이 아니라 VPS에서 실행하면 MT5 터미널과 FastAPI 백엔드를 계속 켜둘 수 있습니다. 자동 매매, 포지션 감시, 청산 후 복기를 안정적으로 운영하려면 로컬 PC보다 VPS가 적합합니다.

## 매매 현황은 어디서 보는가

`MODE=live`로 실행하면 MT5 데모 계좌 또는 실계좌에 실제 주문이 들어갑니다. 이 경우 매매 현황은 MT5 터미널에서 확인합니다.

```bash
make run-wine
make trigger SYMBOL=BTCUSD TIMEFRAMES=M15,M30 MODE=live
```

MT5에서 확인할 항목:

- 열린 포지션
- 진입가
- SL / TP
- 현재 손익
- 청산 이력

`MODE=paper`는 MT5에 주문을 넣지 않는 mock/paper 모드입니다. 이 경우 MT5에는 포지션이 보이지 않으며, 상태는 로컬 파일, SQLite, 서버 로그로 확인합니다.

```text
trading_logs/tracked_positions.json
trading_logs/review_*.md
trading_logs/trading_logs.sqlite
```

## 컴퓨터를 계속 켜둬야 하는가

자동으로 계속 매매, 감시, 복기를 하려면 다음 프로세스가 계속 켜져 있어야 합니다.

- 이 컴퓨터 또는 VPS
- MT5 터미널
- FastAPI 서버 (`make run-wine`)
- position reconcile loop

`MODE=live`로 MT5 계좌에 주문이 이미 들어간 뒤라면, SL/TP는 보통 브로커/MT5 쪽에 등록되어 컴퓨터가 꺼져도 유지됩니다. 다만 컴퓨터가 꺼져 있으면 새 매매 판단, 포지션 청산 감지, `Lessons Learned` 복기 생성은 중단됩니다.

컴퓨터가 꺼져 있을 때 중단되는 것:

- 새 매매 판단
- 청산 감지
- `trading_logs/review_*.md` 및 `trading_logs/trading_logs.sqlite` 복기 기록 생성
- 자동 운영 루프

## 재시작 후 확인 절차

컴퓨터가 꺼졌다가 다시 켜졌다면 아래 순서로 상태를 복구하고 확인합니다.

1. MT5 실행 및 로그인 확인
   - 데모/실계좌 로그인 상태 확인
   - 자동 매매 허용 확인
   - 거래 종목이 Market Watch에 보이는지 확인

2. 백엔드 실행

```bash
make run-wine
```

3. 서버 상태 확인

```bash
curl http://127.0.0.1:8001/api/v1/health
```

`mt5_available: true`이면 MT5 연동 가능 상태입니다.

4. 추적 중인 포지션 확인

```bash
cat trading_logs/tracked_positions.json
```

여기에 포지션이 남아 있으면, 이전에 봇이 열었지만 아직 복기 완료되지 않은 거래가 있다는 뜻입니다. JSON 파일이 없으면 SQLite의 `tracked_positions` 테이블이 보조 저장소 역할을 합니다.

5. MT5에서 실제 열린 포지션 확인
   - MT5 터미널의 Trade 탭에서 현재 포지션 확인
   - `tracked_positions.json`의 ticket/symbol과 맞는지 확인

6. 청산 동기화 수동 실행

```bash
make reconcile
```

이 명령은 다음 중 하나를 수행합니다.

- 아직 열린 포지션이면 그대로 둠
- 이미 청산된 포지션이면 MT5 이력/현재가를 보고 `review_*.md`와 SQLite `trade_reviews` 생성
- 복기 완료한 ticket은 `trading_logs/reviewed_trades.json` 및 SQLite `reviewed_trade_ids`에 기록

7. 복기 파일 확인

```bash
ls -lt trading_logs/review_*.md | head
```

8. 새 매매 트리거

```bash
make trigger SYMBOL=BTCUSD TIMEFRAMES=M15,M30 MODE=live
```

주의: 이미 열린 포지션이 있다면 새 진입을 막는 정책이 필요합니다. 현재 구조는 추적 파일 기반의 청산 복구를 지원하지만, 재시작 후 MT5 open positions를 기준으로 중복 진입을 강제 차단하는 로직은 추가 개선 대상입니다.
