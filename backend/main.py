from backend.api.app import create_app

app = create_app()

if __name__ == "__main__":
    # Wine 환경 터미널에서 `wine python backend/main.py` 로 직접 실행할 때 쓰입니다.
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8001, reload=True)
