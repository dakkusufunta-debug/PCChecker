"""
楽天市場商品検索APIクライアント

アップグレード候補パーツの実勢価格とアフィリエイトリンクを取得する。

設計上の注意(2026-06-12時点の技術検証結果に基づく):
- 2026年2月のインフラ刷新後の新エンドポイントを使用(旧 app.rakuten.co.jp は停止済み)
- 認証は applicationId + accessKey の2つをクエリパラメータで渡す
- 楽天APIは1文字だけの検索語を受け付けない(「Ryzen 5 7600」→ 400エラー)ため、
  検索前にキーワードを正規化する
- 最安値ソートは中古品・型番違いが混入するため、NGキーワードと型番フィルタで除外する
- レート制限(1秒1リクエスト)対策として呼び出し間隔を強制し、結果はファイルにキャッシュする
"""

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"

BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"
CACHE_PATH = BASE_DIR / "price_cache.json"

CACHE_TTL_SEC = 12 * 60 * 60   # 価格キャッシュの有効期間: 12時間
MIN_INTERVAL_SEC = 1.1         # API呼び出しの最小間隔(レート制限対策)
REQUEST_TIMEOUT_SEC = 15

# 新品に絞るための除外ワード(検索クエリ用と商品名の事後フィルタ用)
NG_KEYWORD = "中古 ジャンク 訳あり"
USED_MARKERS = ("中古", "ジャンク", "訳あり", "アウトレット", "リファービッシュ",
                "未使用", "開封品")

_lock = threading.Lock()
_last_call_at = 0.0


# ---------------------------------------------------------------------------
# 認証情報
# ---------------------------------------------------------------------------

def load_credentials() -> dict[str, str]:
    """プロジェクト直下の .env から認証情報を読み込む(依存ライブラリなし)"""
    values: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip()
    return values


def is_configured() -> bool:
    """APIを呼び出すための認証情報が揃っているか"""
    creds = load_credentials()
    app_id = creds.get("RAKUTEN_APPLICATION_ID", "")
    access_key = creds.get("RAKUTEN_ACCESS_KEY", "")
    return bool(app_id and access_key
                and "ここに" not in app_id and "ここに" not in access_key)


# ---------------------------------------------------------------------------
# キーワード正規化
# ---------------------------------------------------------------------------

def normalize_keyword(name: str) -> str:
    """upgrade_options のパーツ名を楽天APIで検索可能な形に正規化する

    - 括弧書きの補足を除去。ただし合計容量("(32GB)" 等)は、容量違いの
      商品(16GB×2 の推奨に 8GB×2 がマッチする等)を弾くために残す
    - 「×2」のような個数表記を「2枚」に変換
    - 楽天APIが拒否する1文字トークンを直前のトークンに連結("Ryzen 5" → "Ryzen5")
    """
    def _paren(m: re.Match) -> str:
        inner = m.group(1).strip()
        return f" {inner} " if re.fullmatch(r"\d+(GB|TB)", inner) else " "

    s = re.sub(r"[（(]([^）)]*)[）)]", _paren, name)
    s = re.sub(r"×(\d+)", r" \1枚", s)

    merged: list[str] = []
    for token in s.split():
        if len(token) == 1 and merged:
            merged[-1] += token
        else:
            merged.append(token)
    return " ".join(merged)


# ---------------------------------------------------------------------------
# 商品の妥当性フィルタ
# ---------------------------------------------------------------------------

def _model_tokens(keyword: str) -> list[str]:
    """キーワードから型番らしきトークン(数字を含む語)を抽出する"""
    return [t for t in keyword.split() if re.search(r"\d", t)]


def _token_pattern(token: str) -> str:
    """型番トークンの照合用正規表現を組み立てる

    - 英字と数字の境目に空白の表記ゆれを許す("Ultra7" ↔ "Ultra 7")
    - 直後に数字が続く場合は別型番とみなす("P3" が "P310" にマッチしない)
    - 直後の英字は許す("AX210" が "AX210NGW" にマッチする。
      "4060Ti" のような派生グレードは matches_model の派生サフィックス
      チェック側で除外される)
    - 数字始まりのトークンは直前の英字を許す("4060" が "RTX4060" にマッチする)
    """
    parts = re.findall(r"\d+|[A-Za-z]+|[^A-Za-z0-9]+", token)
    body = r"\s*".join(re.escape(p) for p in parts)
    prefix = r"(?<!\d)" if token[0].isdigit() else r"(?<![A-Za-z0-9])"
    return prefix + body + r"(?!\d)"


# GPU等の派生グレードを表すサフィックス。キーワード側に無いのに商品名側に
# 付いている場合は別物(例: RTX 4060 と RTX 4060 Ti)とみなす
VARIANT_SUFFIXES = ("Ti", "SUPER", "XT", "XTX", "GRE", "F", "X", "X3D", "KF")


def matches_model(keyword: str, item_name: str) -> bool:
    """商品名がキーワード中の型番トークンをすべて含むか判定する

    - 「P3」が「P310」にマッチしないよう、トークンの前後に英数字が
      続かないことを要求する(後継・類似型番の混入対策)
    - 「RTX 4060」が「RTX 4060 Ti」にマッチしないよう、キーワードに無い
      派生サフィックスが型番直後に付く商品は除外する
    """
    keyword_tokens_lower = {t.lower() for t in keyword.split()}
    for token in _model_tokens(keyword):
        pattern = _token_pattern(token)
        if not re.search(pattern, item_name, flags=re.IGNORECASE):
            return False
        # 型番直後の派生サフィックスをチェック
        for suffix in VARIANT_SUFFIXES:
            if suffix.lower() in keyword_tokens_lower:
                continue
            # 型番トークンと同じ表記ゆれ("RTX4060TI" 等)を許して検出する
            variant_pattern = (_token_pattern(token)
                               + r"\s*" + re.escape(suffix) + r"(?![A-Za-z0-9])")
            if re.search(variant_pattern, item_name, flags=re.IGNORECASE):
                return False
    # 逆方向: キーワード側にある派生サフィックスが商品名に無い場合も別物
    for suffix in VARIANT_SUFFIXES:
        if suffix.lower() in keyword_tokens_lower:
            suffix_pattern = r"(?<![A-Za-z0-9])" + re.escape(suffix) + r"(?![A-Za-z0-9])"
            if not re.search(suffix_pattern, item_name, flags=re.IGNORECASE):
                return False
    return True


def is_new_item(item_name: str) -> bool:
    """商品名から新品とみなせるか判定する(NGキーワードすり抜けの事後フィルタ)"""
    return not any(marker in item_name for marker in USED_MARKERS)


# 本体ではなく付属品・周辺品であることを示すワード
ACCESSORY_MARKERS = ("保護フィルム", "フィルムのみ", "ブラケット", "ドライバーのみ",
                     "ACアダプター", "ACアダプタ", "代替電源", "代用", "互換バッテリー",
                     # 「ケース」はSSD外付けケース・Pi用ケース等の混入対策。
                     # 「スタンド」は正規モニターの「スタンド付き」と衝突するため入れない
                     "ブルーライトカット", "ケース", "壁掛け金具",
                     "フィルター", "覗き見防止")

# パーツ単体ではなく完成品PC・一体型製品であることを示すワード
BUNDLE_MARKERS = ("Windows11", "Windows 11", "ノートパソコン", "ノートPC",
                  "デスクトップパソコン", "ミニPC", "一体型", "ゲーミングPC")

# デスクトップ用RAM検索に混入するノートPC用RAMの目印
SODIMM_MARKERS = ("SODIMM", "S.O.DIMM", "SO-DIMM", "260Pin", "260P", "ノート")

# 参考価格に対してこの比率を下回る商品は付属品・別物とみなす
MIN_PRICE_RATIO = 0.4

# 参考価格に対してこの比率を超える商品は完成品PC等の抱き合わせとみなす
# (2026年のNAND高騰でSSDは目安価格の4倍超があり得るため、緩めの6倍とする)
MAX_PRICE_RATIO = 6.0


def is_valid_item(keyword: str, item_name: str, price: int,
                  ref_price: int | None = None) -> bool:
    """商品が「探しているパーツ本体の新品」として妥当か総合判定する"""
    if not is_new_item(item_name):
        return False
    if not matches_model(keyword, item_name):
        return False
    if any(marker in item_name for marker in ACCESSORY_MARKERS):
        return False
    if any(marker in item_name for marker in BUNDLE_MARKERS):
        return False
    # デスクトップ用メモリの検索ではノート用(SODIMM)を除外
    if "DDR" in keyword.upper():
        upper = item_name.upper()
        if any(m.upper() in upper for m in SODIMM_MARKERS):
            return False
    # 参考価格よりはるかに安い商品は保護フィルム等の付属品の可能性が高い
    if ref_price and ref_price > 0 and price < ref_price * MIN_PRICE_RATIO:
        return False
    # 参考価格よりはるかに高い商品は完成品PC等への搭載品の可能性が高い
    if ref_price and ref_price > 0 and price > ref_price * MAX_PRICE_RATIO:
        return False
    return True


def select_best_item(keyword: str, items: list[dict],
                     ref_price: int | None = None) -> dict | None:
    """検索結果(安い順)から、本体・新品・型番一致する最初の商品を返す"""
    for item in items:
        name = item.get("itemName", "")
        price = int(item.get("itemPrice", 0))
        if is_valid_item(keyword, name, price, ref_price):
            return item
    return None


# ---------------------------------------------------------------------------
# キャッシュ
# ---------------------------------------------------------------------------

def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    try:
        CACHE_PATH.write_text(
            json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def cache_get(cache: dict, keyword: str, now: float | None = None) -> dict | None:
    """有効期限内のキャッシュエントリを返す(なければ None)"""
    entry = cache.get(keyword)
    if not entry:
        return None
    ts = entry.get("fetched_at", 0)
    if (now if now is not None else time.time()) - ts > CACHE_TTL_SEC:
        return None
    return entry


# ---------------------------------------------------------------------------
# API呼び出し
# ---------------------------------------------------------------------------

def _call_api(keyword: str, sort: str = "+itemPrice") -> list[dict]:
    """商品検索APIを1回呼び、商品リストを返す"""
    global _last_call_at
    creds = load_credentials()
    params = {
        "applicationId": creds.get("RAKUTEN_APPLICATION_ID", ""),
        "accessKey": creds.get("RAKUTEN_ACCESS_KEY", ""),
        "affiliateId": creds.get("RAKUTEN_AFFILIATE_ID", ""),
        "keyword": keyword,
        "NGKeyword": NG_KEYWORD,
        # 安い順の上位は付属品・中古が多く、フィルタ後に本体が残るよう多めに取る
        "hits": 30,
        "sort": sort,
        "availability": 1,
        "formatVersion": 2,
    }
    # レート制限: 直前の呼び出しから最小間隔を空ける
    wait = _last_call_at + MIN_INTERVAL_SEC - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_call_at = time.time()

    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SEC) as res:
        data = json.loads(res.read().decode("utf-8"))
    return data.get("Items", [])


def search_part(part_name: str, ref_price: int | None = None) -> dict | None:
    """パーツ名から実勢価格情報を取得する(キャッシュ・レート制限つき)

    ref_price にはハードコードされた目安価格を渡す。極端に安い付属品
    (保護フィルム等)を弾くための下限フィルタとして使う。
    戻り値: {"price": int, "item_name": str, "url": str, "shop": str} または None
    """
    keyword = normalize_keyword(part_name)

    with _lock:
        cache = _load_cache()
        entry = cache_get(cache, keyword)
        if entry is not None:
            return entry.get("result")

        try:
            items = _call_api(keyword)
            best = select_best_item(keyword, items, ref_price)
            if best is None:
                # 安い順で本体が見つからない場合は関連度順で再検索し、
                # 妥当な商品の中から最安値を選ぶ
                items = _call_api(keyword, sort="standard")
                valid = [i for i in items
                         if is_valid_item(keyword, i.get("itemName", ""),
                                          int(i.get("itemPrice", 0)), ref_price)]
                best = min(valid, key=lambda i: int(i.get("itemPrice", 0))) \
                    if valid else None
        except (urllib.error.URLError, urllib.error.HTTPError, OSError,
                json.JSONDecodeError):
            # 通信失敗はキャッシュせず None(UI側はハードコード価格で表示継続)
            return None
        result = None
        if best is not None:
            result = {
                "price": int(best.get("itemPrice", 0)),
                "item_name": best.get("itemName", ""),
                # affiliateUrl が空の場合は通常の商品URLにフォールバック
                "url": best.get("affiliateUrl") or best.get("itemUrl", ""),
                "shop": best.get("shopName", ""),
            }

        # ヒットなし(None)も記録して同じ外れキーワードの再検索を防ぐ
        cache[keyword] = {"fetched_at": time.time(), "result": result}
        _save_cache(cache)
        return result


# ---------------------------------------------------------------------------
# BTO PC検索(買い替え提案用)
# ---------------------------------------------------------------------------

# BTO検索の価格レンジ: 参考価格の0.5〜2.5倍を妥当な完成品とみなす
BTO_MIN_RATIO = 0.5
BTO_MAX_RATIO = 2.5
BTO_MAX_ITEMS = 3


def is_valid_bto_item(keyword: str, item_name: str, price: int,
                      ref_price: int) -> bool:
    """買い替え候補の完成品PCとして妥当か判定する

    パーツ検索と違い完成品PCは除外しない。新品であること・キーワードの
    型番(搭載GPU等)を含むこと・価格帯が妥当であることのみ要求する。
    """
    if not is_new_item(item_name):
        return False
    if any(marker in item_name for marker in ACCESSORY_MARKERS):
        return False
    # ノートPCは別カテゴリのため除外(デスクトップの買い替え提案)
    if "ノート" in item_name:
        return False
    if not matches_model(keyword, item_name):
        return False
    if not (ref_price * BTO_MIN_RATIO <= price <= ref_price * BTO_MAX_RATIO):
        return False
    return True


def search_bto(keyword: str, ref_price: int) -> list[dict]:
    """買い替え候補のBTO PCを最大3件返す(安い順、キャッシュつき)"""
    norm = normalize_keyword(keyword)
    cache_key = f"bto:{norm}"

    with _lock:
        cache = _load_cache()
        entry = cache_get(cache, cache_key)
        if entry is not None:
            return entry.get("result") or []

        try:
            items = _call_api(norm)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError,
                json.JSONDecodeError):
            return []

        results: list[dict] = []
        seen_shops: set[str] = set()
        for item in items:
            name = item.get("itemName", "")
            price = int(item.get("itemPrice", 0))
            shop = item.get("shopName", "")
            if not is_valid_bto_item(norm, name, price, ref_price):
                continue
            # 同一ショップの色違い・構成違いの重複を避ける
            if shop in seen_shops:
                continue
            seen_shops.add(shop)
            results.append({
                "price": price,
                "item_name": name,
                "url": item.get("affiliateUrl") or item.get("itemUrl", ""),
                "shop": shop,
            })
            if len(results) >= BTO_MAX_ITEMS:
                break

        cache[cache_key] = {"fetched_at": time.time(), "result": results}
        _save_cache(cache)
        return results
