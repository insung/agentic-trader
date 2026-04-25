---
description: 트레이딩 봇 서버 구동 및 매매 파이프라인 수동 트리거 운영 워크플로우
---
# Agentic Trader: Bot Operation Workflow (/bot-operate)

이 워크플로우는 실제 트레이딩 봇 서버(FastAPI)를 구동하고, 매매 파이프라인을 트리거하기 위한 운영 지침서입니다.

## 사전 조건
- Wine 환경에서 MT5 터미널이 설치되어 있어야 합니다 (`~/.wine/drive_c/Program Files/MetaTrader 5/`)
- `.env` 파일에 MT5 로그인 정보가 설정되어 있어야 합니다

## 1. 서버 구동 (Background)
Wine Python을 사용하여 MT5가 연결된 FastAPI 서버를 백그라운드로 실행합니다.
Run: `make run-wine`
(주의: 이 명령어를 실행할 때, AI 에이전트는 터미널 옵션 중 `WaitMsBeforeAsync`를 적절히 설정하여 백그라운드 프로세스로 전환되게 만드십시오.)

MT5가 없는 환경에서 테스트하려면 (Mock 모드):
Run: `make run`

## 2. 대화형 CLI로 매매 실행
서버가 켜진 후, 대화형 CLI를 실행하여 종목, 전략, 실행 모드를 선택합니다.
Run: `make cli`

또는 직접 종목을 지정하여 빠르게 트리거할 수도 있습니다:
Run: `make trigger SYMBOL=EURUSD`
Run: `make trigger SYMBOL=XAUUSD`

## 3. 로그 및 매매 일지 모니터링
서버에서 포지션을 성공적으로 체결하고 청산했는지 로그를 점검합니다.
`Risk Reviewer`는 주문 직후가 아니라 포지션 청산 후 실행됩니다. 청산된 거래가 있다면 `trading_logs/` 디렉토리 내에 매매 일지(Markdown)가 생성되는지 확인합니다.
Run: `ls -la trading_logs/`

## 4. 최종 운영 보고
이번 사이클에서 어떤 전략(Strategy)이 주입되었고, 최종 포지션(BUY/SELL)이 어떻게 결정되었는지 요약하여 사용자에게 보고합니다. 가드레일(1% 룰 등)에 막혀 거절되었다면 그 사유도 함께 보고합니다. 시장 휴장(주말)으로 중단되었다면 그 사유도 보고합니다.
