"""rakuten_client のテスト(ネットワーク・実APIキー不要の純粋ロジックのみ)"""

import time

import pytest

import rakuten_client
from rakuten_client import (
    cache_get,
    is_new_item,
    is_valid_item,
    matches_model,
    normalize_keyword,
    select_best_item,
)


# ---------------------------------------------------------------------------
# normalize_keyword: 楽天APIの1文字トークン拒否への対策
# ---------------------------------------------------------------------------

class TestNormalizeKeyword:
    def test_single_char_token_is_merged(self):
        # 技術検証で判明: 「Ryzen 5 7600」は400エラー、「Ryzen5 7600」は成功
        assert normalize_keyword("AMD Ryzen 5 7600") == "AMD Ryzen5 7600"

    def test_x3d_model(self):
        assert normalize_keyword("AMD Ryzen 7 7800X3D") == "AMD Ryzen7 7800X3D"

    def test_parenthetical_is_removed(self):
        assert normalize_keyword("Crucial P3 500GB (NVMe Gen3)") == "Crucial P3 500GB"

    def test_fullwidth_parenthetical_capacity_is_kept(self):
        # 全角括弧でも容量表記は検索条件として残す
        assert normalize_keyword("RTX 4060（8GB）") == "RTX 4060 8GB"
        assert normalize_keyword("RTX 4060（OC版）") == "RTX 4060"

    def test_quantity_mark_is_converted(self):
        assert normalize_keyword("DDR4-3200 8GB×2 (16GB)") == "DDR4-3200 8GB 2枚 16GB"

    def test_total_capacity_in_parenthesis_is_kept(self):
        # 実機検証で混入を確認: 16GB×2 の推奨に合計16GB(8GB×2)の商品がマッチした
        assert normalize_keyword("DDR4-3600 16GB×2 (32GB)") == "DDR4-3600 16GB 2枚 32GB"

    def test_hyphenated_model_is_unchanged(self):
        assert normalize_keyword("Intel Core i5-13400F") == "Intel Core i5-13400F"

    def test_leading_single_char_is_kept(self):
        # 先頭の1文字トークンは連結先がないのでそのまま残す
        assert normalize_keyword("X 570") == "X 570"


# ---------------------------------------------------------------------------
# matches_model: 型番取り違え(P3 と P310 等)の防止
# ---------------------------------------------------------------------------

class TestMatchesModel:
    def test_exact_model_matches(self):
        assert matches_model("Crucial P3 500GB", "Crucial P3 500GB CT500P3SSD8JP")

    def test_successor_model_is_rejected(self):
        # 技術検証で混入を確認: P3 の検索結果に後継の P310 が出る
        assert not matches_model("Crucial P3 500GB", "Crucial 内蔵SSD 500GB P310 M.2")

    def test_different_gpu_is_rejected(self):
        # 技術検証で混入を確認: RTX 4060 の検索結果に RTX 3050 が出る
        assert not matches_model("GeForce RTX 4060", "MSI GeForce RTX 3050 VENTUS 2X 6G")

    def test_gpu_matches_case_insensitive(self):
        assert matches_model("GeForce RTX 4060", "msi geforce rtx 4060 ventus 2x black")

    def test_model_inside_longer_token_is_rejected(self):
        assert not matches_model("RX 7600", "Radeon RX 7600XT 16GB")

    def test_variant_suffix_in_item_is_rejected(self):
        # 実機検証で混入を確認: RTX 4060 の検索に RTX 4060 Ti 搭載機が出る
        assert not matches_model("NVIDIA RTX 4060", "GeForce RTX 4060 Ti搭載 16GB eGPU")
        assert not matches_model("RTX 4080", "GeForce RTX 4080 SUPER 16GB")

    def test_variant_suffix_in_keyword_must_exist_in_item(self):
        # 逆方向: XT 付きを探しているのに無印がヒットするのも防ぐ
        assert not matches_model("AMD RX 7600 XT", "Radeon RX 7600 8GB GDDR6")
        assert matches_model("AMD RX 7600 XT", "Radeon RX 7600 XT 16GB GDDR6")

    def test_keyword_with_suffix_matches_same_suffix(self):
        assert matches_model("RTX 4070 Ti SUPER", "GeForce RTX 4070 Ti SUPER 16GB")

    def test_trailing_letters_are_allowed(self):
        # 実機検証で取りこぼしを確認: AX210 の商品名は「AX210NGW」が主流
        assert matches_model("Intel Wi-Fi 6E AX210", "Intel Wi-Fi 6E AX210NGW 無線LANカード")

    def test_no_space_model_notation_matches(self):
        # 実機検証で取りこぼしを確認: 「RTX4060」のスペースなし表記が多い
        assert matches_model("NVIDIA RTX 4060", "玄人志向 NVIDIA RTX4060 搭載 グラフィックボード")
        assert not matches_model("NVIDIA RTX 4060", "GIGABYTE NVIDIA GeForce RTX4060Ti 搭載")

    def test_letter_digit_spacing_variations_match(self):
        # 正規化で「Ultra7」になるが商品名は「Ultra 7」表記が主流
        assert matches_model("Intel Core Ultra7 265K", "インテル Core Ultra 7 265K BOX")
        assert matches_model("AMD Ryzen AI9 HX 370", "AMD Ryzen AI 9 HX 370 搭載ミニPC")


# ---------------------------------------------------------------------------
# is_new_item / select_best_item: 中古品の除外と最良候補の選択
# ---------------------------------------------------------------------------

def _item(name: str, price: int, affiliate: str = "https://aff.example/x") -> dict:
    return {"itemName": name, "itemPrice": price,
            "affiliateUrl": affiliate, "itemUrl": "https://item.example/x",
            "shopName": "テストショップ"}


class TestSelectBestItem:
    def test_used_item_is_skipped(self):
        items = [
            _item("【中古】GeForce RTX 4060 8GB", 39800),
            _item("MSI GeForce RTX 4060 VENTUS 2X", 45980),
        ]
        best = select_best_item("GeForce RTX 4060", items)
        assert best is not None
        assert best["itemPrice"] == 45980

    def test_wrong_model_is_skipped(self):
        items = [
            _item("MSI GeForce RTX 3050 VENTUS 2X", 30000),
            _item("GIGABYTE GeForce RTX 4060 GAMING OC", 47000),
        ]
        best = select_best_item("GeForce RTX 4060", items)
        assert best is not None
        assert "4060" in best["itemName"]

    def test_no_match_returns_none(self):
        items = [_item("【中古】GeForce RTX 4060", 39800)]
        assert select_best_item("GeForce RTX 4060", items) is None

    def test_accessory_is_rejected(self):
        # 実機検証で混入を確認: モニター検索に保護フィルムが出る
        assert not is_valid_item(
            "ASUS VA24DQF",
            "【商品は保護フィルムのみ】 ASUS VA24DQF 用 マット 反射低減 液晶 保護 フィルム",
            4780, ref_price=18000)

    def test_too_cheap_item_is_rejected_by_ref_price(self):
        # 参考価格の40%未満は付属品・別物とみなす
        assert not is_valid_item("ASUS VA24DQF", "ASUS VA24DQF 関連商品", 1000, ref_price=18000)
        assert is_valid_item("ASUS VA24DQF", "ASUS VA24DQF 23.8インチ モニター", 17500, ref_price=18000)

    def test_ref_price_zero_means_no_floor(self):
        assert is_valid_item("ASUS VA24DQF", "ASUS VA24DQF モニター", 1000, ref_price=None)

    def test_sodimm_is_rejected_for_ram_search(self):
        # 実機検証で混入を確認: デスクトップ用RAM検索にノート用(260Pin SODIMM)が出る
        assert not is_valid_item(
            "DDR4-3200 8GB 2枚",
            "シリコンパワー ddr4 ノートDDR4-3200 (PC4-25600) 8GB×2枚 260Pin",
            18980, ref_price=5000)
        assert is_valid_item(
            "DDR4-3200 8GB 2枚",
            "CFD DDR4-3200 デスクトップ用 8GB 2枚組 288Pin DIMM",
            6000, ref_price=5000)

    def test_power_adapter_accessory_is_rejected(self):
        # 実機検証で混入を確認: CPU/SoC検索にミニPC用の代替ACアダプターが出る
        assert not is_valid_item(
            "AMD Ryzen AI9 HX 370",
            "【代替電源】GMKtec ミニpc対応ACアダプター AMD Ryzen AI 9 HX-370 モデル代用",
            4800, ref_price=None)

    def test_bundle_pc_is_rejected(self):
        # 実機検証で混入を確認: GPU検索にGPU搭載の完成品PCが出る
        assert not is_valid_item(
            "NVIDIA RTX 4060",
            "マウスコンピューター DAIV Z6 (Windows11 Pro/Core i7/RTX 4060)",
            291100, ref_price=45000)

    def test_too_expensive_item_is_rejected_by_ref_price(self):
        # 参考価格の6倍超は完成品PC等の抱き合わせとみなす
        assert not is_valid_item("NVIDIA RTX 4060", "RTX 4060 ワークステーション",
                                 291100, ref_price=45000)
        # NAND高騰による4倍程度の価格上昇は正規品としてあり得るので許容
        assert is_valid_item("Samsung 990 Pro 1TB", "Samsung SSD 990 PRO 1TB",
                             48465, ref_price=12000)

    def test_is_new_item(self):
        assert is_new_item("新品 GeForce RTX 4060")
        assert not is_new_item("【中古】GeForce RTX 4060")
        assert not is_new_item("GeForce RTX 4060 ジャンク品")


# ---------------------------------------------------------------------------
# cache_get: TTLの判定
# ---------------------------------------------------------------------------

class TestCacheGet:
    def test_fresh_entry_is_returned(self):
        now = time.time()
        cache = {"RTX 4060": {"fetched_at": now - 60, "result": {"price": 45980}}}
        entry = cache_get(cache, "RTX 4060", now=now)
        assert entry is not None
        assert entry["result"]["price"] == 45980

    def test_expired_entry_is_ignored(self):
        now = time.time()
        cache = {"RTX 4060": {"fetched_at": now - rakuten_client.CACHE_TTL_SEC - 1,
                              "result": {"price": 45980}}}
        assert cache_get(cache, "RTX 4060", now=now) is None

    def test_missing_entry_returns_none(self):
        assert cache_get({}, "RTX 4060") is None

    def test_negative_cache_entry_is_returned(self):
        # 「ヒットなし」(result=None) もキャッシュ対象。エントリ自体は返る
        now = time.time()
        cache = {"謎パーツ": {"fetched_at": now, "result": None}}
        entry = cache_get(cache, "謎パーツ", now=now)
        assert entry is not None
        assert entry["result"] is None
