.PHONY: test run run-wine trigger reconcile cli install install-quant venv migrate-legacy-data quant-run quant-summary no-trade-audit

# 기본 환경 변수 설정
export PYTHONPATH := .
VENV_BIN := .venv/bin
SYMBOL ?= EURUSD
PORT ?= 8001
WINEPREFIX ?= $(HOME)/.wine
MODE ?= paper
RISK_PCT ?= 0.005
DATA_DB ?= backtests/data/market_data.sqlite
TRADING_LOG_DB ?= trading_logs/trading_logs.sqlite

venv:
	@echo "Checking virtual environment..."
	@if [ ! -d ".venv" ]; then python3 -m venv .venv; fi

test: venv
	@echo "Running tests safely without Wine dependency..."
	$(VENV_BIN)/pytest tests/

# Linux native Python으로 서버 실행 (MT5 미연결, Mock 모드)
run: venv
	@echo "Starting FastAPI server (native Python, no MT5)..."
	$(VENV_BIN)/uvicorn backend.main:app --reload --port $(PORT)

# Wine Python으로 서버 실행 (MT5 연결)
run-wine:
	@echo "Starting FastAPI server via Wine Python (MT5 connected)..."
	@echo "WINEPREFIX: $(WINEPREFIX)"
	WINEPREFIX=$(WINEPREFIX) PYTHONPATH=. wine python -m uvicorn backend.main:app --host 0.0.0.0 --port $(PORT)

# 수동 트리거 (종목 선택 가능)
trigger:
	@echo "Triggering a manual $(MODE) trade for $(SYMBOL) on $(TRIGGER_TIMEFRAMES)..."
	@TF_JSON=$$(python3 -c 'import json; print(json.dumps("$(TRIGGER_TIMEFRAMES)".split(",")))'); \
	curl -s -X POST "http://127.0.0.1:$(PORT)/api/v1/trade/trigger" \
		-H "Content-Type: application/json" \
		-d "{\"symbol\": \"$(SYMBOL)\", \"timeframes\": $$TF_JSON, \"mode\": \"$(MODE)\"}" | python3 -m json.tool

# 추적 중인 포지션 청산 여부를 수동 확인하고 청산된 거래만 복기
reconcile:
	@echo "Reconciling tracked positions..."
	curl -s -X POST "http://127.0.0.1:$(PORT)/api/v1/trade/reconcile" | python3 -m json.tool

# 대화형 CLI 실행
cli:
	@echo "Starting interactive CLI..."
	$(VENV_BIN)/python tools/trade_cli.py --port $(PORT)

install: venv
	@echo "Installing dependencies..."
	$(VENV_BIN)/pip install -r requirements.txt

install-quant: install
	@echo "Installing optional quant research dependencies..."
	$(VENV_BIN)/pip install -r requirements-quant.txt

# --- Backtesting Commands ---
TIMEFRAME ?= M15
TIMEFRAMES ?=
DAYS ?= 30
FROM ?=
TO ?=
STEP ?= 5
START_STEP ?=
MAX_STEPS ?=
NO_REVIEW ?= 0
LOG_FILE ?=
LOG_LEVEL ?= TRACE

DEFAULT_TIMEFRAMES := M15,M30
TRIGGER_TIMEFRAMES := $(strip $(TIMEFRAMES))
ifeq ($(TRIGGER_TIMEFRAMES),)
TRIGGER_TIMEFRAMES := $(DEFAULT_TIMEFRAMES)
endif
BACKTEST_RUN_TIMEFRAMES := $(strip $(TIMEFRAMES))
ifeq ($(BACKTEST_RUN_TIMEFRAMES),)
BACKTEST_RUN_TIMEFRAMES := $(DEFAULT_TIMEFRAMES)
endif
BACKTEST_FETCH_TIMEFRAMES := $(strip $(TIMEFRAMES))
ifeq ($(BACKTEST_FETCH_TIMEFRAMES),)
BACKTEST_FETCH_TIMEFRAMES := $(strip $(TIMEFRAME))
endif
ifeq ($(BACKTEST_FETCH_TIMEFRAMES),)
BACKTEST_FETCH_TIMEFRAMES := $(DEFAULT_TIMEFRAMES)
endif

BACKTEST_ARGS = --data-db "$(DATA_DB)" --symbol $(SYMBOL) --timeframes $(BACKTEST_RUN_TIMEFRAMES) --risk-pct $(RISK_PCT) --step $(STEP) --report
ifneq ($(START_STEP),)
BACKTEST_ARGS += --start-step $(START_STEP)
endif
ifneq ($(MAX_STEPS),)
BACKTEST_ARGS += --max-steps $(MAX_STEPS)
endif
ifeq ($(NO_REVIEW),1)
BACKTEST_ARGS += --no-review
endif
ifneq ($(LOG_FILE),)
BACKTEST_ARGS += --log-file "$(LOG_FILE)"
endif
ifneq ($(LOG_LEVEL),)
BACKTEST_ARGS += --log-level $(LOG_LEVEL)
endif

# 과거 데이터 수집 (예: make backtest-fetch SYMBOL=EURUSD FROM=2023-01-01 TO=2023-01-31)
backtest-fetch:
	@echo "Fetching historical data for $(SYMBOL) on $(BACKTEST_FETCH_TIMEFRAMES)..."
	WINEPREFIX=$(WINEPREFIX) PYTHONPATH=. wine python -m backend.scripts.fetch_history \
		--symbol $(SYMBOL) \
		--timeframes $(BACKTEST_FETCH_TIMEFRAMES) \
		--days $(DAYS) \
		--from "$(FROM)" \
		--to "$(TO)" \
		--data-db "$(DATA_DB)"

# 백테스트 실행 (기본: SQLite, 호환: DATA 변수에 콤마로 구분된 CSV 경로 지정 가능)
# 예: make backtest-run SYMBOL=BTCUSD TIMEFRAMES=M15,M30 FROM=2025-01-01 TO=2025-02-28
backtest-run: venv
	@if [ -n "$(DATA)" ]; then \
		echo "Running agentic backtest using legacy CSV data: $(DATA)..."; \
		$(VENV_BIN)/python -m backend.scripts.run_backtest --data "$(DATA)" $(BACKTEST_ARGS); \
	else \
		if [ -z "$(FROM)" ] || [ -z "$(TO)" ]; then echo "FROM and TO are required for SQLite backtests. Example: make backtest-run SYMBOL=BTCUSD TIMEFRAMES=M15,M30 FROM=2025-01-01 TO=2025-02-28"; exit 1; fi; \
		echo "Running agentic backtest from SQLite $(DATA_DB) ($(FROM) ~ $(TO))..."; \
		$(VENV_BIN)/python -m backend.scripts.run_backtest $(BACKTEST_ARGS) --from "$(FROM)" --to "$(TO)"; \
	fi

QUANT_STRATEGY ?= bollinger
INIT_CASH ?= 10000
FEES ?= 0
SLIPPAGE ?= 0
FILTER_TIMEFRAME ?=
BB_WINDOWS ?= 14,20,30
BB_STDS ?= 1.8,2.0,2.2
RSI_LOWERS ?= 25,30,35
RSI_UPPERS ?= 65,70,75
FILTER_RSI_LOWS ?= 45
FILTER_RSI_HIGHS ?= 55
RRS ?= 1.3,1.5,2.0
STOP_PCTS ?= 0.01
EMA_FAST_WINDOWS ?= 20
EMA_SLOW_WINDOWS ?= 50
PULLBACK_ATRS ?= 0.25,0.5,0.75
ATR_STOP_MULTIPLIERS ?= 1.0,1.5
TREND_RSI_LOWERS ?= 45
TREND_RSI_UPPERS ?= 55
RECLAIM_LOOKBACKS ?= 3,5,8
COOLDOWN_BARS ?= 8,12,20
MA_ADX_MINS ?= 25,30
MA_MAX_CROSS_AGE_BARS ?= 3,6
BREAKOUT_LOOKBACKS ?= 20,30,50
BREAKOUT_ATR_BUFFERS ?= 0.0,0.25,0.5
BREAKOUT_RSI_LOWERS ?= 50,55
BREAKOUT_RSI_UPPERS ?= 45,50
MACD_FAST_WINDOWS ?= 12
MACD_SLOW_WINDOWS ?= 26
MACD_SIGNAL_WINDOWS ?= 9
VEB_LOOKBACKS ?= 30,45,60
VEB_ATR_EXPANSIONS ?= 1.5,2.0
VEB_ADX_MINS ?= 20,25
VEB_SL_ATR_BUFFERS ?= 0.5
RANDOM_SEED ?= 42
RANDOM_ENTRY_PROB ?= 0.01
RANDOM_LONG_BIAS ?= 0.5
RANDOM_MIN_HOLD_BARS ?= 3
RANDOM_MAX_HOLD_BARS ?= 12
TOP ?= 10
SUMMARY_LIMIT ?= 50
SUMMARY_STRATEGY ?=
SUMMARY_RUN_ID ?=
SUMMARY_SYMBOL ?=
SUMMARY_MONTHLY ?= 0
SUMMARY_MONTHLY_FLAG :=
ifeq ($(SUMMARY_MONTHLY),1)
SUMMARY_MONTHLY_FLAG := --monthly
endif
SUMMARY_SYMBOL_ARG :=
ifeq ($(strip $(SUMMARY_SYMBOL)),)
ifneq ($(strip $(SUMMARY_RUN_ID)),)
SUMMARY_SYMBOL_ARG :=
else
SUMMARY_SYMBOL_ARG := --symbol $(SYMBOL)
endif
else
SUMMARY_SYMBOL_ARG := --symbol $(SUMMARY_SYMBOL)
endif

quant-run: venv
	@if [ -z "$(FROM)" ] || [ -z "$(TO)" ]; then echo "FROM and TO are required for quant research. Example: make quant-run SYMBOL=BTCUSD TIMEFRAME=M15 FROM=2025-01-01 TO=2025-01-31"; exit 1; fi
	$(VENV_BIN)/python -m backend.scripts.run_quant_research \
		--data-db "$(DATA_DB)" \
		--symbol $(SYMBOL) \
		--timeframe $(TIMEFRAME) \
		$(if $(FILTER_TIMEFRAME),--filter-timeframe $(FILTER_TIMEFRAME),) \
		--from "$(FROM)" \
		--to "$(TO)" \
		--strategy $(QUANT_STRATEGY) \
		--init-cash $(INIT_CASH) \
		--fees $(FEES) \
		--slippage $(SLIPPAGE) \
		--bb-windows "$(BB_WINDOWS)" \
		--bb-stds "$(BB_STDS)" \
		--rsi-lowers "$(RSI_LOWERS)" \
		--rsi-uppers "$(RSI_UPPERS)" \
		--filter-rsi-lows "$(FILTER_RSI_LOWS)" \
		--filter-rsi-highs "$(FILTER_RSI_HIGHS)" \
		--rrs "$(RRS)" \
		--stop-pcts "$(STOP_PCTS)" \
		--ema-fast-windows "$(EMA_FAST_WINDOWS)" \
		--ema-slow-windows "$(EMA_SLOW_WINDOWS)" \
		--pullback-atrs "$(PULLBACK_ATRS)" \
		--atr-stop-multipliers "$(ATR_STOP_MULTIPLIERS)" \
		--trend-rsi-lowers "$(TREND_RSI_LOWERS)" \
		--trend-rsi-uppers "$(TREND_RSI_UPPERS)" \
		--reclaim-lookbacks "$(RECLAIM_LOOKBACKS)" \
		--cooldown-bars "$(COOLDOWN_BARS)" \
		--ma-adx-mins "$(MA_ADX_MINS)" \
		--ma-max-cross-age-bars "$(MA_MAX_CROSS_AGE_BARS)" \
		--breakout-lookbacks "$(BREAKOUT_LOOKBACKS)" \
		--breakout-atr-buffers "$(BREAKOUT_ATR_BUFFERS)" \
		--breakout-rsi-lowers "$(BREAKOUT_RSI_LOWERS)" \
		--breakout-rsi-uppers "$(BREAKOUT_RSI_UPPERS)" \
		--macd-fast-windows "$(MACD_FAST_WINDOWS)" \
		--macd-slow-windows "$(MACD_SLOW_WINDOWS)" \
		--macd-signal-windows "$(MACD_SIGNAL_WINDOWS)" \
		--veb-lookbacks "$(VEB_LOOKBACKS)" \
		--veb-atr-expansions "$(VEB_ATR_EXPANSIONS)" \
		--veb-adx-mins "$(VEB_ADX_MINS)" \
		--veb-sl-atr-buffers "$(VEB_SL_ATR_BUFFERS)" \
		--random-seed $(RANDOM_SEED) \
		--random-entry-prob $(RANDOM_ENTRY_PROB) \
		--random-long-bias $(RANDOM_LONG_BIAS) \
		--random-min-hold-bars $(RANDOM_MIN_HOLD_BARS) \
		--random-max-hold-bars $(RANDOM_MAX_HOLD_BARS) \
		--top $(TOP)

quant-summary: venv
	$(VENV_BIN)/python -m backend.scripts.summarize_quant_research \
		--data-db "$(DATA_DB)" \
		$(if $(SUMMARY_RUN_ID),--run-id $(SUMMARY_RUN_ID),) \
		$(SUMMARY_SYMBOL_ARG) \
		$(if $(FROM),--from "$(FROM)",) \
		$(if $(TO),--to "$(TO)",) \
		$(if $(SUMMARY_STRATEGY),--strategy $(SUMMARY_STRATEGY),) \
		$(SUMMARY_MONTHLY_FLAG) \
		--limit $(SUMMARY_LIMIT)

no-trade-audit: venv
	@if [ -z "$(RUN_ID)" ]; then echo "RUN_ID is required. Example: make no-trade-audit RUN_ID=BT-123"; exit 1; fi
	$(VENV_BIN)/python -m backend.scripts.run_no_trade_audit \
		--data-db "$(DATA_DB)" \
		--run-id "$(RUN_ID)"

migrate-legacy-data: venv
	@echo "Migrating legacy backtest/trading log artifacts into SQLite..."
	$(VENV_BIN)/python -m backend.scripts.migrate_legacy_data --backtest-db "$(DATA_DB)" --trading-log-db "$(TRADING_LOG_DB)"

# 백테스트 데이터 및 결과 정리
backtest-clean:
	@echo "Cleaning backtest data and results..."
	rm -rf backtests/data/*.csv
	rm -rf backtests/results/*.json
	rm -rf backtests/reports/*
