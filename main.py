"""
PCChecker - PC診断・アップグレード提案アプリ - FastAPIバックエンド
"""

import webbrowser
import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from pc_analyzer import run_analysis

app = FastAPI(title="PCChecker", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = BASE_DIR / "templates" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/api/analyze", response_class=JSONResponse)
async def analyze():
    """PCスペックを分析してJSON形式で返す"""
    try:
        result = run_analysis()
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "message": "スペック取得に失敗しました。管理者権限で実行してください。"},
        )


def open_browser():
    time.sleep(1.2)
    webbrowser.open("http://localhost:8000")


if __name__ == "__main__":
    import uvicorn

    threading.Thread(target=open_browser, daemon=True).start()
    print("PCChecker を起動中...")
    print("ブラウザが自動で開きます → http://localhost:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
