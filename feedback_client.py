"""
ユーザーフィードバック送信クライアント

リリース後の不具合報告・要望を集約するため、アプリ内フォームから送られた
フィードバックを外部のCloudflare Workerへ転送する。

設計上の注意:
- 送信先(sink)は環境変数 PCCUSTOMSUPPORT_FEEDBACK_URL で上書き可能(検証・移行用)。
- 診断データ(スペック・スコア)の添付はユーザーのオプトイン。添付対象は
  ハードウェア構成と診断スコアのみで、氏名・PC名などの個人情報は含まない
  (添付内容は app.js 側で要約を組み立て、UIに明示する)。
- 巨大なペイロードや空コメントはここで弾く。通信失敗時はUIに理由を返す。
"""
import json
import platform
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

import os

from app_paths import APP_VERSION

# 送信先 Cloudflare Worker。デプロイ後に本番URLへ差し替える
# (検証時は環境変数 PCCUSTOMSUPPORT_FEEDBACK_URL で上書き可能)。
FEEDBACK_URL = os.environ.get(
    "PCCUSTOMSUPPORT_FEEDBACK_URL",
    "https://pccustomsupport-feedback.example.workers.dev",
)

REQUEST_TIMEOUT_SEC = 15
MAX_COMMENT_LEN = 2000           # コメント本文の上限文字数
MAX_DIAGNOSTICS_BYTES = 64 * 1024  # 添付診断データのJSONサイズ上限
ALLOWED_CATEGORIES = ("bug", "request", "other")

JST = timezone(timedelta(hours=9))


def is_feedback_configured() -> bool:
    """フィードバック送信先が設定されているか"""
    return bool(FEEDBACK_URL)


def _http_post_json(url: str, payload: dict) -> int:
    """JSONをPOSTし、HTTPステータスコードを返す。テストで差し替え可能。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "PCCustomSupport"},
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as res:
        return res.status


def build_payload(category: str, comment: str,
                  diagnostics: dict | None = None) -> dict:
    """送信ペイロードを組み立てる(サーバー側でバージョン等を付与する)"""
    payload: dict = {
        "category": category,
        "comment": comment,
        "app_version": APP_VERSION,
        "platform": platform.platform(),
        "submitted_at": datetime.now(JST).isoformat(timespec="seconds"),
    }
    if diagnostics is not None:
        payload["diagnostics"] = diagnostics
    return payload


def submit_feedback(category: str, comment: str,
                    diagnostics: dict | None = None) -> dict:
    """フィードバックを検証して送信先へ転送する

    戻り値: {"ok": True} または {"ok": False, "reason": <理由>}
    """
    if not is_feedback_configured():
        return {"ok": False, "reason": "not_configured"}

    category = (category or "").strip()
    if category not in ALLOWED_CATEGORIES:
        return {"ok": False, "reason": "bad_category"}

    comment = (comment or "").strip()
    if not comment:
        return {"ok": False, "reason": "empty_comment"}
    if len(comment) > MAX_COMMENT_LEN:
        comment = comment[:MAX_COMMENT_LEN]

    # 添付診断データが上限を超える場合は付けずに送る(コメント本文は送る)
    if diagnostics is not None:
        try:
            size = len(json.dumps(diagnostics, ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError):
            diagnostics = None
        else:
            if size > MAX_DIAGNOSTICS_BYTES:
                diagnostics = None

    payload = build_payload(category, comment, diagnostics)
    try:
        status = _http_post_json(FEEDBACK_URL, payload)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return {"ok": False, "reason": "network_error"}

    if 200 <= status < 300:
        return {"ok": True}
    return {"ok": False, "reason": "server_error"}
