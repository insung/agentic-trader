.PHONY: test run run-wine trigger cli install venv

# 기본 환경 변수 설정
export PYTHONPATH := .
VENV_BIN := .venv/bin
SYMBOL ?= EURUSD
PORT ?= 8001
WINEPREFIX ?= $(HOME)/.wine

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
	@echo "Triggering a manual trade for $(SYMBOL) on $(TIMEFRAMES)..."
	curl -s -X POST "http://127.0.0.1:$(PORT)/api/v1/trade/trigger" \
		-H "Content-Type: application/json" \
		-d '{"symbol": "$(SYMBOL)", "timeframes": "$(TIMEFRAMES)", "mode": "paper"}' | python3 -m json.tool

# 대화형 CLI 실행
cli:
	@echo "Starting interactive CLI..."
	$(VENV_BIN)/python cli.py --port $(PORT)

install: venv
	@echo "Installing dependencies..."
	$(VENV_BIN)/pip install -r requirements.txt

# --- Backtesting Commands ---
TIMEFRAMES ?= M5,H1
DAYS ?= 30
FROM ?=
TO ?=

# 과거 데이터 수집 (예: make backtest-fetch SYMBOL=EURUSD FROM=2023-01-01 TO=2023-01-31)
backtest-fetch:
	@echo "Fetching historical data for $(SYMBOL) on $(TIMEFRAMES)..."
	WINEPREFIX=$(WINEPREFIX) PYTHONPATH=. wine python -m backend.scripts.fetch_history \
		--symbol $(SYMBOL) \
		--timeframes $(TIMEFRAMES) \
		--days $(DAYS) \
		--from "$(FROM)" \
		--to "$(TO)"

# 백테스트 실행 (DATA 변수에 콤마로 구분된 여러 CSV 경로 지정 가능)
# 예: make backtest-run DATA=backtests/data/EURUSD_M5_...csv,backtests/data/EURUSD_H1_...csv
backtest-run: venv
	@echo "Running agentic backtest using data: $(DATA)..."
	$(VENV_BIN)/python -m backend.scripts.run_backtest --data $(DATA) --symbol $(SYMBOL) --timeframes $(TIMEFRAMES) --report

# 백테스트 데이터 및 결과 정리
backtest-clean:
	@echo "Cleaning backtest data and results..."
	rm -rf backtests/data/*.csv
	rm -rf backtests/results/*.json
	rm -rf docs/trading_logs/backtest_results/*
