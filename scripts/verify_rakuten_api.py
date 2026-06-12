"""
楽天市場商品検索APIの技術検証スクリプト

pc_analyzer.py の upgrade_options に登場する代表的なパーツ名で検索し、
価格・商品名・アフィリエイトURLがどの程度正確に取れるかを確認する。

使い方:
    1. .env.example を .env にコピーして アプリID / アフィリエイトID を記入
    2. python scripts/verify_rakuten_api.py
"""

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

# 2026年2月のインフラ刷新後の新エンドポイント(旧 app.rakuten.co.jp は2026年5月停止)
API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"

# upgrade_options から抜粋した代表パーツ(カテゴリの偏りがないように選定)
TEST_QUERIES = [
    "Crucial BX500 480GB",
    "Crucial P3 500GB NVMe",
    "Samsung 990 Pro 1TB",
    "DDR4-3200 8GB 2枚",
    "DDR5-4800 16GB 2枚",
    "GeForce RTX 4060",
    "GeForce RTX 4070 Ti SUPER",
    "Radeon RX 7600",
    "Core i5-13400F",
    "Ryzen 5 7600",
    "Ryzen 7 7800X3D",
    "ASUS PRIME B760M-A",
    "Intel Wi-Fi 6E AX210",
    "TP-Link UE300",
]


def load_env() -> dict[str, str]:
    """プロジェクト直下の .env を読み込む(依存ライブラリなしの簡易実装)"""
    env_path = Path(__file__).parent.parent / ".env"
    values: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip()
    # 環境変数があれば優先
    for key in ("RAKUTEN_APPLICATION_ID", "RAKUTEN_AFFILIATE_ID", "RAKUTEN_ACCESS_KEY"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def search_item(app_id: str, access_key: str, affiliate_id: str, keyword: str) -> dict:
    """商品検索APIを1回呼び、上位3件を返す"""
    params = {
        "applicationId": app_id,
        "accessKey": access_key,
        "affiliateId": affiliate_id,
        "keyword": keyword,
        "hits": 3,
        "sort": "+itemPrice",      # 安い順(最安値の把握が目的のため)
        "availability": 1,          # 販売可能な商品のみ
        "formatVersion": 2,
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=15) as res:
        return json.loads(res.read().decode("utf-8"))


def main() -> None:
    env = load_env()
    app_id = env.get("RAKUTEN_APPLICATION_ID", "")
    affiliate_id = env.get("RAKUTEN_AFFILIATE_ID", "")
    access_key = env.get("RAKUTEN_ACCESS_KEY", "")
    if not app_id or app_id == "your_application_id_here":
        print("エラー: .env に RAKUTEN_APPLICATION_ID を設定してください。")
        return
    if not access_key or "貼り付け" in access_key:
        print("エラー: .env に RAKUTEN_ACCESS_KEY (アクセスキー) を設定してください。")
        return

    print(f"検証開始: {len(TEST_QUERIES)} 件のパーツ名で検索します\n")
    ok, ng = 0, 0
    for keyword in TEST_QUERIES:
        try:
            data = search_item(app_id, access_key, affiliate_id, keyword)
            items = data.get("Items", [])
            print(f"■ {keyword}")
            if not items:
                ng += 1
                print("  → ヒットなし\n")
            else:
                ok += 1
                for item in items:
                    name = item["itemName"][:60]
                    price = item["itemPrice"]
                    has_aff = "あり" if item.get("affiliateUrl") else "なし"
                    print(f"  ¥{price:,}  {name}...  [アフィリエイトURL: {has_aff}]")
                print()
        except Exception as e:
            ng += 1
            print(f"■ {keyword}\n  → エラー: {e}\n")
        time.sleep(1.2)  # レート制限対策(1秒1リクエスト+余裕)

    print(f"結果: ヒット {ok} 件 / ヒットなし・エラー {ng} 件 (全 {len(TEST_QUERIES)} 件)")


if __name__ == "__main__":
    main()
