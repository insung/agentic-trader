# Agentic Trader MVP Implementation Plan (Custom API Architecture)

의견을 전적으로 수용합니다. 외부 오픈소스 MCP 서버 라이브러리에 설계가 종속될 경우, 추후 유지보수나 커스텀 안전 규칙(Safety Rules) 적용에 한계를 겪게 됩니다. 따라서 **자체 개발 API 서버(FastAPI) 백엔드를 중앙에 두는 최초의 견고한 설계**로 전면 회귀하여 다시 계획을 세웁니다.

## User Review Required

이 아키텍처는 에이전트의 스킬, API 서버, 그리고 규칙 문서를 모두 우리의 컨트롤 하에 두어 완벽한 자유도와 커스텀 안전 장치(하드 손절매 등)를 보장합니다. 아래의 프로젝트 구조 및 파이프라인이 최초로 구상하신 형태와 일치하는지 확인해 주세요.

---

## 🏗 프로젝트 디렉토리 구조 (Directory Architecture)

```text
agentic-trader/
├── .gemini/                 # AI 에이전트를 위한 핵심 프레임워크 (Antigravity 표준 호환)
│   ├── agents/              # AI 페르소나 및 강제 룰 (예: trader.md)
│   ├── rules/               # 이 시스템 구동과 관련된 글로벌 설정 규칙
│   ├── skills/              # 에이전트가 백엔드 API를 콜(호출)할 때 쓰는 커스텀 도구들
│   └── workflows/           # 안티그래비티 기반 능동 루프 파이프라인 (예: trade_loop)
├── backend/                 # 자체 개발 Trading API 서버 (Python + FastAPI)
│   ├── api/                 # REST API 엔드포인트 라우터 (MT5, TradingView 웹훅)
│   ├── core/                # 안전 락(Lock), 3% 손실 제한 등 절대 방어 비즈니스 로직
│   └── main.py              # 서버 실행 진입점
├── infra/                   # Linux(Wine) 구동 스크립트 및 환경 구성 자동화 스크립트
├── strategies/              # 매매 수학 모델, 보조 지표 계산 등 순수 퀀트 로직
├── backtests/               # 과거 데이터를 바탕으로 한 전략 백테스팅(시뮬레이션) 환경
├── tests/                   # 개별 API 통신 및 모듈 단위 테스트 (단위 테스트 전용)
└── docs/                    # 브레인스토밍 문서, 참조 API 스펙 저장소
```

---

## 🧩 외부 플랫폼(API) 연동 전략 설계

종속성을 피하기 위해 우리가 직접 래핑(Wrapping)하는 전략입니다.

### 1. MetaTrader 5 (MT5) 직접 연동 (Time-Series Data 포함)
- **구조:** `MetaTrader5` 파이썬 패키지를 서버 내부에서 직접 호출합니다.
- **데이터 공급 (OHLCV):** MT5 API는 단순 현재가뿐만 아니라 1분봉(M1), 시간봉(H1), 일봉(D1) 등 완벽한 **과거 시계열 캔들 데이터(OHLCV)**를 네이티브로 제공합니다. 이를 정제하여 `GET /api/v1/market/candlesticks?symbol=BTCUSD&timeframe=H1` 형태의 통일된 엔드포인트를 열어줍니다. 이를 통해 에이전트가 트레이딩뷰 없이도 이전 가격 흐름과 추세를 스스로 분석할 수 있습니다.
- **안전 주문 설계:** 매매는 오직 `POST /api/v1/order/execute` 하나의 창구로만 통일하며, 백엔드 서버에서 반드시 `Stop-Loss` 제약 검증 후 MT5 터미널로 쏘는 구조를 갖습니다.
- **(트레이딩뷰 배제):** 공식 API 부재 및 우회 연동의 불안정성을 고려하여 기존 계획에서 TradingView 통합을 완전히 제거합니다. 모든 가격 데이터 검토는 100% MT5 API에서 공급받습니다.

---

## 🚀 단계별 구현 계획 (Phased Implementation)

### Phase 1: Custom FastAPI 백엔드 뼈대 구축 및 Wine 기동
본질적으로 OS 제약(Linux)은 그대로이므로, 백엔드 서버가 구동될 위치 자체는 윈도우 에뮬리케이션 계층이어야 합니다.
1. `backend/` 디렉토리에 FastAPI 초기 코드를 작성.
2. 이 FastAPI 서버가 **Wine 내부 파이썬 환경**에서 로컬 `localhost:8000`으로 런들되도록 인프라 스크립트를 조정합니다.
3. Linux Mint 시스템 로컬 도구를 이용해 `curl localhost:8000/api/v1/health` 통신 성공을 확인.

### Phase 2: 안전 매매 API 구축
1. 백엔드 코어에 "지정된 SL(손실제한) 범위를 넘을 경우 Reject(기각)"하는 하드코딩 필터 알고리즘 구현.
2. `MetaTrader5` 라이브러리를 사용해 데모 계좌에 실제로 주문 파라미터를 쏘는 기능 작성.

### Phase 3: 에이전트 스킬 연결 및 자동 테스트
1. `.gemini/skills/` 폴더 내에, 에이전트가 셸에서 쉽게 실행할 클라이언트용 파이썬(혹은 셸) 스크립트 작성 (`python .gemini/skills/execute.py --action BUY ...`).
2. 에이전트(Antigravity)를 켜고 `/trade_loop`를 통해 자동 매매를 지시.
3. 에이전트 -> 스킬 툴 -> 로컬 백엔드 서버 -> 차단 필터 -> MT5 체결 순으로 완벽히 에어갭(Air-gap)이 분리된 3단계 검증 구조 확립.
