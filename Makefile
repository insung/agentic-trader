.PHONY: test run run-wine trigger reconcile cli install venv migrate-legacy-data

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
	@echo "Triggering a manual $(MODE) trade for $(SYMBOL) on $(TIMEFRAMES)..."
	@TF_JSON=$$(python3 -c 'import json; print(json.dumps("$(TIMEFRAMES)".split(",")))'); \
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

# --- Backtesting Commands ---
TIMEFRAMES ?= M15,M30
DAYS ?= 30
FROM ?=
TO ?=
STEP ?= 5
START_STEP ?=
MAX_STEPS ?=
NO_REVIEW ?= 0
LOG_FILE ?=
LOG_LEVEL ?= TRACE

BACKTEST_ARGS = --data-db "$(DATA_DB)" --symbol $(SYMBOL) --timeframes $(TIMEFRAMES) --risk-pct $(RISK_PCT) --step $(STEP) --report
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
	@echo "Fetching historical data for $(SYMBOL) on $(TIMEFRAMES)..."
	WINEPREFIX=$(WINEPREFIX) PYTHONPATH=. wine python -m backend.scripts.fetch_history \
		--symbol $(SYMBOL) \
		--timeframes $(TIMEFRAMES) \
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

migrate-legacy-data: venv
	@echo "Migrating legacy backtest/trading log artifacts into SQLite..."
	$(VENV_BIN)/python -m backend.scripts.migrate_legacy_data --backtest-db "$(DATA_DB)" --trading-log-db "$(TRADING_LOG_DB)"

# 백테스트 데이터 및 결과 정리
backtest-clean:
	@echo "Cleaning backtest data and results..."
	rm -rf backtests/data/*.csv
	rm -rf backtests/results/*.json
	rm -rf backtests/reports/*
