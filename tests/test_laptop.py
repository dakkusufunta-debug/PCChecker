"""ノートPC対応(筐体判定・提案出し分け・チップセット代替推定)のテスト"""

from pc_analyzer import (
    PROFILES,
    ComponentScore,
    PCSpecs,
    _apply_laptop_constraints,
    _estimate_platform_score_from_cpu,
    analyze_motherboard,
    analyze_ram,
    judge_replacement,
)


def _score(name: str, status: str, recommendations=None, upgrade_options=None) -> ComponentScore:
    return ComponentScore(name=name, current_value="", midrange_standard="",
                          status=status, score=50 if status == "below" else 80,
                          recommendations=recommendations or [],
                          upgrade_options=upgrade_options or [])


# ---------------------------------------------------------------------------
# CPU世代からのプラットフォーム代替推定
# ---------------------------------------------------------------------------

class TestEstimatePlatformScore:
    def test_intel_14th_gen(self):
        assert _estimate_platform_score_from_cpu("Intel Core i5-14400F") == 85

    def test_intel_12th_gen(self):
        assert _estimate_platform_score_from_cpu("12th Gen Intel(R) Core(TM) i7-12700") == 75

    def test_intel_9th_gen(self):
        assert _estimate_platform_score_from_cpu("Intel(R) Core(TM) i9-9900K CPU @ 3.60GHz") == 33

    def test_intel_7th_gen_is_lowest(self):
        assert _estimate_platform_score_from_cpu("Intel Core i5-7400") == 20

    def test_core_ultra(self):
        assert _estimate_platform_score_from_cpu("Intel Core Ultra 7 265K") == 90

    def test_ryzen_9000(self):
        assert _estimate_platform_score_from_cpu("AMD Ryzen 7 9800X3D") == 92

    def test_ryzen_7000(self):
        assert _estimate_platform_score_from_cpu("AMD Ryzen 5 7600") == 85

    def test_ryzen_5000(self):
        assert _estimate_platform_score_from_cpu("AMD Ryzen 5 5600G") == 53

    def test_unknown_returns_zero(self):
        assert _estimate_platform_score_from_cpu("Snapdragon X Elite") == 0


class TestMotherboardFallback:
    def test_oem_board_uses_cpu_estimation(self):
        # メーカー製PC: ボード名にチップセットがなくてもCPU世代で評価される
        specs = PCSpecs(cpu_name="12th Gen Intel(R) Core(TM) i7-12700",
                        motherboard="Dell Inc. 0KWVT8")
        result = analyze_motherboard(specs, PROFILES["mid"])
        assert "推定" in result.current_value
        assert result.score > 30          # 旧来の一律30点から改善されている
        assert result.status != "below"   # 12世代は mid 基準(60)を満たす

    def test_oem_board_with_old_cpu_is_below(self):
        specs = PCSpecs(cpu_name="Intel(R) Core(TM) i5-7400",
                        motherboard="NEC 952A")
        result = analyze_motherboard(specs, PROFILES["mid"])
        assert result.status == "below"

    def test_unknown_cpu_falls_back_to_30(self):
        specs = PCSpecs(cpu_name="Unknown CPU", motherboard="FUJITSU FJNB123")
        result = analyze_motherboard(specs, PROFILES["mid"])
        assert result.score == 30


# ---------------------------------------------------------------------------
# RAM提案のSODIMM切り替え
# ---------------------------------------------------------------------------

class TestLaptopRamOptions:
    def test_all_profiles_have_laptop_ram_table(self):
        for key, profile in PROFILES.items():
            assert "ram_laptop" in profile["upgrade_options"], key

    def test_laptop_gets_sodimm_options(self):
        specs = PCSpecs(ram_total_gb=8.0, ram_type="DDR4", is_laptop=True)
        result = analyze_ram(specs, PROFILES["mid"])
        assert result.upgrade_options
        assert all("SODIMM" in o["name"] for o in result.upgrade_options)

    def test_desktop_gets_dimm_options(self):
        specs = PCSpecs(ram_total_gb=8.0, ram_type="DDR4", is_laptop=False)
        result = analyze_ram(specs, PROFILES["mid"])
        assert result.upgrade_options
        assert all("SODIMM" not in o["name"] for o in result.upgrade_options)


# ---------------------------------------------------------------------------
# ノートPCの提案制約
# ---------------------------------------------------------------------------

class TestLaptopConstraints:
    def test_gpu_upgrade_is_suppressed(self):
        gpu = _score("GPU", "below",
                     recommendations=["VRAMが不足しています。"],
                     upgrade_options=[{"name": "RTX 5060"}])
        _apply_laptop_constraints([gpu])
        assert gpu.upgrade_options == []
        assert any("交換できません" in r for r in gpu.recommendations)

    def test_motherboard_upgrade_is_suppressed(self):
        mb = _score("マザーボード", "below",
                    upgrade_options=[{"name": "B760M"}])
        _apply_laptop_constraints([mb])
        assert mb.upgrade_options == []

    def test_network_options_become_usb(self):
        net = _score("ネットワーク", "below",
                     recommendations=["Wi-Fi規格が Wi-Fi 5 です。"],
                     upgrade_options=[{"name": "Intel BE200 Wi-Fi 7 (PCIe)"}])
        _apply_laptop_constraints([net])
        assert net.upgrade_options
        assert all("USB" in o["name"] for o in net.upgrade_options)

    def test_storage_gets_caveat(self):
        st = _score("ストレージ", "below",
                    recommendations=["SATA SSDが検出されました。"],
                    upgrade_options=[{"name": "Crucial P3 Plus 1TB"}])
        _apply_laptop_constraints([st])
        assert st.upgrade_options                      # 換装提案自体は残す
        assert any("機種により" in r for r in st.recommendations)

    def test_ok_components_are_untouched(self):
        gpu = _score("GPU", "meets")
        _apply_laptop_constraints([gpu])
        assert gpu.recommendations == []


# ---------------------------------------------------------------------------
# ノートPCの買い替え判定
# ---------------------------------------------------------------------------

class TestLaptopReplacement:
    def test_laptop_with_gpu_and_ram_below_is_replace(self):
        cores = [_score("CPU", "meets"), _score("RAM", "below"),
                 _score("GPU", "below"), _score("ストレージ", "meets")]
        rep = judge_replacement("mid", cores, _score("マザーボード", "meets"),
                                is_laptop=True)
        assert rep["verdict"] == "replace"
        assert "ノート" in rep["bto"]["keyword"]

    def test_laptop_with_only_gpu_below_is_consider(self):
        cores = [_score("CPU", "meets"), _score("RAM", "meets"),
                 _score("GPU", "below"), _score("ストレージ", "meets")]
        rep = judge_replacement("mid", cores, _score("マザーボード", "meets"),
                                is_laptop=True)
        assert rep["verdict"] == "consider"

    def test_laptop_with_only_storage_below_is_upgrade(self):
        # ストレージは換装できるので通常のアップグレード判定
        cores = [_score("CPU", "meets"), _score("RAM", "meets"),
                 _score("GPU", "meets"), _score("ストレージ", "below")]
        rep = judge_replacement("mid", cores, _score("マザーボード", "meets"),
                                is_laptop=True)
        assert rep["verdict"] == "upgrade"

    def test_desktop_keeps_desktop_bto(self):
        cores = [_score("CPU", "below"), _score("RAM", "below"),
                 _score("GPU", "below"), _score("ストレージ", "meets")]
        rep = judge_replacement("mid", cores, _score("マザーボード", "below"),
                                is_laptop=False)
        assert "ノート" not in rep["bto"]["keyword"]
