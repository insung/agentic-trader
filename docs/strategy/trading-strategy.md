# Trading Strategies Index

이 문서는 AI 트레이딩 에이전트(`Strategist`)가 참고하고 학습하는 **기초적인 트레이딩 전략들의 인덱스(목차)** 역할을 합니다.

각각의 구체적인 매매 기법과 로직은 `docs/trading-strategies/` 디렉토리에 개별 마크다운 파일로 분리되어 관리되며, **`backend/config/strategies_config.json` (Strategy Registry)** 파일을 통해 각 전략이 어떤 "시장 상태(Market Regime)"에서 동작할지 정의됩니다.

## 🎯 시장 상태 매핑 매트릭스 (Market Regime Matrix)

`Tech Analyst` 에이전트가 시장 상태를 라벨링하면, 파이썬 백엔드가 `strategies_config.json`을 읽고 아래 규칙에 따라 동적으로 관련 전략 문서만 `Strategist` 프롬프트에 주입(Injection)합니다.

| 시장 상태 (Market Regime) | 매매 방향 | 추천 전략 (주입 대상) | 전략 파일 경로 |
| :--- | :--- | :--- | :--- |
| **Bullish (강한 상승장)** | 추세 추종 (Trend Following) | 이동평균선 교차 (골든 크로스), 돌파 매매 | `ma_crossover.md` 등 |
| **Bearish (강한 하락장)** | 추세 추종 (Trend Following) | 이동평균선 교차 (데드 크로스), 돌파 매매 | `ma_crossover.md` 등 |
| **Ranging (횡보장/박스권)** | 역추세 (Mean Reversion) | 볼린저 밴드 이탈, RSI 과매수/과매도 | `bollinger_bands.md`, `rsi_reversal.md` |
| **High Volatility (고변동성장)**| 관망 또는 단기 스캘핑 | 볼린저 밴드 꼬리 매매, 관망(Hold) | `bollinger_bands.md` |

## 🛠️ 커스텀 전략 추가 방법 (Plugin System)

사용자가 새로운 전략을 추가하거나 기존 규칙을 수정하고 싶다면 파이썬 코드를 뜯어고칠 필요가 없습니다.

1.  `docs/trading-strategies/`에 새로운 전략 마크다운 문서를 작성합니다. (예: `my_strategy.md`)
2.  `backend/config/strategies_config.json` 파일을 열고 다음과 같이 등록합니다:
    ```json
    {
      "name": "My Custom Strategy",
      "file": "my_strategy.md",
      "allowed_regimes": ["Bullish", "High Volatility"]
    }
    ```
3.  다음 실행부터 시스템이 지정된 장세에서 자동으로 해당 전략을 로드하여 `Strategist`에게 주입합니다.

---
> 💡 **AI 에이전트 지침:** 파이썬 백엔드가 필터링하여 프롬프트로 주입해 준 전략들만 신뢰하십시오. 현재 시장 상황에 부합하지 않는 전략을 강행하는 "전략 환각(Strategy Hallucination)"을 방지합니다.
