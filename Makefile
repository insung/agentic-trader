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
	@echo "Triggering a manual trade for $(SYMBOL)..."
	curl -s -X POST "http://127.0.0.1:$(PORT)/api/v1/trade/trigger" \
		-H "Content-Type: application/json" \
		-d '{"symbol": "$(SYMBOL)", "mode": "paper"}' | python3 -m json.tool

# 대화형 CLI 실행
cli:
	@echo "Starting interactive CLI..."
	$(VENV_BIN)/python cli.py --port $(PORT)

install: venv
	@echo "Installing dependencies..."
	$(VENV_BIN)/pip install -r requirements.txt
