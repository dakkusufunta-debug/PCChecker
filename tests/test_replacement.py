"""買い替えvsアップグレード判定と BTO 検索フィルタのテスト"""

from pc_analyzer import ComponentScore, judge_replacement
from rakuten_client import is_valid_bto_item


def _score(name: str, status: str) -> ComponentScore:
    return ComponentScore(name=name, current_value="", midrange_standard="",
                          status=status, score=50 if status == "below" else 80)


class TestJudgeReplacement:
    def test_all_meets_is_upgrade(self):
        cores = [_score("CPU", "meets"), _score("RAM", "exceeds"),
                 _score("GPU", "meets"), _score("ストレージ", "exceeds")]
        rep = judge_replacement("mid", cores, _score("マザーボード", "meets"))
        assert rep["verdict"] == "upgrade"
        assert rep["bto"] is not None  # キーワード情報自体は常に返す

    def test_single_below_with_modern_platform_is_upgrade(self):
        cores = [_score("CPU", "meets"), _score("RAM", "meets"),
                 _score("GPU", "below"), _score("ストレージ", "meets")]
        rep = judge_replacement("mid", cores, _score("マザーボード", "meets"))
        assert rep["verdict"] == "upgrade"

    def test_old_platform_with_one_below_is_consider(self):
        cores = [_score("CPU", "meets"), _score("RAM", "meets"),
                 _score("GPU", "below"), _score("ストレージ", "meets")]
        rep = judge_replacement("mid", cores, _score("マザーボード", "below"))
        assert rep["verdict"] == "consider"

    def test_old_platform_with_cpu_and_others_below_is_replace(self):
        cores = [_score("CPU", "below"), _score("RAM", "below"),
                 _score("GPU", "meets"), _score("ストレージ", "meets")]
        rep = judge_replacement("high", cores, _score("マザーボード", "below"))
        assert rep["verdict"] == "replace"
        assert rep["bto"]["ref_price"] > 0

    def test_old_platform_with_three_below_is_replace(self):
        cores = [_score("CPU", "meets"), _score("RAM", "below"),
                 _score("GPU", "below"), _score("ストレージ", "below")]
        rep = judge_replacement("mid", cores, _score("マザーボード", "below"))
        assert rep["verdict"] == "replace"

    def test_many_below_without_old_platform_is_consider(self):
        cores = [_score("CPU", "below"), _score("RAM", "below"),
                 _score("GPU", "below"), _score("ストレージ", "meets")]
        rep = judge_replacement("mid", cores, _score("マザーボード", "meets"))
        assert rep["verdict"] == "consider"

    def test_reasons_mention_below_components(self):
        cores = [_score("CPU", "below"), _score("RAM", "below"),
                 _score("GPU", "below"), _score("ストレージ", "meets")]
        rep = judge_replacement("mid", cores, _score("マザーボード", "below"))
        assert any("CPU" in r for r in rep["reasons"])


class TestIsValidBtoItem:
    KW = "ゲーミングPC RTX 5060 搭載 新品"

    def test_valid_gaming_pc_is_accepted(self):
        assert is_valid_bto_item(
            self.KW, "ゲーミングPC 新品 RTX5060 搭載 Ryzen 7 メモリ32GB", 180000, 200000)

    def test_notebook_is_rejected(self):
        assert not is_valid_bto_item(
            self.KW, "ゲーミングノートPC RTX 5060 搭載 16インチ", 180000, 200000)

    def test_used_pc_is_rejected(self):
        assert not is_valid_bto_item(
            self.KW, "【中古】ゲーミングPC RTX 5060 搭載", 120000, 200000)

    def test_wrong_gpu_is_rejected(self):
        assert not is_valid_bto_item(
            self.KW, "ゲーミングPC RTX 5070 搭載 ハイエンド", 250000, 200000)

    def test_out_of_price_range_is_rejected(self):
        assert not is_valid_bto_item(self.KW, "ゲーミングPC RTX 5060 搭載", 80000, 200000)
        assert not is_valid_bto_item(self.KW, "ゲーミングPC RTX 5060 搭載", 600000, 200000)

    KW_NOTE = "ゲーミングノートPC RTX 5060 新品"

    def test_laptop_keyword_accepts_laptop(self):
        # ノートPC対応: キーワードに「ノート」を含む場合はノートPCを受け入れる
        assert is_valid_bto_item(
            self.KW_NOTE, "ゲーミングノートPC 新品 RTX5060 搭載 16インチ", 180000, 200000)

    def test_laptop_keyword_rejects_desktop(self):
        assert not is_valid_bto_item(
            self.KW_NOTE, "ゲーミングPC デスクトップ 新品 RTX5060 搭載", 180000, 200000)
