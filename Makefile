.PHONY: test run trigger install venv

# 기본 환경 변수 설정
export PYTHONPATH := .
VENV_BIN := .venv/bin

venv:
	@echo "Checking virtual environment..."
	@if [ ! -d ".venv" ]; then python3 -m venv .venv; fi

test: venv
	@echo "Running tests safely without Wine dependency..."
	$(VENV_BIN)/pytest tests/

run: venv
	@echo "Starting FastAPI server..."
	$(VENV_BIN)/uvicorn backend.main:app --reload

trigger:
	@echo "Triggering a manual trade for EURUSD..."
	curl -X POST "http://127.0.0.1:8000/api/v1/trade/trigger?symbol=EURUSD"

install: venv
	@echo "Installing dependencies..."
	$(VENV_BIN)/pip install -r requirements.txt
