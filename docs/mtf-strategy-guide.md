# 다중 타임프레임(MTF) 전략 시스템 가이드

Agentic Trader는 단일 차트의 시야를 넘어, 여러 타임프레임을 동시에 입체적으로 분석하는 **MTF(Multi-Timeframe) 아키텍처**를 완벽하게 지원합니다. 이 문서는 MTF 전략을 기획하고 시스템에 등록하는 방법을 설명합니다.

---

## 1. MTF 아키텍처의 이해

전통적인 트레이딩 봇들은 하나의 차트(예: 5분봉)만 보고 매매하기 때문에 '거시적 추세(Macro Trend)'를 놓치는 휩소(Whipsaw)에 취약합니다. 

Agentic Trader의 MTF 엔진은 다음과 같이 작동합니다:
1. **데이터 다중 수집:** 파이프라인 시작점(Node 1)에서 사용자가 지정한 타임프레임 리스트(예: `M5, H1`)를 모두 순회하며 차트 데이터를 다운로드합니다.
2. **단일 컨텍스트 주입:** 수집된 여러 차트 데이터를 하나의 거대한 텍스트 블록(프롬프트)으로 묶어 AI 요원에게 제공합니다.
3. **교차 필터링 (가장 중요):** AI(Strategist)는 수집된 데이터를 보고, 자신이 알고 있는 전략들(`strategies_config.json`) 중 **"현재 제공된 타임프레임 조건과 완벽히 일치하는 전략"**만 골라냅니다.

---

## 2. 전략 레지스트리 설정 (`strategies_config.json`)

전략을 시스템에 등록할 때, 해당 전략이 **반드시 요구하는 타임프레임**을 명시할 수 있습니다.

```json
{
  "strategies": [
    {
      "name": "MTF 추세 추종 스캘핑",
      "file": "mtf_example.md",
      "allowed_regimes": ["Bullish", "Bearish"],
      "required_timeframes": ["M5", "H1"],
      "description": "1시간봉으로 거시 추세를 확인하고, 5분봉에서 타점을 잡는 전략"
    }
  ]
}
```

### 💡 작동 원리
- 만약 사용자가 `make backtest-run TIMEFRAMES=M5` 로 백테스트를 돌리면?
  👉 H1 데이터가 부족하므로, AI는 이 전략을 **자동으로 무시**합니다.
- 만약 사용자가 `make backtest-run TIMEFRAMES=M5,H1,D1` 로 백테스트를 돌리면?
  👉 요구사항(`M5, H1`)이 모두 충족되었으므로, AI가 이 전략 문서를 꺼내 읽고 매매 가설을 세웁니다.

---

## 3. MTF 전략 문서 작성법 (Markdown)

`docs/trading-strategies/` 내에 작성하는 마크다운 전략 파일은 인간의 언어로 **"어느 타임프레임에서 무엇을 볼지"** 명확히 지시해야 합니다. `docs/trading-strategies/mtf_example.md` 파일을 열어 구체적인 예시를 확인하세요.

---

## 4. 백테스트 및 실행 방법

다중 타임프레임 백테스트를 실행할 때는, 먼저 요구되는 타임프레임들의 과거 데이터를 SQLite에 적재한 뒤 같은 기간으로 조회합니다.
일반적인 백테스트 체크리스트와 `RISK_PCT` 의미는 [backtesting-guide.md](./backtesting-guide.md)를 기준으로 확인하고, 이 문서에는 MTF 예시만 둡니다.

```bash
# 1. 데이터 다운로드 (M5, H1 동시 다운로드)
make backtest-fetch SYMBOL=BTCUSD FROM=2024-01-01 TO=2024-01-31 TIMEFRAMES=M5,H1

# 2. 백테스트 실행 (SQLite에서 M5, H1 기간 조회)
make backtest-run \
  SYMBOL=BTCUSD \
  TIMEFRAMES=M5,H1 \
  FROM=2024-01-01 \
  TO=2024-01-31
```

> **주의사항 (에러 방지):** 기본 데이터 저장소는 `backtests/data/market_data.sqlite`입니다. `make backtest-fetch`를 먼저 실행하지 않았거나 해당 기간/timeframe 캔들이 없으면 백테스트가 명확한 에러로 중단됩니다.
