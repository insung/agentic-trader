.PHONY: test run install

# 기본 환경 변수 설정
export PYTHONPATH := .

test:
	@echo "Running tests safely without Wine dependency..."
	pytest tests/

run:
	@echo "Starting FastAPI server..."
	uvicorn backend.main:app --reload

trigger:
	@echo "Triggering a manual trade for EURUSD..."
	curl -X POST "http://127.0.0.1:8000/api/v1/trade/trigger?symbol=EURUSD"

install:
	@echo "Installing dependencies..."
	pip install -r requirements.txt
