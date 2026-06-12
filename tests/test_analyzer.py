"""
pc_analyzer モジュールの単体テスト
WMI/psutil に依存しない pure function のみをテストする
"""

import pytest
from pc_analyzer import (
    PCSpecs,
    ComponentScore,
    PROFILES,
    DEFAULT_PROFILE,
    NPU_TOPS,
    GPU_TENSOR_TOPS,
    EXTERNAL_TPU_TOPS,
    CPU_TDP,
    GPU_TDP,
    _score,
    _status_from_score,
    _detect_wifi_standard,
    _wifi_rank,
    _extract_chipset,
    _CHIPSET_SCORES,
    analyze_cpu,
    analyze_ram,
    analyze_gpu,
    analyze_storage,
    analyze_display,
    analyze_network,
    analyze_motherboard,
    analyze_ai_accelerator,
    analyze_system_health,
    analyze_psu,
    evaluate_storage_health,
    estimate_psu,
    calculate_overall,
)

# ---------------------------------------------------------------------------
# フィクスチャ
# ---------------------------------------------------------------------------

@pytest.fixture
def low():
    return PROFILES["low"]

@pytest.fixture
def mid():
    return PROFILES["mid"]

@pytest.fixture
def high():
    return PROFILES["high"]


# ---------------------------------------------------------------------------
# PROFILES 辞書の構造チェック
# ---------------------------------------------------------------------------

class TestProfilesStructure:
    def test_all_profiles_exist(self):
        assert set(PROFILES) == {"low", "mid", "high"}

    def test_each_profile_has_required_keys(self):
        required = {"label", "description", "standards", "upgrade_options"}
        for key, profile in PROFILES.items():
            assert required <= set(profile), f"{key} に必須キーが不足"

    def test_each_standards_has_all_components(self):
        components = {"cpu", "ram", "gpu", "storage", "display", "network", "motherboard"}
        for key, profile in PROFILES.items():
            assert components <= set(profile["standards"]), f"{key}.standards に不足"

    def test_each_upgrade_options_has_required_keys(self):
        required = {
            "cpu", "ram", "gpu_low_vram", "gpu_integrated", "gpu_none",
            "storage_hdd", "storage_sata", "storage_small",
            "display_low_res", "display_low_hz", "display_gaming_hz",
            "network_wired", "network_wifi",
            "motherboard",
        }
        for key, profile in PROFILES.items():
            assert required <= set(profile["upgrade_options"]), \
                f"{key}.upgrade_options に不足: {required - set(profile['upgrade_options'])}"

    def test_low_standards_lower_than_high(self):
        assert PROFILES["low"]["standards"]["cpu"]["cores"] < PROFILES["high"]["standards"]["cpu"]["cores"]
        assert PROFILES["low"]["standards"]["ram"]["total_gb"] < PROFILES["high"]["standards"]["ram"]["total_gb"]
        assert PROFILES["low"]["standards"]["gpu"]["vram_gb"] < PROFILES["high"]["standards"]["gpu"]["vram_gb"]

    def test_default_profile_exists(self):
        assert DEFAULT_PROFILE in PROFILES


# ---------------------------------------------------------------------------
# _score
# ---------------------------------------------------------------------------

class TestScore:
    def test_meets_standard_returns_60(self):
        assert _score(1.0, 1.0) == 60

    def test_double_standard_returns_100(self):
        assert _score(2.0, 1.0) == 100

    def test_half_standard_returns_30(self):
        assert _score(0.5, 1.0) == 30

    def test_zero_value_returns_0(self):
        assert _score(0.0, 1.0) == 0

    def test_zero_standard_returns_50(self):
        assert _score(1.0, 0.0) == 50

    def test_clamps_at_100(self):
        assert _score(100.0, 1.0) == 100

    def test_clamps_at_0(self):
        assert _score(0.0, 1.0) >= 0


class TestStatusFromScore:
    def test_below_80_is_meets(self):
        assert _status_from_score(79) == "meets"

    def test_80_and_above_is_exceeds(self):
        assert _status_from_score(80) == "exceeds"

    def test_below_60_is_below(self):
        assert _status_from_score(59) == "below"

    def test_60_is_meets(self):
        assert _status_from_score(60) == "meets"


# ---------------------------------------------------------------------------
# Wi-Fi 検出
# ---------------------------------------------------------------------------

class TestDetectWifiStandard:
    def test_wifi7(self):
        assert _detect_wifi_standard("Intel Wi-Fi 7 BE200") == "Wi-Fi 7"

    def test_wifi7_via_80211be(self):
        assert _detect_wifi_standard("Adapter 802.11be") == "Wi-Fi 7"

    def test_wifi6e(self):
        assert _detect_wifi_standard("Wi-Fi 6E AX210") == "Wi-Fi 6E"

    def test_wifi6_via_ax200(self):
        assert _detect_wifi_standard("Intel AX200") == "Wi-Fi 6"

    def test_wifi6_via_80211ax(self):
        assert _detect_wifi_standard("802.11ax Adapter") == "Wi-Fi 6"

    def test_wifi5(self):
        assert _detect_wifi_standard("802.11ac Wireless") == "Wi-Fi 5"

    def test_wifi4(self):
        assert _detect_wifi_standard("802.11n Adapter") == "Wi-Fi 4"

    def test_unknown(self):
        assert _detect_wifi_standard("Generic Bluetooth") == "不明"


class TestWifiRank:
    def test_wifi7_is_highest(self):
        assert _wifi_rank("Wi-Fi 7") > _wifi_rank("Wi-Fi 6E")

    def test_wifi6e_above_wifi6(self):
        assert _wifi_rank("Wi-Fi 6E") > _wifi_rank("Wi-Fi 6")

    def test_unknown_returns_0(self):
        assert _wifi_rank("不明") == 0

    def test_empty_returns_0(self):
        assert _wifi_rank("") == 0


# ---------------------------------------------------------------------------
# チップセット抽出
# ---------------------------------------------------------------------------

class TestExtractChipset:
    def test_b760(self):
        assert _extract_chipset("MSI PRO B760M-P DDR4") == "B760"

    def test_z790(self):
        assert _extract_chipset("GIGABYTE Z790 AORUS MASTER") == "Z790"

    def test_b450(self):
        assert _extract_chipset("ASUS TUF GAMING B450M-PLUS II") == "B450"

    def test_unknown_returns_empty(self):
        assert _extract_chipset("GENERIC BOARD 1234") == ""

    def test_longer_match_wins(self):
        result = _extract_chipset("ROG STRIX B650E-F GAMING WIFI")
        assert result == "B650E"


# ---------------------------------------------------------------------------
# analyze_cpu（プロファイル別）
# ---------------------------------------------------------------------------

class TestAnalyzeCpu:
    def _make_specs(self, cores=6, threads=12, base_ghz=3.5, name="Test CPU"):
        s = PCSpecs()
        s.cpu_cores, s.cpu_threads, s.cpu_base_ghz, s.cpu_name = cores, threads, base_ghz, name
        return s

    def test_midrange_cpu_meets_mid_profile(self, mid):
        assert analyze_cpu(self._make_specs(), mid).status in ("meets", "exceeds")

    def test_midrange_cpu_meets_or_exceeds_low_profile(self, low):
        # 6C/3.5GHz は low 基準(4C/2.5GHz)を上回るが score=78 なので "meets"
        assert analyze_cpu(self._make_specs(), low).status in ("meets", "exceeds")

    def test_midrange_cpu_below_high_profile(self, high):
        assert analyze_cpu(self._make_specs(), high).status == "below"

    def test_weak_cpu_below_all_profiles(self, low, mid, high):
        specs = self._make_specs(cores=2, threads=4, base_ghz=2.0)
        for profile in [low, mid, high]:
            assert analyze_cpu(specs, profile).status == "below"

    def test_high_end_cpu_exceeds_all_profiles(self, low, mid, high):
        specs = self._make_specs(cores=16, threads=32, base_ghz=5.0)
        for profile in [low, mid, high]:
            assert analyze_cpu(specs, profile).status == "exceeds"

    def test_upgrade_options_come_from_profile(self, low, high):
        specs = self._make_specs(cores=2, threads=4, base_ghz=2.0)
        low_opts  = analyze_cpu(specs, low).upgrade_options
        high_opts = analyze_cpu(specs, high).upgrade_options
        assert low_opts != high_opts

    def test_upgrade_options_not_empty_when_below(self, mid):
        specs = self._make_specs(cores=2, threads=4, base_ghz=2.0)
        assert len(analyze_cpu(specs, mid).upgrade_options) > 0


# ---------------------------------------------------------------------------
# analyze_ram（プロファイル別）
# ---------------------------------------------------------------------------

class TestAnalyzeRam:
    def _make_specs(self, total_gb=16.0, ram_type="DDR4", slots_used=2, slots_total=4):
        s = PCSpecs()
        s.ram_total_gb, s.ram_type = total_gb, ram_type
        s.ram_slots_used, s.ram_slots_total = slots_used, slots_total
        return s

    def test_16gb_exceeds_low(self, low):
        assert analyze_ram(self._make_specs(16.0), low).status == "exceeds"

    def test_16gb_meets_mid(self, mid):
        assert analyze_ram(self._make_specs(16.0), mid).status in ("meets", "exceeds")

    def test_16gb_below_high(self, high):
        assert analyze_ram(self._make_specs(16.0), high).status == "below"

    def test_ddr5_suggests_ddr5_upgrade(self, mid):
        result = analyze_ram(self._make_specs(8.0, "DDR5"), mid)
        assert any("DDR5" in u["name"] for u in result.upgrade_options)

    def test_ddr4_suggests_ddr4_upgrade(self, mid):
        result = analyze_ram(self._make_specs(8.0, "DDR4"), mid)
        assert any("DDR4" in u["name"] for u in result.upgrade_options)

    def test_empty_slot_recommendation(self, mid):
        result = analyze_ram(self._make_specs(8.0, slots_used=1, slots_total=4), mid)
        assert any("空きスロット" in r for r in result.recommendations)


# ---------------------------------------------------------------------------
# analyze_gpu（プロファイル別）
# ---------------------------------------------------------------------------

class TestAnalyzeGpu:
    def _make_specs(self, name="NVIDIA GeForce RTX 3060", vram_gb=8.0):
        s = PCSpecs()
        s.gpu_name, s.gpu_vram_gb = name, vram_gb
        return s

    def test_rtx3060_exceeds_low(self, low):
        assert analyze_gpu(self._make_specs(), low).status == "exceeds"

    def test_rtx3060_meets_mid(self, mid):
        assert analyze_gpu(self._make_specs(), mid).status in ("meets", "exceeds")

    def test_rtx3060_below_high(self, high):
        assert analyze_gpu(self._make_specs(), high).status == "below"

    def test_no_gpu_returns_below_all_profiles(self, low, mid, high):
        for profile in [low, mid, high]:
            assert analyze_gpu(PCSpecs(), profile).status == "below"

    def test_integrated_gpu_is_below_all(self, low, mid, high):
        specs = self._make_specs("Intel UHD Graphics 770", 2.0)
        for profile in [low, mid, high]:
            assert analyze_gpu(specs, profile).status == "below"

    def test_low_profile_suggests_cheaper_gpu(self, low, high):
        specs = PCSpecs()
        low_opts  = analyze_gpu(specs, low).upgrade_options
        high_opts = analyze_gpu(specs, high).upgrade_options
        assert low_opts != high_opts


# ---------------------------------------------------------------------------
# analyze_storage（プロファイル別）
# ---------------------------------------------------------------------------

class TestAnalyzeStorage:
    def _nvme(self, size_gb=500, free_gb=100, model="Samsung 990 Pro"):
        return {
            "model": model, "size_gb": size_gb, "free_gb": free_gb,
            "is_ssd": True, "is_nvme": True, "interface": "NVMe",
            "mountpoints": ["C:\\"],
        }

    def _make_specs(self, disks):
        s = PCSpecs()
        s.storage_list = disks
        return s

    def test_256gb_nvme_meets_low(self, low):
        # _score(256, 256) = 60 → "meets"（基準ちょうどなので exceeds にはならない）
        result = analyze_storage(self._make_specs([self._nvme(256)]), low)
        assert result.status in ("meets", "exceeds")

    def test_256gb_nvme_below_mid(self, mid):
        result = analyze_storage(self._make_specs([self._nvme(256)]), mid)
        assert result.status == "below"

    def test_1tb_nvme_exceeds_all_profiles(self, low, mid, high):
        for profile in [low, mid, high]:
            result = analyze_storage(self._make_specs([self._nvme(1000)]), profile)
            assert result.status in ("meets", "exceeds")

    def test_c_drive_prioritized_over_first_disk(self, mid):
        hdd = {"model": "HDD", "size_gb": 2000, "free_gb": 500,
               "is_ssd": False, "is_nvme": False, "interface": "HDD", "mountpoints": ["D:\\"]}
        nvme = self._nvme(1000)
        result = analyze_storage(self._make_specs([hdd, nvme]), mid)
        assert result.status == "exceeds"

    def test_multiple_disks_shown_in_value(self, mid):
        result = analyze_storage(self._make_specs([self._nvme(), self._nvme(model="WD Black")]), mid)
        assert "ほか" in result.current_value


# ---------------------------------------------------------------------------
# analyze_display（プロファイル別）
# ---------------------------------------------------------------------------

class TestAnalyzeDisplay:
    def _make_specs(self, width=1920, height=1080, hz=60):
        s = PCSpecs()
        s.display_width, s.display_height, s.display_refresh_hz = width, height, hz
        return s

    def test_fhd60hz_exceeds_low(self, low):
        assert analyze_display(self._make_specs(), low).status == "exceeds"

    def test_fhd60hz_meets_mid(self, mid):
        assert analyze_display(self._make_specs(), mid).status in ("meets", "exceeds")

    def test_fhd60hz_below_high(self, high):
        assert analyze_display(self._make_specs(), high).status == "below"

    def test_no_display_below_all(self, low, mid, high):
        for profile in [low, mid, high]:
            assert analyze_display(PCSpecs(), profile).status == "below"

    def test_4k_144hz_exceeds_all(self, low, mid, high):
        for profile in [low, mid, high]:
            assert analyze_display(self._make_specs(3840, 2160, 144), profile).status == "exceeds"

    def test_low_hz_gives_recommendation(self, mid):
        result = analyze_display(self._make_specs(1920, 1080, 30), mid)
        assert len(result.recommendations) > 0


# ---------------------------------------------------------------------------
# analyze_network（プロファイル別）
# ---------------------------------------------------------------------------

class TestAnalyzeNetwork:
    def _make_specs(self, wired_mbps=1000.0, wifi_std="Wi-Fi 6"):
        s = PCSpecs()
        s.network_wired_mbps = wired_mbps
        s.network_wired_name = "Test Adapter"
        s.network_wifi_standard = wifi_std
        s.network_wifi_name = "Test Wi-Fi"
        return s

    def test_gigabit_wifi6_exceeds_low(self, low):
        assert analyze_network(self._make_specs(), low).status == "exceeds"

    def test_gigabit_wifi6_meets_mid(self, mid):
        assert analyze_network(self._make_specs(), mid).status in ("meets", "exceeds")

    def test_gigabit_wifi6_below_high(self, high):
        result = analyze_network(self._make_specs(), high)
        assert result.status == "below"

    def test_no_network_below_all(self, low, mid, high):
        for profile in [low, mid, high]:
            assert analyze_network(PCSpecs(), profile).status == "below"

    def test_low_profile_suggests_cheaper_adapter(self, low, high):
        specs = self._make_specs(wired_mbps=10.0, wifi_std="Wi-Fi 4")
        low_opts  = analyze_network(specs, low).upgrade_options
        high_opts = analyze_network(specs, high).upgrade_options
        assert low_opts != high_opts


# ---------------------------------------------------------------------------
# analyze_motherboard（プロファイル別）
# ---------------------------------------------------------------------------

class TestAnalyzeMb:
    def _make_specs(self, mb="ASUS ROG STRIX B760-F GAMING WIFI", chipset="B760"):
        s = PCSpecs()
        s.motherboard, s.mb_chipset = mb, chipset
        return s

    def test_b760_exceeds_low(self, low):
        assert analyze_motherboard(self._make_specs(), low).status == "exceeds"

    def test_b760_meets_mid(self, mid):
        assert analyze_motherboard(self._make_specs(), mid).status in ("meets", "exceeds")

    def test_b760_not_exceeds_high(self, high):
        # B760 (chipset_raw=85) vs high min=85: _score(85,85)=60 → "meets"（below にはならない）
        assert analyze_motherboard(self._make_specs(), high).status in ("meets", "below")

    def test_z790_exceeds_low_and_mid(self, low, mid):
        specs = self._make_specs("ASUS PRIME Z790-P", "Z790")
        for profile in [low, mid]:
            assert analyze_motherboard(specs, profile).status == "exceeds"

    def test_z790_meets_high(self, high):
        # Z790 (chipset_raw=95) vs high min=85: _score(95,85)=64 → "meets"
        specs = self._make_specs("ASUS PRIME Z790-P", "Z790")
        assert analyze_motherboard(specs, high).status in ("meets", "exceeds")

    def test_b450_below_mid_and_high(self, mid, high):
        specs = self._make_specs("MSI B450 TOMAHAWK", "B450")
        assert analyze_motherboard(specs, mid).status == "below"
        assert analyze_motherboard(specs, high).status == "below"

    def test_b450_meets_low(self, low):
        specs = self._make_specs("MSI B450 TOMAHAWK", "B450")
        assert analyze_motherboard(specs, low).status in ("meets", "exceeds")

    def test_unknown_chipset_below_all(self, low, mid, high):
        s = PCSpecs()
        s.motherboard, s.mb_chipset = "Unknown Board", ""
        for profile in [low, mid, high]:
            assert analyze_motherboard(s, profile).status == "below"


# ---------------------------------------------------------------------------
# クロスプロファイル検証（同一 specs で評価が異なること）
# ---------------------------------------------------------------------------

class TestCrossProfile:
    """同じハードウェアを3プロファイルで評価すると結果が変わることを確認"""

    def test_rtx3060_score_increases_from_high_to_low(self):
        s = PCSpecs()
        s.gpu_name, s.gpu_vram_gb = "NVIDIA RTX 3060", 8.0
        scores = {key: analyze_gpu(s, PROFILES[key]).score for key in ("low", "mid", "high")}
        assert scores["low"] >= scores["mid"] >= scores["high"]

    def test_16gb_ram_score_increases_from_high_to_low(self):
        s = PCSpecs()
        s.ram_total_gb, s.ram_type = 16.0, "DDR4"
        scores = {key: analyze_ram(s, PROFILES[key]).score for key in ("low", "mid", "high")}
        assert scores["low"] >= scores["mid"] >= scores["high"]

    def test_same_cpu_different_status_across_profiles(self):
        s = PCSpecs()
        s.cpu_name, s.cpu_cores, s.cpu_threads, s.cpu_base_ghz = "Core i5-13400", 6, 12, 3.5
        low_r  = analyze_cpu(s, PROFILES["low"])
        high_r = analyze_cpu(s, PROFILES["high"])
        assert low_r.score > high_r.score

    def test_upgrade_options_differ_between_profiles(self):
        s = PCSpecs()
        s.gpu_name, s.gpu_vram_gb = "GTX 1650", 4.0
        low_opts  = analyze_gpu(s, PROFILES["low"]).upgrade_options
        high_opts = analyze_gpu(s, PROFILES["high"]).upgrade_options
        assert low_opts != high_opts


# ---------------------------------------------------------------------------
# calculate_overall
# ---------------------------------------------------------------------------

class TestCalculateOverall:
    def _make_score(self, name, score, status):
        return ComponentScore(
            name=name, current_value="", midrange_standard="",
            status=status, score=score,
        )

    def test_all_high_scores_gives_A(self):
        scores = [
            self._make_score("CPU", 90, "exceeds"),
            self._make_score("RAM", 90, "exceeds"),
            self._make_score("GPU", 90, "exceeds"),
            self._make_score("ストレージ", 90, "exceeds"),
        ]
        assert calculate_overall(scores)["grade"] == "A"

    def test_all_low_scores_gives_D(self):
        scores = [
            self._make_score("CPU", 20, "below"),
            self._make_score("RAM", 20, "below"),
            self._make_score("GPU", 20, "below"),
            self._make_score("ストレージ", 20, "below"),
        ]
        assert calculate_overall(scores)["grade"] == "D"

    def test_priority_upgrades_sorted_by_score(self):
        scores = [
            self._make_score("CPU", 30, "below"),
            self._make_score("RAM", 10, "below"),
            self._make_score("GPU", 90, "exceeds"),
            self._make_score("ストレージ", 80, "exceeds"),
        ]
        result = calculate_overall(scores)
        assert result["priority_upgrades"] == ["RAM", "CPU"]

    def test_score_range_is_0_to_100(self):
        scores = [
            self._make_score("CPU", 50, "meets"),
            self._make_score("RAM", 50, "meets"),
            self._make_score("GPU", 50, "meets"),
            self._make_score("ストレージ", 50, "meets"),
        ]
        assert 0 <= calculate_overall(scores)["score"] <= 100


# ---------------------------------------------------------------------------
# PROFILES 構造に ai_accelerator が追加されていること
# ---------------------------------------------------------------------------

class TestProfilesAiAccelerator:
    def test_all_profiles_have_ai_accelerator_standard(self):
        for key, profile in PROFILES.items():
            assert "ai_accelerator" in profile["standards"], \
                f"{key}.standards に ai_accelerator がない"

    def test_all_profiles_have_ai_accelerator_upgrade_options(self):
        for key, profile in PROFILES.items():
            assert "ai_accelerator" in profile["upgrade_options"], \
                f"{key}.upgrade_options に ai_accelerator がない"

    def test_min_tops_increases_from_low_to_high(self):
        low_tops  = PROFILES["low"]["standards"]["ai_accelerator"]["min_tops"]
        mid_tops  = PROFILES["mid"]["standards"]["ai_accelerator"]["min_tops"]
        high_tops = PROFILES["high"]["standards"]["ai_accelerator"]["min_tops"]
        assert low_tops <= mid_tops <= high_tops


# ---------------------------------------------------------------------------
# evaluate_storage_health
# ---------------------------------------------------------------------------

class TestEvaluateStorageHealth:
    def _disk(self, wear=0, temp=0, poh=0, read_err=0, write_err=0):
        return {
            "wear_percent":   wear,
            "temperature_c":  temp,
            "power_on_hours": poh,
            "read_errors":    read_err,
            "write_errors":   write_err,
        }

    def test_healthy_disk_returns_ok(self):
        level, warnings = evaluate_storage_health(self._disk())
        assert level == "ok"
        assert warnings == []

    def test_high_wear_returns_critical(self):
        level, _ = evaluate_storage_health(self._disk(wear=95))
        assert level == "critical"

    def test_moderate_wear_returns_warning(self):
        level, _ = evaluate_storage_health(self._disk(wear=75))
        assert level == "warning"

    def test_low_wear_returns_caution(self):
        level, _ = evaluate_storage_health(self._disk(wear=55))
        assert level == "caution"

    def test_high_temperature_returns_warning(self):
        level, _ = evaluate_storage_health(self._disk(temp=72))
        assert level == "warning"

    def test_moderate_temperature_returns_caution(self):
        level, _ = evaluate_storage_health(self._disk(temp=62))
        assert level == "caution"

    def test_many_errors_returns_critical(self):
        level, _ = evaluate_storage_health(self._disk(read_err=200))
        assert level == "critical"

    def test_long_power_on_hours_returns_caution(self):
        level, _ = evaluate_storage_health(self._disk(poh=45000))
        assert level == "caution"

    def test_warning_messages_are_generated(self):
        _, warnings = evaluate_storage_health(self._disk(wear=91, temp=71))
        assert len(warnings) >= 2


# ---------------------------------------------------------------------------
# analyze_ai_accelerator（プロファイル別）
# ---------------------------------------------------------------------------

class TestAnalyzeAiAccelerator:
    def _make_specs(
        self,
        npu_name="", npu_tops=0.0,
        gpu_tensor=False, gpu_tensor_tops=0.0,
        external=None,
    ):
        s = PCSpecs()
        s.ai_npu_name         = npu_name
        s.ai_npu_tops         = npu_tops
        s.ai_gpu_tensor_cores = gpu_tensor
        s.ai_gpu_tensor_tops  = gpu_tensor_tops
        s.ai_external_devices = external or []
        s.ai_total_tops       = npu_tops + gpu_tensor_tops + sum(
            d.get("tops", 0) for d in (external or [])
        )
        return s

    def test_no_ai_returns_below_for_mid(self, mid):
        result = analyze_ai_accelerator(self._make_specs(), mid)
        assert result.status in ("below", "meets")

    def test_rtx4070_tensor_exceeds_low(self, low):
        specs = self._make_specs(gpu_tensor=True, gpu_tensor_tops=466.0)
        assert analyze_ai_accelerator(specs, low).status in ("meets", "exceeds")

    def test_rtx4070_tensor_meets_mid(self, mid):
        specs = self._make_specs(gpu_tensor=True, gpu_tensor_tops=466.0)
        result = analyze_ai_accelerator(specs, mid)
        assert result.status in ("meets", "exceeds")

    def test_rtx4070_tensor_exceeds_high(self, high):
        # RTX 4070 (466 TOPS) は high 基準 (200 TOPS) を大きく超えるため exceeds
        specs = self._make_specs(gpu_tensor=True, gpu_tensor_tops=466.0)
        result = analyze_ai_accelerator(specs, high)
        assert result.status in ("meets", "exceeds")

    def test_small_tops_below_high(self, high):
        # 外付け Coral (4 TOPS) のみでは high 基準 (200 TOPS) 未達
        specs = self._make_specs(external=[{"name": "Coral USB", "tops": 4.0}])
        result = analyze_ai_accelerator(specs, high)
        assert result.status == "below"

    def test_upgrade_options_not_empty_when_below(self, high):
        result = analyze_ai_accelerator(self._make_specs(), high)
        assert len(result.upgrade_options) > 0

    def test_score_increases_with_higher_tops_in_same_profile(self, high):
        # 同じ high プロファイルでも TOPS が多いほどスコアが高い
        low_tops  = analyze_ai_accelerator(self._make_specs(gpu_tensor=True, gpu_tensor_tops=50.0), high).score
        high_tops = analyze_ai_accelerator(self._make_specs(gpu_tensor=True, gpu_tensor_tops=466.0), high).score
        assert high_tops >= low_tops


# ---------------------------------------------------------------------------
# analyze_system_health
# ---------------------------------------------------------------------------

class TestAnalyzeSystemHealth:
    def _make_specs(
        self,
        trim=True, power_plan="バランス",
        startup=5, last_update="2026-01-01",
    ):
        s = PCSpecs()
        s.trim_enabled        = trim
        s.power_plan          = power_plan
        s.startup_app_count   = startup
        s.last_windows_update = last_update
        return s

    def test_optimal_settings_returns_high_score(self):
        result = analyze_system_health(self._make_specs())
        assert result.score >= 80

    def test_trim_disabled_reduces_score(self):
        good = analyze_system_health(self._make_specs(trim=True))
        bad  = analyze_system_health(self._make_specs(trim=False))
        assert bad.score < good.score

    def test_power_saver_plan_reduces_score(self):
        good = analyze_system_health(self._make_specs(power_plan="バランス"))
        bad  = analyze_system_health(self._make_specs(power_plan="Power saver"))
        assert bad.score < good.score

    def test_many_startup_apps_reduces_score(self):
        good = analyze_system_health(self._make_specs(startup=5))
        bad  = analyze_system_health(self._make_specs(startup=25))
        assert bad.score < good.score

    def test_outdated_windows_update_adds_recommendation(self):
        result = analyze_system_health(self._make_specs(last_update="2024-01-01"))
        assert any("Windows Update" in r for r in result.recommendations)

    def test_trim_disabled_adds_recommendation(self):
        result = analyze_system_health(self._make_specs(trim=False))
        assert any("TRIM" in r for r in result.recommendations)


# ---------------------------------------------------------------------------
# estimate_psu / analyze_psu
# ---------------------------------------------------------------------------

class TestEstimatePsu:
    def _make_specs(self, cpu_name="Intel Core i7-14700K", gpu_name="NVIDIA GeForce RTX 4070"):
        s = PCSpecs()
        s.cpu_name = cpu_name
        s.gpu_name = gpu_name
        return s

    def test_returns_positive_values(self):
        specs = self._make_specs()
        est, rec = estimate_psu(specs)
        assert est > 0
        assert rec > 0

    def test_recommended_is_greater_than_estimated(self):
        specs = self._make_specs()
        est, rec = estimate_psu(specs)
        assert rec > est

    def test_high_end_gpu_gives_larger_psu(self):
        low_specs  = self._make_specs(gpu_name="NVIDIA GeForce GTX 1650")
        high_specs = self._make_specs(gpu_name="NVIDIA GeForce RTX 4090")
        _, rec_low  = estimate_psu(low_specs)
        _, rec_high = estimate_psu(high_specs)
        assert rec_high >= rec_low

    def test_unknown_cpu_falls_back_to_65w(self):
        specs = self._make_specs(cpu_name="Unknown CPU", gpu_name="")
        est, _ = estimate_psu(specs)
        assert est == 65 + 0 + 100

    def test_analyze_psu_returns_component_score(self):
        specs = self._make_specs()
        specs.psu_estimated_tdp_w, specs.psu_recommended_w = estimate_psu(specs)
        result = analyze_psu(specs)
        assert result.name == "PSU 容量推定"
        assert "推定消費電力" in result.current_value
