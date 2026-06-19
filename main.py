"""
PCChecker - PC診断・アップグレード提案アプリ - FastAPIバックエンド
"""

import socket
import sys
import threading
import urllib.request
import webbrowser

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app_paths import data_dir, is_frozen, resource_dir
from pc_analyzer import run_analysis
from rakuten_client import is_available, search_bto, search_part
from feedback_client import submit_feedback
from desktop_shortcut import create_desktop_shortcut

app = FastAPI(title="PCChecker", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = resource_dir()
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


@app.get("/api/price", response_class=JSONResponse)
def price(q: str, ref: int = 0):
    """パーツ名から楽天市場の実勢価格とアフィリエイトリンクを返す

    同期defで定義しFastAPIのスレッドプールで実行する(rakuten_client側の
    ロックとレート制限により、同時リクエストはAPI呼び出しとしては直列化される)。
    """
    if not q.strip():
        return JSONResponse(status_code=400, content={"ok": False, "reason": "empty_query"})
    if not is_available():
        return {"ok": False, "reason": "not_configured"}
    try:
        result = search_part(q, ref_price=ref or None)
    except Exception:
        return {"ok": False, "reason": "error"}
    if result is None:
        return {"ok": False, "reason": "no_match"}
    return {"ok": True, **result}


@app.get("/api/bto", response_class=JSONResponse)
def bto(q: str, ref: int):
    """買い替え候補のBTO PC(最大3件)を楽天市場から返す"""
    if not q.strip() or ref <= 0:
        return JSONResponse(status_code=400, content={"ok": False, "reason": "bad_request"})
    if not is_available():
        return {"ok": False, "reason": "not_configured"}
    try:
        items = search_bto(q, ref_price=ref)
    except Exception:
        return {"ok": False, "reason": "error"}
    return {"ok": True, "items": items}


class FeedbackIn(BaseModel):
    category: str
    comment: str
    include_diagnostics: bool = False
    diagnostics: dict | None = None


@app.post("/api/feedback", response_class=JSONResponse)
def feedback(body: FeedbackIn):
    """アプリ内フィードバック(不具合報告・要望)を送信先へ転送する"""
    # 添付しない指定なら診断データは送らない
    diag = body.diagnostics if body.include_diagnostics else None
    try:
        return submit_feedback(body.category, body.comment, diag)
    except Exception:
        return {"ok": False, "reason": "error"}


@app.post("/api/create-desktop-shortcut", response_class=JSONResponse)
def create_desktop_shortcut_endpoint():
    """デスクトップにPCCheckerのショートカットを作成する(任意操作)"""
    try:
        return create_desktop_shortcut()
    except Exception:
        return {"ok": False, "reason": "error"}


PREFERRED_PORT = 8000


def pick_port(preferred: int = PREFERRED_PORT) -> int:
    """希望ポートが空いていればそれを、使用中なら空きポートを返す"""
    for port in (preferred, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
        except OSError:
            continue
    raise OSError("利用可能なポートが見つかりませんでした")


def wait_and_open_browser(url: str, timeout_sec: float = 15.0, interval_sec: float = 0.3) -> bool:
    """サーバーがHTTP応答を返すのを待ってからブラウザを開く"""
    import time

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as res:
                if res.status == 200:
                    webbrowser.open(url)
                    return True
        except Exception:
            time.sleep(interval_sec)
    return False


def _setup_frozen_logging() -> None:
    """ウィンドウなしexeでは標準出力がないため、ログをファイルへ逃がす"""
    if is_frozen() and (sys.stdout is None or sys.stderr is None):
        log_file = open(data_dir() / "pcchecker.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file


def main() -> None:
    import uvicorn

    _setup_frozen_logging()
    port = pick_port()
    url = f"http://127.0.0.1:{port}"
    threading.Thread(target=wait_and_open_browser, args=(url,), daemon=True).start()
    print("PCChecker を起動中...")
    print(f"ブラウザが自動で開きます → {url}")
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
