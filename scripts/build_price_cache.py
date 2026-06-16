"""
中継サーバー用 日次バッチ: 楽天市場の実勢価格キャッシュを生成する

配布版のexeはユーザーPCから楽天API(IP許可制)を直接叩けないため、固定IPの
中継サーバー(VPS)でこのスクリプトをcron実行し、全アップグレード候補パーツ
およびBTO候補の価格・アフィリエイトリンクを1つのJSONにまとめて出力する。
出力JSONをCloudflare(Pages/R2)へ公開し、exe側の rakuten_client.py が
REMOTE_CACHE_URL 経由で参照する。

実行前提:
- このスクリプトを動かす環境に有効な .env(applicationId/accessKey/affiliateId)
  があり、その実行元IPが楽天APIのIP許可リストに登録されていること。
- 楽天APIキーはこの中継サーバーにのみ置く(配布物・配信物には含めない)。

Linux VPSでの実行に対応するため、pc_analyzer がトップレベルで import する
Windows専用モジュール(wmi/winreg)を、未インストールならスタブ化してから
import する。PROFILES/BTO_SUGGESTIONS は単なるdictリテラルで、import時に
これらのモジュールへ触れないため安全に列挙できる。

使い方:
    python scripts/build_price_cache.py [出力先パス]
    (省略時は dist_cache/price_cache.json)
"""
from __future__ import annotations

import json
import os
import re
import sys
import types
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# --- Windows専用モジュールのスタブ化(Linux VPS対応) -----------------------
for _name in ("wmi", "winreg", "psutil"):
    try:
        __import__(_name)
    except Exception:
        sys.modules[_name] = types.ModuleType(_name)

# プロジェクトルートを import パスに追加(scripts/ から1つ上)
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from pc_analyzer import PROFILES, BTO_SUGGESTIONS, BTO_SUGGESTIONS_LAPTOP  # noqa: E402
from rakuten_client import (  # noqa: E402
    is_configured, normalize_keyword, search_bto, search_part,
)

JST = timezone(timedelta(hours=9))
CACHE_TTL_HOURS = 24
REQUEST_TIMEOUT_SEC = 15

ALERT_WEBHOOK_ENV = "PCCHECKER_ALERT_WEBHOOK"
PRICE_MIN_HIT_RATIO_ENV = "PCCHECKER_PRICE_MIN_HIT_RATIO"
BTO_MIN_HITS_ENV = "PCCHECKER_BTO_MIN_HITS"
DEFAULT_PRICE_MIN_HIT_RATIO = 0.5
DEFAULT_BTO_MIN_HITS = 1


def parse_ref_price(price_text: str) -> int:
    """「約 ¥45,000〜」のような目安価格文字列から数値を取り出す

    app.js の parseRefPrice と同じ規則(数字以外を除去)で、クライアントが
    送る ref と一致させる。
    """
    digits = re.sub(r"[^\d]", "", str(price_text or ""))
    return int(digits) if digits else 0


def collect_price_targets() -> dict[str, int]:
    """全プロファイルの upgrade_options から (正規化キーワード -> ref価格) を集める

    同じパーツが複数プロファイルに現れる場合は最初の出現を採用する
    (ref は妥当性レンジの基準にのみ使うため差異は問題にならない)。
    """
    targets: dict[str, int] = {}
    for profile in PROFILES.values():
        for items in profile.get("upgrade_options", {}).values():
            for item in items:
                name = item.get("name", "")
                ref = parse_ref_price(item.get("price", ""))
                if ref <= 0:
                    continue  # 目安価格が数値でない項目はクライアントもスキップする
                key = normalize_keyword(name)
                if key and key not in targets:
                    targets[key] = ref
    return targets


def collect_bto_targets() -> dict[str, int]:
    """デスクトップ/ノート両方のBTO候補から (正規化キーワード -> ref価格) を集める"""
    targets: dict[str, int] = {}
    for table in (BTO_SUGGESTIONS, BTO_SUGGESTIONS_LAPTOP):
        for entry in table.values():
            key = normalize_keyword(entry.get("keyword", ""))
            ref = int(entry.get("ref_price", 0))
            if key and ref > 0 and key not in targets:
                targets[key] = ref
    return targets


def build_cache() -> dict:
    """全対象を楽天APIで取得し、配信用JSONの中身を組み立てる"""
    prices: dict[str, dict | None] = {}
    price_targets = collect_price_targets()
    for i, (keyword, ref) in enumerate(price_targets.items(), 1):
        print(f"[price {i}/{len(price_targets)}] {keyword} (ref={ref})", flush=True)
        # search_part は内部でキーワード正規化するが、結果キーは正規化済みに揃える
        prices[keyword] = search_part(keyword, ref_price=ref)

    bto: dict[str, list[dict]] = {}
    bto_targets = collect_bto_targets()
    for i, (keyword, ref) in enumerate(bto_targets.items(), 1):
        print(f"[bto {i}/{len(bto_targets)}] {keyword} (ref={ref})", flush=True)
        bto[keyword] = search_bto(keyword, ref_price=ref)

    return {
        "generated_at": datetime.now(JST).isoformat(timespec="seconds"),
        "ttl_hours": CACHE_TTL_HOURS,
        "prices": prices,
        "bto": bto,
    }


def _env_float(name: str, default: float) -> float:
    """環境変数から float を読む。壊れた値なら既定値へ戻す。"""
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    """環境変数から int を読む。壊れた値なら既定値へ戻す。"""
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def summarize_cache(cache: dict) -> dict:
    """生成済みキャッシュから健全性判定に使う件数を集計する"""
    prices = cache.get("prices", {})
    bto = cache.get("bto", {})
    generated_at = cache.get("generated_at")
    if not generated_at:
        generated_at = datetime.now(JST).isoformat(timespec="seconds")
    return {
        "generated_at": generated_at,
        "price_hits": sum(1 for v in prices.values() if v),
        "price_total": len(prices),
        "bto_hits": sum(1 for v in bto.values() if v),
        "bto_total": len(bto),
    }


def evaluate_health(cache: dict | None = None,
                    exception: Exception | None = None) -> dict:
    """収集結果が配信に使える状態か判定する"""
    if exception is not None:
        return {
            "healthy": False,
            "reasons": [f"収集中に例外が発生: {type(exception).__name__}: {exception}"],
            "generated_at": datetime.now(JST).isoformat(timespec="seconds"),
            "price_hits": 0,
            "price_total": 0,
            "bto_hits": 0,
            "bto_total": 0,
        }

    if cache is None:
        raise ValueError("cache または exception のどちらかが必要です")

    summary = summarize_cache(cache)
    reasons: list[str] = []
    price_min_ratio = _env_float(PRICE_MIN_HIT_RATIO_ENV, DEFAULT_PRICE_MIN_HIT_RATIO)
    bto_min_hits = _env_int(BTO_MIN_HITS_ENV, DEFAULT_BTO_MIN_HITS)

    price_hits = summary["price_hits"]
    price_total = summary["price_total"]
    if price_total > 0 and price_hits / price_total < price_min_ratio:
        reasons.append(
            f"価格ヒット数がしきい値未満: {price_hits}/{price_total} "
            f"({price_min_ratio:.0%} 未満)"
        )
    if summary["bto_hits"] < bto_min_hits:
        reasons.append(
            f"BTOヒット数がしきい値未満: {summary['bto_hits']}件 "
            f"(最低 {bto_min_hits}件)"
        )

    return {"healthy": not reasons, "reasons": reasons, **summary}


def build_alert_message(health: dict) -> str:
    """Discord互換Webhookへ送る本文を組み立てる"""
    reasons = " / ".join(health.get("reasons") or ["理由不明"])
    return (
        "[PCChecker] 価格キャッシュ更新の異常を検知しました\n"
        f"理由: {reasons}\n"
        f"価格ヒット: {health.get('price_hits', 0)}/{health.get('price_total', 0)}\n"
        f"BTOヒット: {health.get('bto_hits', 0)}/{health.get('bto_total', 0)}\n"
        f"generated_at: {health.get('generated_at', '')}\n"
        "対処ヒント: 楽天IP許可リストの再確認(eo光IP変動の可能性)を行ってください。"
    )


def _http_post_json(url: str, payload: dict) -> int:
    """JSONをPOSTし、HTTPステータスコードを返す。テストで差し替え可能。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "PCChecker"},
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as res:
        return res.status


def notify_unhealthy(health: dict) -> dict:
    """異常時のWebhook通知をベストエフォートで送る"""
    url = os.environ.get(ALERT_WEBHOOK_ENV, "").strip()
    if not url:
        print(f"WARNING: {ALERT_WEBHOOK_ENV} が未設定のため異常通知をスキップしました。",
              file=sys.stderr)
        return {"ok": False, "reason": "not_configured"}

    payload = {"content": build_alert_message(health)}
    try:
        status = _http_post_json(url, payload)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        print(f"WARNING: 異常通知の送信に失敗しました: {exc}", file=sys.stderr)
        return {"ok": False, "reason": "network_error"}

    if 200 <= status < 300:
        return {"ok": True}
    print(f"WARNING: 異常通知の送信先がエラーを返しました: HTTP {status}", file=sys.stderr)
    return {"ok": False, "reason": "server_error"}


def main(argv: list[str]) -> int:
    if not is_configured():
        print("ERROR: 有効な .env(楽天APIキー)が見つかりません。"
              "このバッチはIP許可済みの中継サーバー上で実行してください。",
              file=sys.stderr)
        return 1

    out_path = Path(argv[1]) if len(argv) > 1 else _ROOT / "dist_cache" / "price_cache.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        cache = build_cache()
    except Exception as exc:
        health = evaluate_health(exception=exc)
        print(f"ERROR: 価格キャッシュ生成に失敗しました: {exc}", file=sys.stderr)
        notify_unhealthy(health)
        return 1

    out_path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")

    health = evaluate_health(cache)
    hits = health["price_hits"]
    bto_hits = health["bto_hits"]
    print(f"\n生成完了: {out_path}")
    print(f"  価格: {hits}/{len(cache['prices'])} 件ヒット")
    print(f"  BTO : {bto_hits}/{len(cache['bto'])} キーワードでヒット")
    if not health["healthy"]:
        print("WARNING: 価格キャッシュ生成結果が異常です: "
              + " / ".join(health["reasons"]), file=sys.stderr)
        notify_unhealthy(health)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
