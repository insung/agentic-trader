# Agentic Trader: Bot Operation Workflow (/bot-operate)

이 워크플로우는 실제 트레이딩 봇 서버(FastAPI)를 구동하고, 백그라운드에서 동작 상태를 모니터링하기 위한 운영 지침서입니다.

## 1. 서버 구동 (Background)
백그라운드에서 봇 서버를 실행합니다.
Run: `make run`
(주의: 이 명령어를 실행할 때, AI 에이전트는 터미널 옵션 중 `WaitMsBeforeAsync`를 적절히 설정하여 백그라운드 프로세스로 전환되게 만드십시오.)

## 2. 수동 트레이드 사이클 1회 가동
서버가 켜진 후, 1~2초 대기했다가 AI 매매 파이프라인을 1회 호출합니다.
Run: `make trigger`

## 3. 로그 및 매매 일지 모니터링
서버에서 포지션을 성공적으로 체결하고 청산했는지 로그를 점검합니다.
특히 5단계 `Risk Reviewer` 에이전트가 `docs/trading_logs/` 디렉토리 내에 매매 일지(Markdown)를 성공적으로 생성했는지 확인합니다.
Run: `ls -la docs/trading_logs/`

## 4. 최종 운영 보고
이번 사이클에서 어떤 전략(Strategy)이 주입되었고, 최종 포지션(BUY/SELL)이 어떻게 결정되었는지 요약하여 사용자에게 보고합니다. 가드레일(1% 룰 등)에 막혀 거절되었다면 그 사유도 함께 보고합니다.
