"""
2026年世代パーツ表更新のための流通検証スクリプト

upgrade_options の差し替え候補を楽天APIで検索し、
「新品が買える・妥当な価格が取れる」ことを確認する。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rakuten_client import search_part

# (パーツ名, 参考価格) — 参考価格は2026年6月の市場調査に基づく目安
CANDIDATES = [
    # --- GPU (現行世代) ---
    ("NVIDIA RTX 5060", 50000),
    ("NVIDIA RTX 5060 Ti 16GB", 90000),
    ("NVIDIA RTX 5070", 100000),
    ("NVIDIA RTX 5070 Ti", 150000),
    ("AMD RX 9060 XT", 60000),
    ("AMD RX 9070 XT", 100000),
    ("Intel Arc B580", 45000),
    # --- GPU (旧世代の残存確認) ---
    ("AMD RX 6600", 35000),
    ("NVIDIA RTX 3050", 30000),
    # --- CPU ---
    ("Intel Core i3-14100", 20000),
    ("Intel Core i5-14400F", 28000),
    ("AMD Ryzen 5 5600GT", 20000),
    ("AMD Ryzen 5 7600", 30000),
    ("AMD Ryzen 7 7800X3D", 70000),
    ("AMD Ryzen 7 9800X3D", 90000),
    ("Intel Core Ultra 7 265K", 60000),
    ("AMD Ryzen 9 9950X", 110000),
    # --- ストレージ (価格更新) ---
    ("Crucial BX500 500GB", 8000),
    ("Crucial P3 Plus 1TB", 15000),
    ("Samsung 990 Pro 1TB", 45000),
    ("WD Black SN850X 1TB", 40000),
    ("Samsung 990 Pro 2TB", 80000),
    # --- ディスプレイ ---
    ("ASUS VA24DQF", 18000),
    ("Dell G2425H", 20000),
    ("KOORUI 24E3", 15000),
    # --- ネットワーク (Wi-Fi 7) ---
    ("Intel BE200 Wi-Fi 7", 6000),
    ("TP-Link Archer TBE550E Wi-Fi 7", 12000),
    # --- AIアクセラレータ ---
    ("Hailo-8 M.2", 30000),
    ("Google Coral USB Accelerator", 17000),
]


def main() -> None:
    ok, ng = 0, 0
    for name, ref in CANDIDATES:
        r = search_part(name, ref_price=ref)
        if r:
            ok += 1
            print(f"OK  {name}  ¥{r['price']:,} | {r['item_name'][:55]}")
        else:
            ng += 1
            print(f"NG  {name}  ヒットなし")
    print(f"\n結果: {ok} OK / {ng} NG (全{len(CANDIDATES)}件)")


if __name__ == "__main__":
    main()
