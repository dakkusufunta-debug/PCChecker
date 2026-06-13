"""
PCスペック収集・分析モジュール（プロファイル切替対応版）
Windows環境向け（psutil + WMI使用）
"""

import json
import platform
import re
import subprocess
import winreg
import psutil
import wmi
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# AI アクセラレータ TOPS テーブル（出典: 各社公式仕様書）
# ---------------------------------------------------------------------------

NPU_TOPS: dict[str, float] = {
    "Intel AI Boost": 11.0,            # Core Ultra 100/200 Series (Meteor Lake)
    "Intel AI Boost (Lunar Lake)": 48.0,  # Core Ultra 200V Series (Lunar Lake)
    "AMD Ryzen AI": 16.0,              # Ryzen 7040/8040 Series (XDNA)
    "AMD Ryzen AI (Strix)": 50.0,      # Ryzen AI 300 Series (XDNA2 / Strix Point)
}

GPU_TENSOR_TOPS: dict[str, float] = {
    # RTX 50 シリーズ
    "RTX 5090": 3352.0, "RTX 5080": 1801.0, "RTX 5070 Ti": 1407.0,
    "RTX 5070": 988.0,  "RTX 5060 Ti": 759.0, "RTX 5060": 614.0,
    # RTX 40 シリーズ
    "RTX 4090": 1321.0, "RTX 4080 SUPER": 836.0, "RTX 4080": 780.0,
    "RTX 4070 Ti SUPER": 706.0, "RTX 4070 Ti": 641.0,
    "RTX 4070 SUPER": 568.0, "RTX 4070": 466.0,
    "RTX 4060 Ti": 353.0, "RTX 4060": 242.0,
    # RTX 30 シリーズ
    "RTX 3090 Ti": 320.0, "RTX 3090": 285.0, "RTX 3080 Ti": 273.0,
    "RTX 3080": 238.0,  "RTX 3070 Ti": 174.0, "RTX 3070": 163.0,
    "RTX 3060 Ti": 136.0, "RTX 3060": 101.0,
    # RTX 20 シリーズ
    "RTX 2080 Ti": 107.0, "RTX 2080 SUPER": 89.0, "RTX 2080": 81.0,
    "RTX 2070 SUPER": 73.0, "RTX 2070": 57.0,
    "RTX 2060 SUPER": 57.0, "RTX 2060": 52.0,
}

EXTERNAL_TPU_TOPS: dict[str, float] = {
    "Coral USB": 4.0, "Coral M.2": 4.0, "Coral PCIe": 8.0,
    "Hailo-8": 26.0,  "Hailo-8L": 13.0,
}


# ---------------------------------------------------------------------------
# PSU 推定 TDP テーブル（出典: 各社公式仕様書）
# ---------------------------------------------------------------------------

CPU_TDP: dict[str, int] = {
    # Intel Core Ultra 200S (Arrow Lake)
    "Ultra 9 285K": 125, "Ultra 7 265K": 125, "Ultra 5 245K": 125,
    "Ultra 5 235": 65,
    # AMD Ryzen 9000
    "Ryzen 9 9950X": 170, "Ryzen 9 9900X": 120,
    "Ryzen 7 9800X3D": 120, "Ryzen 7 9700X": 65,
    "Ryzen 5 9600X": 65,
    # AMD Ryzen 5000 (追加分)
    "Ryzen 5 5600GT": 65,
    # Intel 第14世代
    "i9-14900K": 125, "i9-14900": 65,
    "i7-14700K": 125, "i7-14700": 65,
    "i5-14600K": 125, "i5-14400": 65,
    "i3-14100": 60,
    # Intel 第13世代
    "i9-13900K": 125, "i9-13900": 65,
    "i7-13700K": 125, "i7-13700": 65,
    "i5-13600K": 125, "i5-13400": 65,
    "i3-13100": 60,
    # Intel 第12世代
    "i9-12900K": 125, "i7-12700K": 125, "i5-12600K": 125,
    "i7-12700": 65,   "i5-12400": 65,   "i3-12100": 60,
    # AMD Ryzen 7000
    "Ryzen 9 7950X": 170, "Ryzen 9 7900X": 170, "Ryzen 9 7900": 65,
    "Ryzen 7 7800X3D": 120, "Ryzen 7 7700X": 105, "Ryzen 7 7700": 65,
    "Ryzen 5 7600X": 105,   "Ryzen 5 7600": 65,
    # AMD Ryzen 5000
    "Ryzen 9 5950X": 105, "Ryzen 9 5900X": 105,
    "Ryzen 7 5800X3D": 105, "Ryzen 7 5800X": 105, "Ryzen 7 5700X": 65,
    "Ryzen 5 5600X": 65, "Ryzen 5 5600": 65, "Ryzen 5 5500": 65,
}

GPU_TDP: dict[str, int] = {
    # RTX 50
    "RTX 5090": 575, "RTX 5080": 360, "RTX 5070 Ti": 300, "RTX 5070": 250,
    "RTX 5060 Ti": 180, "RTX 5060": 145,
    # RX 9000 (RDNA4)
    "RX 9070 XT": 304, "RX 9070": 220, "RX 9060 XT": 180,
    # Intel Arc B
    "Arc B580": 190, "Arc B570": 150,
    # RTX 40
    "RTX 4090": 450, "RTX 4080 SUPER": 320, "RTX 4080": 320,
    "RTX 4070 Ti SUPER": 285, "RTX 4070 Ti": 285,
    "RTX 4070 SUPER": 220, "RTX 4070": 200,
    "RTX 4060 Ti": 165, "RTX 4060": 115,
    # RTX 30
    "RTX 3090 Ti": 450, "RTX 3090": 350, "RTX 3080 Ti": 350,
    "RTX 3080": 320,  "RTX 3070 Ti": 290, "RTX 3070": 220,
    "RTX 3060 Ti": 200, "RTX 3060": 170,
    # RX 7000
    "RX 7900 XTX": 355, "RX 7900 XT": 315, "RX 7800 XT": 263,
    "RX 7700 XT": 245,  "RX 7600 XT": 190,  "RX 7600": 165,
    # RX 6000
    "RX 6900 XT": 300, "RX 6800 XT": 300, "RX 6700 XT": 230,
    "RX 6600 XT": 160, "RX 6500 XT": 107,
}


# ---------------------------------------------------------------------------
# スペックプロファイル定義（low / mid / high）
# ---------------------------------------------------------------------------

PROFILES: dict[str, dict] = {
    "low": {
        "label": "ロースペック（コスパ重視）",
        "description": "オフィスワーク・Webブラウジング・動画視聴中心",
        "standards": {
            "cpu":        {"cores": 4,    "threads": 8,  "base_ghz": 2.5,
                           "label": "Core i3-12100 / Ryzen 3 5300G 相当"},
            "ram":        {"total_gb": 8.0,
                           "label": "8GB DDR4"},
            "gpu":        {"vram_gb": 2.0,
                           "label": "GTX 1650 / 統合GPU可"},
            "storage":    {"total_gb": 256.0, "free_gb": 30.0, "is_ssd": True,
                           "label": "SATA SSD 256GB以上"},
            "display":    {"width": 1366, "height": 768, "refresh_hz": 60,
                           "label": "HD (1366×768) / 60Hz以上"},
            "network":    {"wired_mbps": 100.0, "wifi_rank": 4,
                           "label": "100Mbps有線 / Wi-Fi 4以上"},
            "motherboard":{"min_chipset_score": 28,
                           "label": "AM4 B350以上 / 第9世代Intel以降"},
            "ai_accelerator": {"min_tops": 0,
                               "label": "AI機能なし可"},
        },
        "upgrade_options": {
            "cpu": [
                {"name": "Intel Core i3-14100",   "price": "約 ¥22,000〜", "note": "4C/8T, 省電力・オフィス用途に最適"},
                {"name": "AMD Ryzen 5 5600GT",    "price": "約 ¥22,000〜", "note": "6C/12T, AM4・クーラー付属でコスパ良好"},
                {"name": "AMD Ryzen 5 7600",      "price": "約 ¥29,000〜", "note": "6C/12T, AM5移行も視野に入るなら"},
            ],
            "ram": [
                {"name": "DDR4-3200 8GB×1",              "price": "約 ¥9,000〜",  "note": "最低限のシングル構成"},
                {"name": "DDR4-3200 8GB×2 (16GB)",        "price": "約 ¥18,000〜", "note": "デュアルチャネルで体感向上"},
                {"name": "DDR5-4800 8GB×2 (16GB)",        "price": "約 ¥30,000〜", "note": "DDR5プラットフォーム向け最小構成"},
            ],
            "ram_laptop": [
                {"name": "DDR4-3200 SODIMM 8GB×2 (16GB)",  "price": "約 ¥18,000〜", "note": "ノートPC用・増設可否は機種によります"},
                {"name": "DDR5-4800 SODIMM 8GB×2 (16GB)",  "price": "約 ¥50,000〜", "note": "DDR5ノート用・増設可否は機種によります"},
            ],
            "gpu_low_vram": [
                {"name": "NVIDIA RTX 3050",  "price": "約 ¥30,000〜", "note": "6GB GDDR6, 補助電源不要・軽量ゲーム向け"},
                {"name": "Intel Arc B580",   "price": "約 ¥56,000〜", "note": "12GB GDDR6, VRAM大容量のエントリー上位"},
            ],
            "gpu_integrated": [
                {"name": "NVIDIA RTX 3050",  "price": "約 ¥30,000〜", "note": "6GB, 70W・補助電源不要モデルあり"},
                {"name": "Intel Arc B580",   "price": "約 ¥56,000〜", "note": "12GB, フルHDゲームも視野"},
            ],
            "storage_hdd": [
                {"name": "Crucial BX500 500GB (SATA SSD)", "price": "約 ¥17,000〜", "note": "HDDから快速換装の定番"},
                {"name": "Crucial P3 Plus 1TB (NVMe)",     "price": "約 ¥24,000〜", "note": "NVMe対応マザーボードなら"},
            ],
            "storage_sata": [
                {"name": "Crucial P3 Plus 1TB (NVMe Gen4)", "price": "約 ¥24,000〜", "note": "読み取り5000MB/s, コスパ重視"},
            ],
            "storage_small": [
                {"name": "Crucial BX500 500GB (SATA)",  "price": "約 ¥17,000〜", "note": "コスパ重視・容量追加"},
                {"name": "Crucial P3 Plus 1TB (NVMe)",  "price": "約 ¥24,000〜", "note": "大容量のデータドライブ向け"},
            ],
            "display_low_res": [
                {"name": "IODATA GigaCrysta 23.8型", "price": "約 ¥21,000〜", "note": "フルHD・ゲーミング対応の万能機"},
            ],
            "display_low_hz": [
                {"name": "IODATA GigaCrysta 23.8型", "price": "約 ¥21,000〜", "note": "高リフレッシュレート対応"},
            ],
            "display_gaming_hz": [
                {"name": "ASUS TUF Gaming VG249Q3A (24型 180Hz)", "price": "約 ¥28,000〜", "note": "IPS / 180Hz / FHD"},
            ],
            "network_wired": [
                {"name": "TP-Link UE300 (USB 3.0 Gigabit)", "price": "約 ¥1,500〜", "note": "USB接続・工事不要でGigabit化"},
            ],
            "network_wifi": [
                {"name": "TP-Link Archer T4E (PCIe Wi-Fi 5)", "price": "約 ¥2,500〜", "note": "AC1300, PCIe接続"},
                {"name": "TP-Link Archer TX20E (Wi-Fi 6)",    "price": "約 ¥3,500〜", "note": "Wi-Fi 6対応PCIeカード"},
            ],
            "motherboard": [
                {"name": "MSI PRO B450M-A MAX WIFI", "price": "約 ¥10,000〜（中古）", "note": "AM4, Wi-Fi付き, コスパ良好"},
                {"name": "ASUS PRIME B660M-A D4",    "price": "約 ¥14,000〜",         "note": "LGA1700, DDR4対応"},
            ],
            "gpu_none": [
                {"name": "NVIDIA RTX 3050", "price": "約 ¥30,000〜", "note": "6GB, 70W・補助電源不要モデルあり"},
                {"name": "Intel Arc B580",  "price": "約 ¥56,000〜", "note": "12GB, フルHDゲームも視野"},
            ],
            "ai_accelerator": [
                {"name": "Google Coral USB Accelerator", "price": "約 ¥17,000〜",
                 "note": "4 TOPS, USB接続・工事不要でAI推論を追加"},
            ],
        },
    },

    "mid": {
        "label": "ミドルスペック（汎用）",
        "description": "マルチタスク・ゲーム・クリエイティブ作業に対応",
        "standards": {
            "cpu":        {"cores": 6,      "threads": 12, "base_ghz": 3.5,
                           "label": "Core i5-13400 / Ryzen 5 7600 相当"},
            "ram":        {"total_gb": 16.0,
                           "label": "16GB DDR4/DDR5"},
            "gpu":        {"vram_gb": 8.0,
                           "label": "RTX 3060 / RX 6700 XT 相当"},
            "storage":    {"total_gb": 500.0, "free_gb": 100.0, "is_ssd": True,
                           "label": "NVMe SSD 500GB以上"},
            "display":    {"width": 1920, "height": 1080, "refresh_hz": 60,
                           "label": "フルHD (1920×1080) / 60Hz以上"},
            "network":    {"wired_mbps": 1000.0, "wifi_rank": 5,
                           "label": "Gigabit有線 / Wi-Fi 6 (802.11ax)以上"},
            "motherboard":{"min_chipset_score": 60,
                           "label": "第12世代Intel以降 / AMD AM5 (PCIe 4.0対応)"},
            "ai_accelerator": {"min_tops": 50,
                               "label": "NPU内蔵またはRTX 4060以上"},
        },
        "upgrade_options": {
            "cpu": [
                {"name": "AMD Ryzen 5 7600",       "price": "約 ¥29,000〜", "note": "6C/12T, AM5のコスパ定番"},
                {"name": "Intel Core i5-14400F",   "price": "約 ¥41,000〜", "note": "10C/16T, LGA1700の手堅い選択"},
                {"name": "AMD Ryzen 7 7800X3D",    "price": "約 ¥46,000〜", "note": "3D V-Cache搭載, ゲーム向け高コスパ"},
            ],
            "ram": [
                {"name": "DDR4-3200 8GB×2 (16GB)",  "price": "約 ¥18,000〜", "note": "コスパ重視・デュアルチャネル"},
                {"name": "DDR4-3600 16GB×2 (32GB)", "price": "約 ¥42,000〜", "note": "将来も余裕のある32GB構成"},
                {"name": "DDR5-4800 16GB×2 (32GB)", "price": "約 ¥64,000〜", "note": "DDR5プラットフォーム向け"},
            ],
            "ram_laptop": [
                {"name": "DDR4-3200 SODIMM 8GB×2 (16GB)",   "price": "約 ¥18,000〜", "note": "ノートPC用・増設可否は機種によります"},
                {"name": "DDR5-5600 SODIMM 16GB×2 (32GB)",  "price": "約 ¥85,000〜", "note": "DDR5ノート用32GB構成"},
            ],
            "gpu_low_vram": [
                {"name": "NVIDIA RTX 5060",   "price": "約 ¥56,000〜", "note": "8GB GDDR7, ミドルスペック定番"},
                {"name": "AMD RX 9060 XT",    "price": "約 ¥57,000〜", "note": "RDNA4世代, コスパ良好"},
            ],
            "gpu_integrated": [
                {"name": "NVIDIA RTX 5060",        "price": "約 ¥56,000〜", "note": "ミドルスペック定番, 8GB GDDR7"},
                {"name": "AMD RX 9060 XT",         "price": "約 ¥57,000〜", "note": "RDNA4世代, コスパ良好"},
                {"name": "NVIDIA RTX 5060 Ti 16GB", "price": "約 ¥95,000〜", "note": "16GB VRAM, より高パフォーマンス"},
            ],
            "storage_hdd": [
                {"name": "Crucial P3 Plus 1TB (NVMe)",    "price": "約 ¥24,000〜", "note": "コスパ重視のNVMe"},
                {"name": "WD Black SN850X 1TB (NVMe)",    "price": "約 ¥41,000〜", "note": "読み取り最大7300MB/s"},
                {"name": "Samsung 990 Pro 1TB (NVMe)",    "price": "約 ¥48,000〜", "note": "読み取り最大7450MB/s"},
            ],
            "storage_sata": [
                {"name": "Crucial P3 Plus 1TB (NVMe)",    "price": "約 ¥24,000〜", "note": "コスパ重視のNVMe"},
                {"name": "Samsung 990 Pro 1TB (NVMe)",    "price": "約 ¥48,000〜", "note": "読み取り最大7450MB/s"},
            ],
            "storage_small": [
                {"name": "Crucial P3 Plus 1TB (NVMe)",  "price": "約 ¥24,000〜", "note": "大容量・コスパ重視"},
            ],
            "display_low_res": [
                {"name": "IODATA GigaCrysta 23.8型",  "price": "約 ¥21,000〜", "note": "フルHD・ゲーミング対応"},
                {"name": "LG 27UL500-W (27型 4K)",    "price": "約 ¥35,000〜", "note": "4K UHDモニター"},
            ],
            "display_low_hz": [
                {"name": "ASUS TUF Gaming VG249Q3A (24型 180Hz)", "price": "約 ¥28,000〜", "note": "IPS / 180Hz / FHD"},
            ],
            "display_gaming_hz": [
                {"name": "ASUS TUF Gaming VG249Q3A (24型 180Hz)", "price": "約 ¥28,000〜", "note": "IPS / 180Hz / FHD"},
                {"name": "MSI G274QPF-QD (27型 QHD 165Hz)",       "price": "約 ¥35,000〜", "note": "QHD / 165Hz / 量子ドット"},
            ],
            "network_wired": [
                {"name": "Intel I225-V搭載 2.5GbE カード", "price": "約 ¥3,000〜", "note": "PCIe接続の2.5GbEアダプタ"},
            ],
            "network_wifi": [
                {"name": "Intel Wi-Fi 6E AX210 (PCIe)",   "price": "約 ¥4,000〜", "note": "Wi-Fi 6E対応, 6GHz帯使用可"},
                {"name": "Intel BE200 Wi-Fi 7 (PCIe)",    "price": "約 ¥8,000〜", "note": "Wi-Fi 7対応PCIeカード"},
            ],
            "motherboard": [
                {"name": "ASUS PRIME B760M-A",         "price": "約 ¥17,000〜", "note": "DDR4対応, LGA1700, コスパ重視"},
                {"name": "MSI MAG B650 TOMAHAWK WIFI", "price": "約 ¥35,000〜", "note": "AM5対応, DDR5, PCIe 4.0/5.0"},
            ],
            "gpu_none": [
                {"name": "NVIDIA RTX 5060", "price": "約 ¥56,000〜", "note": "ミドルスペックの定番, 8GB GDDR7"},
                {"name": "AMD RX 9060 XT",  "price": "約 ¥57,000〜", "note": "RDNA4世代, コスパ良好"},
            ],
            "ai_accelerator": [
                {"name": "Google Coral USB Accelerator",    "price": "約 ¥17,000〜",
                 "note": "4 TOPS, 手軽に追加できるAI推論デバイス"},
                {"name": "Intel Core Ultra 7 265K (AI Boost内蔵)", "price": "CPU交換参照",
                 "note": "36 TOPS NPU搭載 (Arrow Lake)"},
                {"name": "AMD Ryzen AI 9 HX 370 (Strix Point)", "price": "CPU交換参照",
                 "note": "50 TOPS NPU搭載 (XDNA2)"},
            ],
        },
    },

    "high": {
        "label": "ハイスペック（クリエイター・ゲーマー向け）",
        "description": "4Kゲーム・4K動画編集・AI開発・配信向け",
        "standards": {
            "cpu":        {"cores": 8,      "threads": 16, "base_ghz": 4.0,
                           "label": "Core i7-14700K / Ryzen 7 7800X3D 相当"},
            "ram":        {"total_gb": 32.0,
                           "label": "32GB DDR5"},
            "gpu":        {"vram_gb": 12.0,
                           "label": "RTX 4070 Ti / RX 7800 XT 以上"},
            "storage":    {"total_gb": 1000.0, "free_gb": 200.0, "is_ssd": True,
                           "label": "NVMe Gen4 SSD 1TB以上"},
            "display":    {"width": 2560, "height": 1440, "refresh_hz": 144,
                           "label": "QHD (2560×1440) / 144Hz以上"},
            "network":    {"wired_mbps": 2500.0, "wifi_rank": 6,
                           "label": "2.5GbE有線 / Wi-Fi 6E以上"},
            "motherboard":{"min_chipset_score": 85,
                           "label": "Z790 / B650E / X670E (PCIe 5.0/DDR5対応)"},
            "ai_accelerator": {"min_tops": 200,
                               "label": "RTX 4070+ または NPU+TPU構成"},
        },
        "upgrade_options": {
            "cpu": [
                {"name": "AMD Ryzen 7 9800X3D",    "price": "約 ¥61,000〜", "note": "3D V-Cache第2世代, ゲーム最強クラス"},
                {"name": "Intel Core Ultra 7 265K", "price": "約 ¥60,000〜", "note": "20C, NPU内蔵 (Arrow Lake)"},
                {"name": "AMD Ryzen 9 9950X",      "price": "約 ¥96,000〜", "note": "16C/32T, 動画編集・AI向け最強"},
            ],
            "ram": [
                {"name": "DDR5-6000 16GB×2 (32GB)",  "price": "約 ¥70,000〜",  "note": "ゲーム向け高クロック構成"},
                {"name": "DDR5-6000 32GB×2 (64GB)",  "price": "約 ¥130,000〜", "note": "動画編集・AI向け大容量"},
                {"name": "DDR4-3600 16GB×2 (32GB)",  "price": "約 ¥42,000〜",  "note": "DDR4プラットフォーム向け"},
            ],
            "ram_laptop": [
                {"name": "DDR5-5600 SODIMM 16GB×2 (32GB)",  "price": "約 ¥85,000〜",  "note": "ノートPC用32GB・増設可否は機種によります"},
                {"name": "DDR5-5600 SODIMM 32GB×2 (64GB)",  "price": "約 ¥160,000〜", "note": "クリエイター向け大容量ノート用"},
            ],
            "gpu_low_vram": [
                {"name": "AMD RX 9070 XT",    "price": "約 ¥93,000〜",  "note": "16GB, RDNA4ハイクラスのコスパ枠"},
                {"name": "NVIDIA RTX 5070",   "price": "約 ¥105,000〜", "note": "12GB GDDR7, WQHDゲーム快適"},
            ],
            "gpu_integrated": [
                {"name": "AMD RX 9070 XT",      "price": "約 ¥93,000〜",  "note": "16GB, RDNA4ハイクラスのコスパ枠"},
                {"name": "NVIDIA RTX 5070",     "price": "約 ¥105,000〜", "note": "12GB GDDR7, WQHDゲーム快適"},
                {"name": "NVIDIA RTX 5070 Ti",  "price": "約 ¥160,000〜", "note": "16GB GDDR7, 4Kゲームも視野"},
            ],
            "storage_hdd": [
                {"name": "WD Black SN850X 2TB (NVMe Gen4)",  "price": "約 ¥80,000〜", "note": "高速・大容量プレミアムSSD"},
                {"name": "Samsung 990 Pro 2TB (NVMe Gen4)",  "price": "約 ¥91,000〜", "note": "読み取り7450MB/s, 大容量"},
            ],
            "storage_sata": [
                {"name": "WD Black SN850X 2TB (NVMe Gen4)", "price": "約 ¥80,000〜", "note": "PS5互換の高速SSD"},
                {"name": "Samsung 990 Pro 2TB (NVMe Gen4)", "price": "約 ¥91,000〜", "note": "読み取り7450MB/s"},
            ],
            "storage_small": [
                {"name": "WD Black SN850X 2TB (NVMe Gen4)", "price": "約 ¥80,000〜", "note": "高速・大容量"},
                {"name": "Samsung 990 Pro 2TB (NVMe Gen4)", "price": "約 ¥91,000〜", "note": "容量・速度ともにトップクラス"},
            ],
            "display_low_res": [
                {"name": "LG 32GQ950-B (32型 4K 144Hz)",               "price": "約 ¥90,000〜",  "note": "Nano IPS 4K, ゲーム・クリエイター兼用"},
                {"name": "Samsung Odyssey Neo G8 (32型 4K 240Hz)",      "price": "約 ¥100,000〜", "note": "ミニLED 4K, 高輝度"},
                {"name": "ASUS ProArt PA32UCX (32型 4K)",               "price": "約 ¥200,000〜", "note": "クリエイター向けリファレンスモニター"},
            ],
            "display_low_hz": [
                {"name": "ASUS ROG Swift OLED PG27AQDM (27型 QHD 240Hz)", "price": "約 ¥120,000〜", "note": "OLED / 240Hz, ゲーミング最高峰"},
                {"name": "LG 27GR95QE-B (27型 QHD 240Hz OLED)",           "price": "約 ¥90,000〜",  "note": "OLED / 240Hz / QHD"},
            ],
            "display_gaming_hz": [
                {"name": "ASUS ROG Swift OLED PG27AQDM (27型 QHD 240Hz)", "price": "約 ¥120,000〜", "note": "OLED / 240Hz, 究極のゲーミング体験"},
                {"name": "Samsung Odyssey Neo G7 (32型 QHD 165Hz)",        "price": "約 ¥70,000〜",  "note": "ミニLED / 165Hz / QHD"},
            ],
            "network_wired": [
                {"name": "Intel X550-T1 (PCIe 10GbE NIC)",   "price": "約 ¥15,000〜", "note": "10ギガビット対応PCIe NIC"},
                {"name": "QNAP QNA-UC5G1T (USB 5GbE)",       "price": "約 ¥8,000〜",  "note": "USB接続5GbEアダプタ"},
            ],
            "network_wifi": [
                {"name": "Intel BE200 Wi-Fi 7 (PCIe)",          "price": "約 ¥8,000〜",  "note": "Wi-Fi 7対応, 320MHz幅"},
                {"name": "TP-Link Archer TBE550E (Wi-Fi 7)",    "price": "約 ¥13,000〜", "note": "Wi-Fi 7+Bluetooth 5.4 PCIeカード"},
            ],
            "motherboard": [
                {"name": "ASUS ROG STRIX Z790-E GAMING WIFI", "price": "約 ¥65,000〜", "note": "Intel最高峰 Z790, Wi-Fi 6E内蔵"},
                {"name": "MSI MEG X670E ACE",                  "price": "約 ¥80,000〜", "note": "AMD最高峰 X670E, PCIe 5.0 x2"},
                {"name": "GIGABYTE Z790 AORUS MASTER",         "price": "約 ¥55,000〜", "note": "Z790, 高機能・高耐久"},
            ],
            "gpu_none": [
                {"name": "AMD RX 9070 XT",     "price": "約 ¥93,000〜",  "note": "16GB, RDNA4ハイクラスのコスパ枠"},
                {"name": "NVIDIA RTX 5070 Ti", "price": "約 ¥160,000〜", "note": "16GB GDDR7, 4Kゲームも視野"},
            ],
            "ai_accelerator": [
                {"name": "NVIDIA RTX 5070",    "price": "約 ¥105,000〜",
                 "note": "988 TOPS Tensor Core, WQHDゲーム・AI推論を両立"},
                {"name": "NVIDIA RTX 5070 Ti", "price": "約 ¥160,000〜",
                 "note": "1407 TOPS Tensor Core, 最高峰クラスのAI処理性能"},
            ],
        },
    },
}

DEFAULT_PROFILE = "mid"


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------

@dataclass
class ComponentScore:
    """コンポーネント評価結果"""
    name: str
    current_value: str
    midrange_standard: str
    status: str           # "below" | "meets" | "exceeds"
    score: int            # 0〜100
    recommendations: list[str] = field(default_factory=list)
    upgrade_options: list[dict] = field(default_factory=list)
    notes: str = ""


@dataclass
class PCSpecs:
    """収集したPCスペック"""
    cpu_name: str = ""
    cpu_cores: int = 0
    cpu_threads: int = 0
    cpu_base_ghz: float = 0.0
    cpu_max_ghz: float = 0.0

    ram_total_gb: float = 0.0
    ram_available_gb: float = 0.0
    ram_type: str = ""
    ram_slots_used: int = 0
    ram_slots_total: int = 0

    gpu_name: str = ""
    gpu_vram_gb: float = 0.0
    gpu_driver: str = ""

    storage_list: list[dict] = field(default_factory=list)

    display_width: int = 0
    display_height: int = 0
    display_refresh_hz: int = 0
    display_name: str = ""

    network_wired_mbps: float = 0.0
    network_wired_name: str = ""
    network_wifi_standard: str = ""
    network_wifi_name: str = ""

    os_name: str = ""
    os_version: str = ""

    motherboard: str = ""
    mb_chipset: str = ""
    bios_version: str = ""

    # AI アクセラレータ
    ai_npu_name: str = ""
    ai_npu_tops: float = 0.0
    ai_external_devices: list[dict] = field(default_factory=list)
    ai_gpu_tensor_cores: bool = False
    ai_gpu_tensor_tops: float = 0.0
    ai_total_tops: float = 0.0

    # システム健全性
    trim_enabled: bool = True
    power_plan: str = ""
    startup_app_count: int = 0
    last_windows_update: str = ""

    # PSU 推定
    psu_estimated_tdp_w: int = 0
    psu_recommended_w: int = 0

    # 筐体タイプ(ノートPC判定)
    is_laptop: bool = False


# ---------------------------------------------------------------------------
# ヘルパー関数
# ---------------------------------------------------------------------------

def _get_gpu_vram_from_registry() -> float:
    """レジストリからGPUのDedicated VRAMを取得する（WMIの4GB上限問題を回避）"""
    try:
        base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as key:
            for i in range(20):
                try:
                    sub_name = f"{i:04d}"
                    with winreg.OpenKey(key, sub_name) as sub:
                        try:
                            vram_bytes, _ = winreg.QueryValueEx(sub, "HardwareInformation.qwMemorySize")
                            if vram_bytes and vram_bytes > 0:
                                return round(vram_bytes / (1024 ** 3), 1)
                        except FileNotFoundError:
                            pass
                        try:
                            vram_bytes, _ = winreg.QueryValueEx(sub, "HardwareInformation.MemorySize")
                            if vram_bytes and vram_bytes > 0:
                                return round(vram_bytes / (1024 ** 3), 1)
                        except FileNotFoundError:
                            pass
                except (FileNotFoundError, OSError):
                    continue
    except Exception:
        pass
    return 0.0


def _get_physical_disk_types() -> dict:
    """MSFT_PhysicalDisk WMI クラスで各ディスクのSSD/NVMe種別を取得する。
    BusType 8 = RAID/AHCI コントローラ経由のSATA（Intel RST等）も SATA として扱う。
    """
    result = {}
    try:
        c2 = wmi.WMI(namespace="root/microsoft/windows/storage")
        for d in c2.MSFT_PhysicalDisk():
            bus = int(getattr(d, "BusType", 0) or 0)
            media = int(getattr(d, "MediaType", 0) or 0)
            friendly = (getattr(d, "FriendlyName", "") or "").strip()
            serial = (getattr(d, "SerialNumber", "") or "").strip().replace(" ", "")

            is_nvme = bus == 17
            is_ssd = is_nvme or media == 4
            if is_nvme:
                bus_label = "NVMe"
            elif bus in (11, 8, 3):
                bus_label = "SATA"
            elif bus == 7:
                bus_label = "USB"
            else:
                bus_label = "不明"

            entry = {"is_ssd": is_ssd, "is_nvme": is_nvme, "bus_type": bus_label}
            if friendly:
                result[friendly] = entry
            if serial:
                result[serial] = entry
    except Exception:
        pass
    return result


def _detect_wifi_standard(name: str) -> str:
    """アダプタ名から Wi-Fi 規格を推定する"""
    n = name.lower()
    if "wi-fi 7" in n or "802.11be" in n:
        return "Wi-Fi 7"
    if "wi-fi 6e" in n or "6e" in n:
        return "Wi-Fi 6E"
    if "wi-fi 6" in n or "802.11ax" in n or "ax200" in n or "ax210" in n or "ax211" in n or "ax1690" in n:
        return "Wi-Fi 6"
    if "802.11ac" in n or "wi-fi 5" in n:
        return "Wi-Fi 5"
    if "802.11n" in n or "wi-fi 4" in n:
        return "Wi-Fi 4"
    return "不明"


def _wifi_rank(standard: str) -> int:
    return {"Wi-Fi 7": 7, "Wi-Fi 6E": 6, "Wi-Fi 6": 5, "Wi-Fi 5": 4, "Wi-Fi 4": 3}.get(standard, 0)


_CHIPSET_SCORES: dict[str, int] = {
    # Intel 第15世代 Arrow Lake (2024-)
    "Z890": 100, "B860": 90, "H810": 80,
    # Intel 第12-14世代 Alder/Raptor Lake (2022-2024)
    "Z790": 95, "B760": 85, "H770": 80, "H610": 65,
    "Z690": 85, "B660": 75, "H670": 72,
    # Intel 第11世代 Rocket Lake (2021)
    "Z590": 58, "B560": 52, "H570": 52, "H510": 42,
    # Intel 第10世代 Comet Lake (2020)
    "Z490": 48, "B460": 43, "H470": 43, "H410": 35,
    # Intel 第8-9世代 Coffee Lake (2018-2019)
    "Z390": 38, "B365": 33, "H370": 36, "Z370": 33, "B360": 28,
    # AMD AM5 800シリーズ (2024-)
    "X870E": 100, "X870": 95, "B850": 88, "B840": 65,
    # AMD AM5 (2022-)
    "X670E": 100, "X670": 95, "B650E": 90, "B650": 85, "A620": 70,
    # AMD AM4 (2017-2022)
    "X570": 58, "B550": 53, "A520": 43,
    "X470": 43, "B450": 38, "A320": 28,
    "X370": 33, "B350": 28,
}


def _extract_chipset(mb_name: str) -> str:
    """マザーボード名からチップセット型番を抽出する（長い型番を優先）"""
    name = mb_name.upper()
    for chip in sorted(_CHIPSET_SCORES, key=len, reverse=True):
        if chip in name:
            return chip
    return ""


def _estimate_platform_score_from_cpu(cpu_name: str) -> int:
    """CPU名の世代からプラットフォーム年代スコアを推定する

    メーカー製PC(Dell/Lenovo/NEC等)はマザーボード名が社内型番で
    チップセットを特定できないため、CPU世代を代替指標として使う。
    スコア感は _CHIPSET_SCORES と揃える(同世代チップセットの中間程度)。
    返り値 0 は推定不能。
    """
    name = cpu_name.lower()

    # Intel Core Ultra (2023〜) = 最新プラットフォーム
    if "core" in name and "ultra" in name:
        return 90

    # Intel Core iN-XXXX(X) 形式: 数字部の先頭が世代
    m = re.search(r"i[3579]-(\d{4,5})", name)
    if m:
        digits = m.group(1)
        gen = int(digits[:2]) if len(digits) == 5 else int(digits[0])
        if gen >= 14:
            return 85
        if gen >= 12:
            return 75
        if gen >= 10:
            return 48
        if gen >= 8:
            return 33
        return 20

    # AMD Ryzen XXXX 形式: 千の位が世代
    m = re.search(r"ryzen\s*(?:ai\s*)?[3579]?\s*(?:pro\s*)?(\d{4})", name)
    if m:
        series = int(m.group(1))
        if series >= 9000:
            return 92
        if series >= 7000:
            return 85
        if series >= 5000:
            return 53
        if series >= 3000:
            return 38
        return 25

    return 0


# ---------------------------------------------------------------------------
# ストレージ健全性
# ---------------------------------------------------------------------------

def get_storage_health() -> list[dict]:
    """PowerShell経由でストレージ健全性情報を取得する（追加依存なし）"""
    cmd = [
        "powershell", "-NoProfile", "-Command",
        "Get-PhysicalDisk | Get-StorageReliabilityCounter | "
        "Select-Object DeviceId, Wear, PowerOnHours, Temperature, "
        "ReadErrorsTotal, WriteErrorsTotal | ConvertTo-Json -Depth 3",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if not result.stdout:
            return []
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]
        return data if isinstance(data, list) else []
    except Exception:
        return []


def evaluate_storage_health(disk: dict) -> tuple[str, list[str]]:
    """ストレージの警告レベル ("ok"/"caution"/"warning"/"critical") とメッセージ一覧を返す"""
    warnings: list[str] = []
    level = "ok"
    _levels = ["ok", "caution", "warning", "critical"]

    def _max(a: str, b: str) -> str:
        return b if _levels.index(b) > _levels.index(a) else a

    wear = int(disk.get("wear_percent") or 0)
    if wear >= 90:
        level = _max(level, "critical")
        warnings.append(f"摩耗度 {wear}% - 早急な交換を推奨します。")
    elif wear >= 70:
        level = _max(level, "warning")
        warnings.append(f"摩耗度 {wear}% - 重要データのバックアップを推奨。")
    elif wear >= 50:
        level = _max(level, "caution")
        warnings.append(f"摩耗度 {wear}% - 残り寿命に注意してください。")

    temp = int(disk.get("temperature_c") or 0)
    if temp >= 70:
        level = _max(level, "warning")
        warnings.append(f"温度 {temp}℃ - 冷却強化を推奨します。")
    elif temp >= 60:
        level = _max(level, "caution")
        warnings.append(f"温度 {temp}℃ - やや高温です。換気を確認してください。")

    poh = int(disk.get("power_on_hours") or 0)
    if poh >= 40000:
        level = _max(level, "caution")
        warnings.append(f"通電時間 {poh:,}時間 - 経年的な交換時期に近づいています。")

    err = int(disk.get("read_errors") or 0) + int(disk.get("write_errors") or 0)
    if err > 100:
        level = _max(level, "critical")
        warnings.append(f"読書エラー {err}回 - ディスク障害の兆候があります。")
    elif err > 10:
        level = _max(level, "warning")
        warnings.append(f"読書エラー {err}回 - ディスクの状態を確認してください。")

    return level, warnings


# ---------------------------------------------------------------------------
# システム健全性チェック
# ---------------------------------------------------------------------------

def get_system_health() -> dict:
    """TRIM・電源プラン・スタートアップ数・最終WindowsUpdateを収集する"""
    result: dict = {
        "trim_enabled": True,
        "power_plan": "",
        "startup_app_count": 0,
        "last_windows_update": "",
    }

    # TRIM 設定（SSD向け）
    try:
        r = subprocess.run(
            ["fsutil", "behavior", "query", "DisableDeleteNotify"],
            capture_output=True, text=True, timeout=5,
        )
        result["trim_enabled"] = "= 0" in r.stdout or "0\r\n" in r.stdout
    except Exception:
        pass

    # アクティブな電源プラン
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance -Namespace root\\cimv2\\power -ClassName Win32_PowerPlan "
             "| Where-Object IsActive -eq $true | Select-Object -ExpandProperty ElementName"],
            capture_output=True, text=True, timeout=10,
        )
        result["power_plan"] = r.stdout.strip()
    except Exception:
        pass

    # スタートアップアプリ数（レジストリ Run キー）
    try:
        count = 0
        hives = [
            (winreg.HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        ]
        for hive, path in hives:
            try:
                with winreg.OpenKey(hive, path) as k:
                    i = 0
                    while True:
                        try:
                            winreg.EnumValue(k, i)
                            count += 1
                            i += 1
                        except OSError:
                            break
            except FileNotFoundError:
                pass
        result["startup_app_count"] = count
    except Exception:
        pass

    # 最終 Windows Update 適用日
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-HotFix | Sort-Object InstalledOn -Descending | "
             "Select-Object -First 1).InstalledOn.ToString('yyyy-MM-dd')"],
            capture_output=True, text=True, timeout=20,
        )
        result["last_windows_update"] = r.stdout.strip()
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# PSU 容量推定
# ---------------------------------------------------------------------------

def estimate_psu(specs: "PCSpecs") -> tuple[int, int]:
    """推定消費電力と推奨PSU容量を返す (estimated_w, recommended_w)"""
    cpu_name_l = specs.cpu_name.lower()
    cpu_tdp = 65
    for key, tdp in CPU_TDP.items():
        if key.lower() in cpu_name_l:
            cpu_tdp = tdp
            break

    gpu_name_l = specs.gpu_name.lower()
    gpu_tdp = 0
    for key, tdp in GPU_TDP.items():
        if key.lower() in gpu_name_l:
            gpu_tdp = tdp
            break

    # RAM・ストレージ・マザーボード・冷却等
    misc_w = 100
    estimated = cpu_tdp + gpu_tdp + misc_w

    # 余裕係数 1.5 倍 → 80Plus 標準容量に切り上げ
    raw_recommended = int(estimated * 1.5)
    for std_size in (450, 550, 650, 750, 850, 1000, 1200):
        if raw_recommended <= std_size:
            recommended = std_size
            break
    else:
        recommended = 1200

    return estimated, recommended


# ---------------------------------------------------------------------------
# スペック収集
# ---------------------------------------------------------------------------

def collect_specs() -> PCSpecs:
    """WMI + psutil でPCスペックを収集する"""
    specs = PCSpecs()
    c = wmi.WMI()

    # --- CPU ---
    try:
        cpu_info = c.Win32_Processor()[0]
        specs.cpu_name = cpu_info.Name.strip()
        specs.cpu_cores = cpu_info.NumberOfCores
        specs.cpu_threads = cpu_info.NumberOfLogicalProcessors
        max_mhz = cpu_info.MaxClockSpeed or 0
        specs.cpu_max_ghz = round(max_mhz / 1000, 2)
        freq = psutil.cpu_freq()
        if freq:
            specs.cpu_base_ghz = round(freq.min / 1000, 2) if freq.min > 0 else round(freq.current / 1000, 2)
        else:
            specs.cpu_base_ghz = specs.cpu_max_ghz
    except Exception:
        pass

    # --- RAM ---
    try:
        mem = psutil.virtual_memory()
        specs.ram_total_gb = round(mem.total / (1024 ** 3), 1)
        specs.ram_available_gb = round(mem.available / (1024 ** 3), 1)

        mem_modules = c.Win32_PhysicalMemory()
        specs.ram_slots_used = len(mem_modules)
        if mem_modules:
            mem_type_map = {20: "DDR", 21: "DDR2", 22: "DDR2 FB-DIMM", 24: "DDR3", 26: "DDR4", 34: "DDR5"}
            smbios_map    = {20: "DDR", 21: "DDR2", 22: "DDR2 FB-DIMM", 24: "DDR3", 26: "DDR4", 34: "DDR5"}
            first = mem_modules[0]
            mt = first.MemoryType or 0
            smt = getattr(first, "SMBIOSMemoryType", 0) or 0
            specs.ram_type = mem_type_map.get(mt) or smbios_map.get(smt) or "DDR4"

        try:
            boards = c.Win32_PhysicalMemoryArray()
            if boards:
                specs.ram_slots_total = boards[0].MemoryDevices or 0
        except Exception:
            pass
    except Exception:
        pass

    # --- GPU ---
    try:
        gpus = c.Win32_VideoController()
        selected = None
        for gpu in gpus:
            name = (gpu.Name or "").lower()
            if "intel" not in name and "microsoft" not in name:
                selected = gpu
                break
        if selected is None and gpus:
            selected = gpus[0]

        if selected:
            specs.gpu_name = selected.Name.strip()
            vram_gb = _get_gpu_vram_from_registry()
            if vram_gb and vram_gb > 0:
                specs.gpu_vram_gb = vram_gb
            else:
                vram_bytes = selected.AdapterRAM or 0
                specs.gpu_vram_gb = round(max(vram_bytes, 0) / (1024 ** 3), 1)
            specs.gpu_driver = selected.DriverVersion or ""
    except Exception:
        pass

    # --- Storage ---
    try:
        disk_usage = {p.mountpoint: psutil.disk_usage(p.mountpoint)
                      for p in psutil.disk_partitions(all=False)
                      if p.fstype}

        phys_disk_map = _get_physical_disk_types()

        disk_to_mountpoints: dict[str, list[str]] = {}
        try:
            part_to_logical: dict[str, str] = {}
            for assoc2 in c.Win32_LogicalDiskToPartition():
                try:
                    part_to_logical[assoc2.Antecedent.DeviceID] = assoc2.Dependent.DeviceID + "\\"
                except Exception:
                    continue
            for assoc1 in c.Win32_DiskDriveToDiskPartition():
                try:
                    dev_id = assoc1.Antecedent.DeviceID
                    part_id = assoc1.Dependent.DeviceID
                    if dev_id not in disk_to_mountpoints:
                        disk_to_mountpoints[dev_id] = []
                    if part_id in part_to_logical:
                        disk_to_mountpoints[dev_id].append(part_to_logical[part_id])
                except Exception:
                    continue
        except Exception:
            pass

        for disk in c.Win32_DiskDrive():
            model = (disk.Model or "").strip()
            size_bytes = int(disk.Size or 0)
            size_gb = round(size_bytes / (1024 ** 3), 0)
            serial = (disk.SerialNumber or "").strip()

            serial_clean = serial.replace(" ", "")
            phys = (
                phys_disk_map.get(model)
                or phys_disk_map.get(serial_clean)
                or next((v for k, v in phys_disk_map.items()
                         if model and (model in k or k in model)), None)
            )
            if phys:
                is_ssd, is_nvme, bus_type_label = phys["is_ssd"], phys["is_nvme"], phys["bus_type"]
            else:
                model_lower = model.lower()
                is_nvme = "nvme" in model_lower or bool(re.search(r"wds\d+\w+0[bc]", model_lower))
                is_ssd = is_nvme or "ssd" in model_lower or "solid" in model_lower
                bus_type_label = "NVMe" if is_nvme else "SATA" if is_ssd else "HDD"

            mounts = disk_to_mountpoints.get(disk.DeviceID, [])
            free_gb_map = {mp: round(disk_usage[mp].free / (1024 ** 3), 1)
                           for mp in mounts if mp in disk_usage}
            if free_gb_map:
                free_gb = free_gb_map.get("C:\\") or max(free_gb_map.values())
            else:
                free_gb = round(disk_usage["C:\\"].free / (1024 ** 3), 1) if "C:\\" in disk_usage else 0.0

            specs.storage_list.append({
                "model": model, "size_gb": size_gb, "free_gb": free_gb,
                "is_ssd": is_ssd, "is_nvme": is_nvme, "interface": bus_type_label,
                "mountpoints": mounts,
            })
    except Exception:
        pass

    # --- Display ---
    try:
        for vc in c.Win32_VideoController():
            w = int(vc.CurrentHorizontalResolution or 0)
            h = int(vc.CurrentVerticalResolution or 0)
            hz = int(vc.CurrentRefreshRate or 0)
            if w > 0 and h > 0:
                specs.display_width = w
                specs.display_height = h
                specs.display_refresh_hz = hz
                break
        monitors = c.Win32_DesktopMonitor()
        if monitors:
            specs.display_name = (monitors[0].Name or "").strip()
    except Exception:
        pass

    # --- Network ---
    try:
        for adapter in c.Win32_NetworkAdapter():
            if not getattr(adapter, "NetEnabled", False):
                continue
            name = adapter.Name or ""
            name_l = name.lower()
            speed_bps = int(adapter.Speed or 0)
            speed_mbps = round(speed_bps / 1_000_000, 0)

            is_wifi = any(k in name_l for k in ("wireless", "wi-fi", "wifi", "802.11", "wlan"))
            if is_wifi:
                std = _detect_wifi_standard(name)
                if _wifi_rank(std) > _wifi_rank(specs.network_wifi_standard):
                    specs.network_wifi_standard = std
                    specs.network_wifi_name = name
            elif speed_mbps > 0 and speed_mbps > specs.network_wired_mbps:
                specs.network_wired_mbps = speed_mbps
                specs.network_wired_name = name
    except Exception:
        pass

    # --- OS ---
    try:
        uname = platform.uname()
        specs.os_name = f"{uname.system} {uname.release}"
        specs.os_version = platform.version()
    except Exception:
        pass

    # --- マザーボード ---
    try:
        mb = c.Win32_BaseBoard()[0]
        specs.motherboard = f"{mb.Manufacturer} {mb.Product}".strip()
        specs.mb_chipset = _extract_chipset(specs.motherboard)
    except Exception:
        pass

    # --- 筐体タイプ(ノートPC判定) ---
    # ChassisTypes: 8-11=ノート系, 14=サブノート, 30=タブレット,
    # 31=コンバーチブル, 32=デタッチャブル
    try:
        laptop_types = {8, 9, 10, 11, 14, 30, 31, 32}
        for enclosure in c.Win32_SystemEnclosure():
            types = enclosure.ChassisTypes or []
            if any(int(t) in laptop_types for t in types):
                specs.is_laptop = True
                break
    except Exception:
        pass

    # --- AI アクセラレータ ---
    try:
        for device in c.Win32_PnPEntity():
            name = (device.Name or "").strip()
            if not name:
                continue
            name_l = name.lower()
            # Intel AI Boost / NPU
            if any(k in name_l for k in ("ai boost", "ipu device", "intel npu", "neural processor")):
                npu_key = "Intel AI Boost (Lunar Lake)" if "lunar" in name_l else "Intel AI Boost"
                specs.ai_npu_name = name
                specs.ai_npu_tops = NPU_TOPS.get(npu_key, NPU_TOPS["Intel AI Boost"])
            # AMD XDNA / Ryzen AI
            elif any(k in name_l for k in ("xdna", "ryzen ai", "amd npu")):
                npu_key = "AMD Ryzen AI (Strix)" if any(k in name_l for k in ("strix", "8040", "ai 300")) \
                    else "AMD Ryzen AI"
                specs.ai_npu_name = name
                specs.ai_npu_tops = NPU_TOPS.get(npu_key, NPU_TOPS["AMD Ryzen AI"])
            # 外付け TPU/VPU（Google Coral, Hailo 等）
            elif any(k in name_l for k in ("coral", "movidius", "myriad", "hailo")):
                tops = next(
                    (v for k, v in EXTERNAL_TPU_TOPS.items()
                     if k.lower().replace(" ", "") in name_l.replace(" ", "")),
                    0.0,
                )
                specs.ai_external_devices.append({"name": name, "tops": tops})

        # GPU Tensor Core 検出
        gpu_upper = specs.gpu_name.upper()
        if "RTX" in gpu_upper:
            specs.ai_gpu_tensor_cores = True
            for key, tops in GPU_TENSOR_TOPS.items():
                if key.upper() in gpu_upper:
                    specs.ai_gpu_tensor_tops = tops
                    break

        specs.ai_total_tops = (
            specs.ai_npu_tops
            + specs.ai_gpu_tensor_tops
            + sum(d.get("tops", 0.0) for d in specs.ai_external_devices)
        )
    except Exception:
        pass

    # --- ストレージ健全性（L2: PowerShell Get-StorageReliabilityCounter）---
    try:
        health_list = get_storage_health()
        for i, disk_entry in enumerate(specs.storage_list):
            raw = health_list[i] if i < len(health_list) else {}
            wear   = int(raw.get("Wear")             or 0)
            poh    = int(raw.get("PowerOnHours")     or 0)
            temp   = int(raw.get("Temperature")      or 0)
            r_err  = int(raw.get("ReadErrorsTotal")  or 0)
            w_err  = int(raw.get("WriteErrorsTotal") or 0)

            health_info = {
                "health_status":               "Healthy",
                "wear_percent":                wear,
                "power_on_hours":              poh,
                "temperature_c":               temp,
                "read_errors":                 r_err,
                "write_errors":                w_err,
                "estimated_life_remaining_pct": max(0, 100 - wear),
            }
            level, health_warnings = evaluate_storage_health(health_info)
            health_info["warning_level"]    = level
            health_info["health_warnings"]  = health_warnings
            disk_entry.update(health_info)
    except Exception:
        pass

    # --- システム健全性 ---
    try:
        sys_health = get_system_health()
        specs.trim_enabled        = sys_health.get("trim_enabled", True)
        specs.power_plan          = sys_health.get("power_plan", "")
        specs.startup_app_count   = sys_health.get("startup_app_count", 0)
        specs.last_windows_update = sys_health.get("last_windows_update", "")
    except Exception:
        pass

    # --- PSU 推定 ---
    try:
        specs.psu_estimated_tdp_w, specs.psu_recommended_w = estimate_psu(specs)
    except Exception:
        pass

    return specs


# ---------------------------------------------------------------------------
# スコアリング
# ---------------------------------------------------------------------------

def _score(value: float, standard: float, higher_is_better: bool = True) -> int:
    """0〜100のスコアを算出する"""
    if standard <= 0:
        return 50
    ratio = value / standard
    if higher_is_better:
        s = min(int(ratio * 60), 100)
        if ratio >= 1.0:
            s = min(60 + int((ratio - 1.0) * 40), 100)
    else:
        s = min(int((1 / ratio) * 60), 100) if ratio > 0 else 0
    return max(0, min(s, 100))


def _status_from_score(score: int) -> str:
    if score >= 80:
        return "exceeds"
    if score >= 60:
        return "meets"
    return "below"


# ---------------------------------------------------------------------------
# コンポーネント別分析（profile 引数追加）
# ---------------------------------------------------------------------------

def analyze_cpu(specs: PCSpecs, profile: dict) -> ComponentScore:
    std = profile["standards"]["cpu"]
    opts = profile["upgrade_options"]

    score_cores   = _score(specs.cpu_cores,    std["cores"])
    score_threads = _score(specs.cpu_threads,   std["threads"])
    score_freq    = _score(specs.cpu_base_ghz,  std["base_ghz"])
    score  = int(score_cores * 0.4 + score_threads * 0.3 + score_freq * 0.3)
    status = _status_from_score(score)

    recommendations: list[str] = []
    upgrade_options: list[dict] = []

    if specs.cpu_cores < std["cores"]:
        recommendations.append(
            f"物理コア数が {specs.cpu_cores} コアです。"
            f"この基準では {std['cores']} コア以上を推奨します。"
        )
        upgrade_options = opts["cpu"][:]

    if specs.cpu_base_ghz > 0 and specs.cpu_base_ghz < std["base_ghz"]:
        recommendations.append(
            f"ベースクロックが {specs.cpu_base_ghz} GHz と低めです。"
            f"{std['base_ghz']} GHz 以上を目安にしてください。"
        )

    if score >= 80:
        notes = "CPUはこの基準を大幅に上回っています。しばらくアップグレード不要です。"
    elif score >= 60:
        notes = "CPUはこの基準を概ね満たしています。"
    else:
        notes = "CPUアップグレードにより大幅なパフォーマンス向上が見込めます。"

    current_val = f"{specs.cpu_name} ({specs.cpu_cores}コア/{specs.cpu_threads}スレッド, {specs.cpu_base_ghz}GHz)"
    return ComponentScore(
        name="CPU", current_value=current_val,
        midrange_standard=std["label"], status=status, score=score,
        recommendations=recommendations, upgrade_options=upgrade_options, notes=notes,
    )


def analyze_ram(specs: PCSpecs, profile: dict) -> ComponentScore:
    std  = profile["standards"]["ram"]
    opts = profile["upgrade_options"]
    score  = _score(specs.ram_total_gb, std["total_gb"])
    status = _status_from_score(score)

    recommendations: list[str] = []
    upgrade_options: list[dict] = []

    if specs.ram_total_gb < std["total_gb"]:
        needed = std["total_gb"] - specs.ram_total_gb
        recommendations.append(
            f"現在 {specs.ram_total_gb}GB です。"
            f"この基準では {int(std['total_gb'])}GB 以上を推奨します（あと {needed:.0f}GB 必要）。"
        )
        ram_type = specs.ram_type or "DDR4"
        # ノートPCはSODIMM、デスクトップはDIMMの候補から選ぶ
        ram_table = opts.get("ram_laptop", opts["ram"]) if specs.is_laptop else opts["ram"]
        if "DDR5" in ram_type:
            upgrade_options = [o for o in ram_table if "DDR5" in o["name"]]
        else:
            upgrade_options = [o for o in ram_table if "DDR4" in o["name"]]

    if specs.ram_slots_total > 0 and specs.ram_slots_used < specs.ram_slots_total:
        empty = specs.ram_slots_total - specs.ram_slots_used
        recommendations.append(
            f"空きスロットが {empty} 本あります。"
            "同規格のRAMを追加してデュアルチャネル構成にすると帯域幅が向上します。"
        )

    if score >= 80:
        notes = "RAMは十分です。マルチタスクや動画編集も快適に行えます。"
    elif score >= 60:
        notes = "この基準を満たしています。"
    else:
        notes = "RAM増設はコストパフォーマンスが非常に高いアップグレードです。"

    slot_info   = f", スロット {specs.ram_slots_used}/{specs.ram_slots_total}" if specs.ram_slots_total > 0 else ""
    current_val = f"{specs.ram_total_gb}GB {specs.ram_type}{slot_info}"
    return ComponentScore(
        name="RAM", current_value=current_val,
        midrange_standard=std["label"], status=status, score=score,
        recommendations=recommendations, upgrade_options=upgrade_options, notes=notes,
    )


def analyze_gpu(specs: PCSpecs, profile: dict) -> ComponentScore:
    std  = profile["standards"]["gpu"]
    opts = profile["upgrade_options"]

    if not specs.gpu_name or specs.gpu_vram_gb == 0:
        return ComponentScore(
            name="GPU", current_value="検出できませんでした",
            midrange_standard=std["label"], status="below", score=0,
            recommendations=["GPUが検出できませんでした。専用GPUの搭載を検討してください。"],
            upgrade_options=opts["gpu_none"],
            notes="専用GPUが未搭載です。ゲームや映像制作には必須です。",
        )

    score = _score(specs.gpu_vram_gb, std["vram_gb"])
    is_integrated = any(k in specs.gpu_name.lower() for k in ["intel", "radeon vega", "uhd", "iris"])
    if is_integrated:
        score = min(score, 30)

    status = _status_from_score(score)
    recommendations: list[str] = []
    upgrade_options: list[dict] = []

    if is_integrated:
        recommendations.append("統合グラフィックスが検出されました。3Dゲームや映像制作には専用GPUが必要です。")
        upgrade_options = opts["gpu_integrated"][:]
    elif specs.gpu_vram_gb < std["vram_gb"]:
        recommendations.append(
            f"VRAM が {specs.gpu_vram_gb}GB です。"
            f"この基準では {std['vram_gb']:.0f}GB 以上を推奨します。"
        )
        upgrade_options = opts["gpu_low_vram"][:]

    if score >= 80:
        notes = "GPUはこの基準を超えています。快適な動作が期待できます。"
    elif score >= 60:
        notes = "この基準を概ね満たしています。"
    else:
        notes = "GPUアップグレードで体感パフォーマンスが劇的に向上します。"

    current_val = f"{specs.gpu_name} (VRAM: {specs.gpu_vram_gb}GB)"
    return ComponentScore(
        name="GPU", current_value=current_val,
        midrange_standard=std["label"], status=status, score=score,
        recommendations=recommendations, upgrade_options=upgrade_options, notes=notes,
    )


def analyze_storage(specs: PCSpecs, profile: dict) -> ComponentScore:
    std  = profile["standards"]["storage"]
    opts = profile["upgrade_options"]

    if not specs.storage_list:
        return ComponentScore(
            name="ストレージ", current_value="検出できませんでした",
            midrange_standard=std["label"], status="below", score=0,
            notes="ストレージ情報が取得できませんでした。",
        )

    primary = next(
        (d for d in specs.storage_list if "C:\\" in d.get("mountpoints", [])),
        specs.storage_list[0],
    )
    size_gb, free_gb, is_ssd, is_nvme = (
        primary["size_gb"], primary["free_gb"], primary["is_ssd"], primary["is_nvme"]
    )

    score = _score(size_gb, std["total_gb"])
    if not is_ssd:
        score = int(score * 0.5)
    elif not is_nvme:
        score = int(score * 0.85)

    status = _status_from_score(score)
    recommendations: list[str] = []
    upgrade_options: list[dict] = []

    if not is_ssd:
        recommendations.append("HDDが検出されました。NVMe SSDへの換装でOSの起動・アプリ読み込みが劇的に高速化します。")
        upgrade_options = opts["storage_hdd"][:]
    elif not is_nvme:
        recommendations.append("SATA SSDが検出されました。NVMe SSDに換装することでさらなる高速化が可能です。")
        upgrade_options = opts["storage_sata"][:]

    if size_gb < std["total_gb"]:
        recommendations.append(
            f"ストレージ容量が {size_gb:.0f}GB です。"
            f"この基準では {std['total_gb']:.0f}GB 以上を推奨します。"
        )
        if not upgrade_options:
            upgrade_options = opts["storage_small"][:]

    if free_gb < std["free_gb"]:
        recommendations.append(
            f"空き容量が {free_gb:.1f}GB と少なくなっています。"
            "不要ファイルの整理または増設を推奨します。"
        )

    if score >= 80:
        notes = "ストレージはこの基準を十分に満たしています。"
    elif score >= 60:
        notes = "ストレージは概ね問題ありません。"
    else:
        notes = "ストレージのアップグレードはコストパフォーマンスが高い投資です。"

    storage_type = "NVMe SSD" if is_nvme else ("SATA SSD" if is_ssd else "HDD")
    current_val  = f"{primary['model']} ({size_gb:.0f}GB, {storage_type}, 空き: {free_gb:.1f}GB)"
    if len(specs.storage_list) > 1:
        current_val += f"  ほか {len(specs.storage_list) - 1} 台"

    return ComponentScore(
        name="ストレージ", current_value=current_val,
        midrange_standard=std["label"], status=status, score=score,
        recommendations=recommendations, upgrade_options=upgrade_options, notes=notes,
    )


def analyze_display(specs: PCSpecs, profile: dict) -> ComponentScore:
    std  = profile["standards"]["display"]
    opts = profile["upgrade_options"]

    if specs.display_width == 0 or specs.display_height == 0:
        return ComponentScore(
            name="ディスプレイ", current_value="検出できませんでした",
            midrange_standard=std["label"], status="below", score=0,
            notes="ディスプレイ情報を取得できませんでした。モニターが接続されているか確認してください。",
        )

    pixel_score = _score(specs.display_width * specs.display_height, std["width"] * std["height"])
    hz_score    = _score(specs.display_refresh_hz, std["refresh_hz"]) if specs.display_refresh_hz > 0 else 50
    score  = int(pixel_score * 0.6 + hz_score * 0.4)
    status = _status_from_score(score)

    recommendations: list[str] = []
    upgrade_options: list[dict] = []

    if specs.display_width < std["width"] or specs.display_height < std["height"]:
        recommendations.append(
            f"解像度が {specs.display_width}×{specs.display_height} です。"
            f"この基準では {std['width']}×{std['height']} 以上を推奨します。"
        )
        upgrade_options = opts["display_low_res"][:]

    if specs.display_refresh_hz > 0 and specs.display_refresh_hz < 60:
        recommendations.append(f"リフレッシュレートが {specs.display_refresh_hz}Hz と低めです。60Hz以上を推奨します。")
        upgrade_options = opts["display_low_hz"][:]
    elif specs.display_refresh_hz > 0 and specs.display_refresh_hz < std["refresh_hz"]:
        recommendations.append(
            f"現在 {specs.display_refresh_hz}Hz です。"
            f"この基準では {std['refresh_hz']}Hz 以上を推奨します。"
        )
        if not upgrade_options:
            upgrade_options = opts["display_gaming_hz"][:]

    if score >= 80:
        notes = "ディスプレイはこの基準を十分に満たしています。"
    elif score >= 60:
        notes = "この基準を概ね満たしています。"
    else:
        notes = "ディスプレイのアップグレードで作業効率・没入感が大幅に向上します。"

    name_part   = f" ({specs.display_name})" if specs.display_name else ""
    current_val = f"{specs.display_width}×{specs.display_height} / {specs.display_refresh_hz}Hz{name_part}"
    return ComponentScore(
        name="ディスプレイ", current_value=current_val,
        midrange_standard=std["label"], status=status, score=score,
        recommendations=recommendations, upgrade_options=upgrade_options, notes=notes,
    )


def analyze_network(specs: PCSpecs, profile: dict) -> ComponentScore:
    std  = profile["standards"]["network"]
    opts = profile["upgrade_options"]

    has_wired = specs.network_wired_mbps > 0
    has_wifi  = bool(specs.network_wifi_standard and specs.network_wifi_standard != "不明")

    if not has_wired and not has_wifi:
        return ComponentScore(
            name="ネットワーク", current_value="検出できませんでした",
            midrange_standard=std["label"], status="below", score=0,
            notes="有効なネットワークアダプタが検出できませんでした。",
        )

    wired_score = _score(specs.network_wired_mbps, std["wired_mbps"]) if has_wired else 0
    wifi_score  = min(int(_wifi_rank(specs.network_wifi_standard) / 7 * 100), 100) if has_wifi else 0

    if has_wired and has_wifi:
        score = int(wired_score * 0.6 + wifi_score * 0.4)
    elif has_wired:
        score = wired_score
    else:
        score = wifi_score

    status = _status_from_score(score)
    recommendations: list[str] = []
    upgrade_options: list[dict] = []

    if has_wired and specs.network_wired_mbps < std["wired_mbps"]:
        recommendations.append(
            f"有線LANが {specs.network_wired_mbps:.0f}Mbps です。"
            f"この基準では {std['wired_mbps']:.0f}Mbps 以上を推奨します。"
        )
        upgrade_options.extend(opts["network_wired"])

    wifi_rank_val = _wifi_rank(specs.network_wifi_standard) if has_wifi else 0
    if wifi_rank_val < std["wifi_rank"]:
        if not has_wifi:
            recommendations.append("Wi-Fiアダプタが検出されませんでした。この基準のWi-Fi対応アダプタの追加を検討してください。")
        else:
            recommendations.append(
                f"Wi-Fi規格が {specs.network_wifi_standard} です。"
                f"この基準ではWi-Fi {'6E' if std['wifi_rank'] >= 6 else '6'} 以上を推奨します。"
            )
        upgrade_options.extend(opts["network_wifi"])

    if score >= 80:
        notes = "ネットワーク環境はこの基準を十分に満たしています。"
    elif score >= 60:
        notes = "この基準を概ね満たしています。"
    else:
        notes = "ネットワークアダプタのアップグレードで通信速度・安定性が向上します。"

    parts = []
    if has_wired:
        parts.append(f"有線 {specs.network_wired_mbps:.0f}Mbps ({specs.network_wired_name})")
    if has_wifi:
        parts.append(f"{specs.network_wifi_standard} ({specs.network_wifi_name})")
    current_val = " / ".join(parts)

    return ComponentScore(
        name="ネットワーク", current_value=current_val,
        midrange_standard=std["label"], status=status, score=score,
        recommendations=recommendations, upgrade_options=upgrade_options, notes=notes,
    )


def analyze_motherboard(specs: PCSpecs, profile: dict) -> ComponentScore:
    std  = profile["standards"]["motherboard"]
    opts = profile["upgrade_options"]
    mb_name = specs.motherboard or "不明"
    chipset = specs.mb_chipset

    if not chipset:
        # メーカー製PCはボード名にチップセットが含まれないため、
        # CPU世代からプラットフォーム年代を代替推定する
        estimated = _estimate_platform_score_from_cpu(specs.cpu_name)
        if estimated > 0:
            score  = _score(estimated, std["min_chipset_score"])
            status = _status_from_score(score)
            if score >= 60:
                notes = "CPU世代からの推定で、プラットフォームはこの基準を概ね満たしています。"
            else:
                notes = "CPU世代からの推定で、プラットフォームがこの基準より古い可能性があります。"
            return ComponentScore(
                name="マザーボード",
                current_value=f"{mb_name} (CPU世代から推定)",
                midrange_standard=std["label"], status=status, score=score,
                recommendations=["メーカー製PCのためチップセットを特定できませんでした。"
                                 "CPU世代に基づく推定評価です。"],
                notes=notes,
            )
        return ComponentScore(
            name="マザーボード", current_value=mb_name,
            midrange_standard=std["label"], status="below", score=30,
            recommendations=["チップセットを特定できませんでした。マザーボードが古い可能性があります。"],
            notes="チップセット情報が不明なため正確な評価ができません。",
        )

    chipset_raw   = _CHIPSET_SCORES.get(chipset, 30)
    min_score     = std["min_chipset_score"]
    score         = _score(chipset_raw, min_score)
    status        = _status_from_score(score)

    recommendations: list[str] = []
    upgrade_options: list[dict] = []

    if chipset_raw < min_score:
        recommendations.append(
            f"チップセット {chipset} はこの基準（スコア {min_score} 以上）を下回っています。"
            "より新しいプラットフォームへの移行を検討してください。"
        )
        upgrade_options = opts["motherboard"][:]

    if score >= 80:
        notes = f"チップセット {chipset} はこの基準に対して十分な性能を持つプラットフォームです。"
    elif score >= 60:
        notes = f"チップセット {chipset} はこの基準を概ね満たしています。"
    else:
        notes = f"チップセット {chipset} はこの基準を下回っています。プラットフォーム全体の更新を検討してください（CPU・RAM・マザーボードのセット交換）。"

    current_val = f"{mb_name} (チップセット: {chipset})"
    return ComponentScore(
        name="マザーボード", current_value=current_val,
        midrange_standard=std["label"], status=status, score=score,
        recommendations=recommendations, upgrade_options=upgrade_options, notes=notes,
    )


# ---------------------------------------------------------------------------
# AI アクセラレータ分析
# ---------------------------------------------------------------------------

def analyze_ai_accelerator(specs: PCSpecs, profile: dict) -> ComponentScore:
    std  = profile["standards"].get("ai_accelerator", {"min_tops": 0, "label": "AI機能なし可"})
    opts = profile["upgrade_options"].get("ai_accelerator", [])

    total_tops = specs.ai_total_tops
    min_tops   = float(std.get("min_tops", 0))

    if min_tops == 0:
        score = 80 if total_tops > 0 else 60
    else:
        score = _score(total_tops, min_tops)

    status = _status_from_score(score)
    recommendations: list[str] = []
    upgrade_options: list[dict] = []

    if total_tops == 0:
        recommendations.append(
            "AI アクセラレータ（NPU/Tensor Core/外付けTPU）が検出されませんでした。"
        )
        upgrade_options = opts[:]
    elif total_tops < min_tops:
        recommendations.append(
            f"AI 処理性能が {total_tops:.0f} TOPS です。"
            f"この基準では {min_tops:.0f} TOPS 以上を推奨します。"
        )
        upgrade_options = opts[:]

    parts: list[str] = []
    if specs.ai_npu_name:
        parts.append(f"NPU: {specs.ai_npu_name} ({specs.ai_npu_tops:.0f} TOPS)")
    if specs.ai_gpu_tensor_cores:
        parts.append(f"GPU Tensor Core ({specs.ai_gpu_tensor_tops:.0f} TOPS)")
    for d in specs.ai_external_devices:
        parts.append(f"外付け: {d['name']} ({d.get('tops', 0):.0f} TOPS)")
    current_val = " / ".join(parts) if parts else f"なし (合計 {total_tops:.0f} TOPS)"

    if score >= 80:
        notes = f"AI 処理性能は十分です（合計 {total_tops:.0f} TOPS）。"
    elif score >= 60:
        notes = f"AI 処理性能はこの基準を概ね満たしています（合計 {total_tops:.0f} TOPS）。"
    else:
        notes = f"AIワークロードには性能不足の可能性があります（合計 {total_tops:.0f} TOPS）。"

    return ComponentScore(
        name="AI アクセラレータ", current_value=current_val,
        midrange_standard=std["label"], status=status, score=score,
        recommendations=recommendations, upgrade_options=upgrade_options, notes=notes,
    )


# ---------------------------------------------------------------------------
# システム健全性分析
# ---------------------------------------------------------------------------

def analyze_system_health(specs: PCSpecs) -> ComponentScore:
    """TRIM・電源プラン・スタートアップ数・Windows Update を評価する"""
    recommendations: list[str] = []
    score = 100

    if not specs.trim_enabled:
        recommendations.append(
            "TRIM が無効です。SSD の書き込み性能が低下します。"
            "「fsutil behavior set DisableDeleteNotify 0」で有効化を推奨します。"
        )
        score -= 20

    if specs.power_plan:
        plan_l = specs.power_plan.lower()
        if "power saver" in plan_l or "省電力" in plan_l:
            recommendations.append(
                f"電源プランが「{specs.power_plan}」です。"
                "「バランス」または「高パフォーマンス」への変更でパフォーマンスが向上します。"
            )
            score -= 15

    if specs.startup_app_count > 20:
        recommendations.append(
            f"スタートアップアプリが {specs.startup_app_count} 個登録されています。"
            "不要なアプリを無効にすることで起動時間と常駐メモリが改善します。"
        )
        score -= 15
    elif specs.startup_app_count > 10:
        recommendations.append(
            f"スタートアップアプリが {specs.startup_app_count} 個あります。"
            "不要なものを無効化すると起動が速くなります。"
        )
        score -= 5

    if specs.last_windows_update:
        try:
            from datetime import date
            last = date.fromisoformat(specs.last_windows_update)
            delta = (date.today() - last).days
            if delta > 180:
                recommendations.append(
                    f"最終 Windows Update から {delta} 日経過しています。"
                    "セキュリティのため更新を確認してください。"
                )
                score -= 20
            elif delta > 90:
                recommendations.append(
                    f"最終 Windows Update から {delta} 日経過しています。更新を確認してください。"
                )
                score -= 10
        except ValueError:
            pass

    score = max(0, score)
    status = _status_from_score(score)

    parts: list[str] = []
    parts.append(f"TRIM: {'有効' if specs.trim_enabled else '無効'}")
    if specs.power_plan:
        parts.append(f"電源: {specs.power_plan}")
    parts.append(f"スタートアップ: {specs.startup_app_count} 個")
    if specs.last_windows_update:
        parts.append(f"最終更新: {specs.last_windows_update}")
    current_val = " / ".join(parts)

    if score >= 80:
        notes = "システム設定は最適化されています。"
    elif score >= 60:
        notes = "一部の設定を見直すとパフォーマンスが向上します。"
    else:
        notes = "システム設定の最適化でコスト0円のパフォーマンス改善が期待できます。"

    return ComponentScore(
        name="システム健全性", current_value=current_val,
        midrange_standard="TRIM有効 / バランス以上 / スタートアップ10個以下",
        status=status, score=score,
        recommendations=recommendations, upgrade_options=[], notes=notes,
    )


# ---------------------------------------------------------------------------
# PSU 容量分析
# ---------------------------------------------------------------------------

def analyze_psu(specs: PCSpecs) -> ComponentScore:
    """推定消費電力と推奨 PSU 容量を評価する"""
    estimated = specs.psu_estimated_tdp_w
    recommended = specs.psu_recommended_w

    parts = [f"推定消費電力: {estimated}W", f"推奨PSU容量: {recommended}W 以上"]
    current_val = " / ".join(parts)

    # 推奨容量に応じて 80Plus グレードを提案
    if recommended >= 750:
        grade_note = "80Plus Gold 以上を推奨（効率・静音性が向上）"
    elif recommended >= 550:
        grade_note = "80Plus Bronze 以上を推奨"
    else:
        grade_note = "80Plus Bronze 対応モデルで十分"

    recommendations: list[str] = [
        f"CPU ({specs.cpu_name}) + GPU ({specs.gpu_name or 'なし'}) の合計 TDP から"
        f" 推定消費電力 {estimated}W を算出しました。",
        f"余裕を持たせた推奨 PSU 容量は {recommended}W です（{grade_note}）。",
        "※ この推定値はあくまで目安です。実際のシステム構成に合わせて検討してください。",
    ]

    return ComponentScore(
        name="PSU 容量推定", current_value=current_val,
        midrange_standard="推定消費電力の1.5倍を目安",
        status="meets", score=70,
        recommendations=recommendations, upgrade_options=[], notes=grade_note,
    )


# ---------------------------------------------------------------------------
# 総合評価
# ---------------------------------------------------------------------------

def calculate_overall(core_scores: list[ComponentScore]) -> dict:
    """コア4種（CPU/RAM/GPU/Storage）で総合評価を算出する"""
    weights = {"CPU": 0.3, "RAM": 0.2, "GPU": 0.35, "ストレージ": 0.15}
    total   = sum(s.score * weights.get(s.name, 0.25) for s in core_scores)
    overall = int(total)

    if overall >= 80:
        grade, label = "A", "ハイスペック"
        message = "この基準を大きく上回っています。現状のPCで快適な作業が可能です。"
    elif overall >= 60:
        grade, label = "B", "基準クリア"
        message = "この基準を概ね満たしています。一部のコンポーネントを改善するとより快適になります。"
    elif overall >= 40:
        grade, label = "C", "基準以下"
        message = "いくつかのコンポーネントがこの基準を下回っています。優先度の高い箇所からアップグレードを検討しましょう。"
    else:
        grade, label = "D", "大幅に基準以下"
        message = "この基準に達するには複数のコンポーネントのアップグレードが必要です。"

    priority = sorted(
        [s for s in core_scores if s.status == "below"],
        key=lambda x: x.score,
    )

    return {
        "score": overall, "grade": grade, "label": label,
        "message": message,
        "priority_upgrades": [s.name for s in priority],
    }


# ---------------------------------------------------------------------------
# ノートPC向けの提案制約
# ---------------------------------------------------------------------------

# ノートPCに増設可能なUSB接続ネットワークアダプタ
LAPTOP_NETWORK_WIRED_OPTIONS = [
    {"name": "TP-Link UE300 (USB 3.0 Gigabit)", "price": "約 ¥1,500〜",
     "note": "USB接続・ノートPCでもGigabit化"},
]
LAPTOP_NETWORK_WIFI_OPTIONS = [
    {"name": "TP-Link Archer TX20U Plus (USB Wi-Fi 6)", "price": "約 ¥4,000〜",
     "note": "USB接続・ノートPCでも増設可能"},
]


def _apply_laptop_constraints(scores: list[ComponentScore]) -> None:
    """ノートPCで物理的に交換できないパーツの提案を抑制・差し替えする

    対象: GPU増設・マザーボード交換は不可。PCIe接続のネットワークカードは
    USB接続品に差し替え。ストレージ換装は可能だが機種依存の注意を付す。
    """
    for s in scores:
        if s.name == "GPU":
            s.upgrade_options = []
            if s.status == "below":
                s.recommendations = [
                    "ノートPCのGPUは交換できません。GPU性能が必要な場合は、"
                    "外付けGPU(eGPU)対応機種の確認、または買い替えをご検討ください。"
                ]
        elif s.name == "マザーボード":
            s.upgrade_options = []
            if s.status == "below":
                s.recommendations = [
                    "ノートPCのマザーボード(プラットフォーム)は交換できません。"
                    "世代が古い場合は買い替えが現実的な選択肢です。"
                ]
        elif s.name == "ネットワーク":
            if s.upgrade_options:
                replaced: list[dict] = []
                if any("有線" in r for r in s.recommendations):
                    replaced.extend(LAPTOP_NETWORK_WIRED_OPTIONS)
                if any("Wi-Fi" in r for r in s.recommendations):
                    replaced.extend(LAPTOP_NETWORK_WIFI_OPTIONS)
                s.upgrade_options = replaced
        elif s.name == "ストレージ":
            if s.upgrade_options:
                s.recommendations.append(
                    "※ ノートPCの換装可否(M.2スロットの有無・サイズ)は機種により異なります。"
                )


def _apply_desktop_notes(scores: list[ComponentScore]) -> None:
    """デスクトップPC向けの注意書きを付す

    スリム型・省スペース筐体(メーカー製に多い)はWMIから判別できないため、
    GPU増設の提案には物理サイズ・電源容量の確認を促す注記を常に添える。
    """
    for s in scores:
        if s.name == "GPU" and s.upgrade_options:
            s.recommendations.append(
                "※ スリム型・省スペース筐体ではカードサイズ(ロープロファイル対応)と"
                "電源容量をご確認ください。"
            )


# ---------------------------------------------------------------------------
# 買い替え vs アップグレード判定
# ---------------------------------------------------------------------------

# 買い替え提案時に楽天で検索するBTO PCのキーワードと価格帯(プロファイル別)
BTO_SUGGESTIONS: dict[str, dict] = {
    "low": {
        "keyword": "デスクトップパソコン 新品 Ryzen 16GB SSD",
        "ref_price": 80000,
        "label": "普段使い向けの新品デスクトップPC",
    },
    "mid": {
        "keyword": "ゲーミングPC RTX 5060 搭載 新品",
        "ref_price": 200000,
        "label": "RTX 5060クラス搭載のゲーミングPC",
    },
    "high": {
        "keyword": "ゲーミングPC RTX 5070 搭載 新品",
        "ref_price": 300000,
        "label": "RTX 5070クラス搭載のハイエンドゲーミングPC",
    },
}

# ノートPC向けの買い替え候補キーワード
BTO_SUGGESTIONS_LAPTOP: dict[str, dict] = {
    "low": {
        "keyword": "ノートパソコン 新品 16GB SSD",
        "ref_price": 90000,
        "label": "普段使い向けの新品ノートPC",
    },
    "mid": {
        "keyword": "ゲーミングノートPC RTX 5060 新品",
        "ref_price": 200000,
        "label": "RTX 5060クラス搭載のゲーミングノートPC",
    },
    "high": {
        "keyword": "ゲーミングノートPC RTX 5070 新品",
        "ref_price": 320000,
        "label": "RTX 5070クラス搭載のハイエンドゲーミングノートPC",
    },
}


def judge_replacement(profile_key: str, core_scores: list[ComponentScore],
                      mb_score: ComponentScore, is_laptop: bool = False) -> dict:
    """部分アップグレードで延命するか、買い替えるべきかを判定する

    考え方: CPU・マザーボード(プラットフォーム)の交換が必要になると、
    RAM・場合によってはストレージも巻き込む「総とっかえ」になり、
    部分アップグレードの価格優位性が消えるため、買い替えと比較すべき。
    """
    below = [s.name for s in core_scores if s.status == "below"]
    platform_old = mb_score.status == "below"
    cpu_below = any(s.name == "CPU" and s.status == "below" for s in core_scores)
    gpu_below = any(s.name == "GPU" and s.status == "below" for s in core_scores)

    reasons: list[str] = []
    if platform_old:
        reasons.append("マザーボード(プラットフォーム)がこの基準の世代要件を下回っています。"
                       "CPU交換にはマザーボード・RAMの同時交換が必要になる可能性が高いです。")
    if below:
        reasons.append(f"基準以下のコアコンポーネントが {len(below)} 種あります"
                       f"({'・'.join(below)})。")

    if is_laptop and (cpu_below or gpu_below):
        # ノートPCはCPU・GPUを交換できないため、不足していれば買い替え一択に近い
        reasons.append("ノートPCはCPU・GPU・マザーボードを交換できないため、"
                       "パーツ交換で改善できる余地が限られます。")
        if len(below) >= 2:
            verdict = "replace"
            summary = ("ノートPCでは交換できないコンポーネントが基準を下回っています。"
                       "性能を改善するには買い替えが現実的です。")
        else:
            verdict = "consider"
            summary = ("ノートPCのため交換による改善余地が限られます。"
                       "用途に支障がある場合は買い替えをご検討ください。")
    elif platform_old and (len(below) >= 3 or (cpu_below and len(below) >= 2)):
        verdict = "replace"
        summary = ("プラットフォーム一新を含む大規模な交換が必要なため、"
                   "パーツ単位の延命より新しいPCへの買い替えのほうが割安になる可能性が高いです。")
    elif platform_old and len(below) >= 1:
        verdict = "consider"
        summary = ("アップグレードは可能ですが、プラットフォームが古いため"
                   "投資効果が限定的です。買い替えとの価格比較をおすすめします。")
    elif len(below) >= 3:
        verdict = "consider"
        summary = ("複数のパーツ交換が必要です。合計費用によっては"
                   "買い替えのほうが効率的な場合があります。")
    else:
        verdict = "upgrade"
        summary = ("不足しているパーツの交換だけで十分に改善できます。"
                   "部分アップグレードでの延命がおすすめです。")
        if not below:
            reasons = ["コアコンポーネントはこの基準を満たしています。"]

    bto_table = BTO_SUGGESTIONS_LAPTOP if is_laptop else BTO_SUGGESTIONS
    return {
        "verdict": verdict,            # "upgrade" | "consider" | "replace"
        "summary": summary,
        "reasons": reasons,
        "bto": bto_table.get(profile_key),
    }


# ---------------------------------------------------------------------------
# エントリーポイント
# ---------------------------------------------------------------------------

def _score_to_dict(s: ComponentScore) -> dict:
    return {
        "name": s.name, "current_value": s.current_value,
        "midrange_standard": s.midrange_standard, "status": s.status, "score": s.score,
        "recommendations": s.recommendations, "upgrade_options": s.upgrade_options,
        "notes": s.notes,
    }


def run_analysis() -> dict:
    """全コンポーネントを全プロファイルで分析して結果を返す"""
    specs = collect_specs()  # WMI は1回だけ実行

    # プロファイル非依存の分析（1回だけ実行）
    system_health_score = analyze_system_health(specs)
    psu_score           = analyze_psu(specs)

    profiles_result: dict[str, dict] = {}
    for key, profile in PROFILES.items():
        core_scores = [
            analyze_cpu(specs, profile),
            analyze_ram(specs, profile),
            analyze_gpu(specs, profile),
            analyze_storage(specs, profile),
        ]
        mb_score = analyze_motherboard(specs, profile)
        extra_scores = [
            analyze_display(specs, profile),
            analyze_network(specs, profile),
            mb_score,
            analyze_ai_accelerator(specs, profile),
            system_health_score,
        ]
        # ノートPCでは電源ユニットの交換概念がないためPSUカードは出さない
        if not specs.is_laptop:
            extra_scores.append(psu_score)

        if specs.is_laptop:
            _apply_laptop_constraints(core_scores + extra_scores)
        else:
            _apply_desktop_notes(core_scores + extra_scores)

        profiles_result[key] = {
            "label":       profile["label"],
            "description": profile["description"],
            "scores":      [_score_to_dict(s) for s in core_scores + extra_scores],
            "overall":     calculate_overall(core_scores),
            "replacement": judge_replacement(key, core_scores, mb_score, specs.is_laptop),
        }

    return {
        "specs": {
            "cpu_name":              specs.cpu_name,
            "cpu_cores":             specs.cpu_cores,
            "cpu_threads":           specs.cpu_threads,
            "cpu_base_ghz":          specs.cpu_base_ghz,
            "cpu_max_ghz":           specs.cpu_max_ghz,
            "ram_total_gb":          specs.ram_total_gb,
            "ram_available_gb":      specs.ram_available_gb,
            "ram_type":              specs.ram_type,
            "ram_slots_used":        specs.ram_slots_used,
            "ram_slots_total":       specs.ram_slots_total,
            "gpu_name":              specs.gpu_name,
            "gpu_vram_gb":           specs.gpu_vram_gb,
            "gpu_driver":            specs.gpu_driver,
            "storage_list":          specs.storage_list,
            "display_width":         specs.display_width,
            "display_height":        specs.display_height,
            "display_refresh_hz":    specs.display_refresh_hz,
            "display_name":          specs.display_name,
            "network_wired_mbps":    specs.network_wired_mbps,
            "network_wired_name":    specs.network_wired_name,
            "network_wifi_standard": specs.network_wifi_standard,
            "network_wifi_name":     specs.network_wifi_name,
            "os_name":               specs.os_name,
            "os_version":            specs.os_version,
            "motherboard":           specs.motherboard,
            "mb_chipset":            specs.mb_chipset,
            # AI アクセラレータ
            "ai_npu_name":           specs.ai_npu_name,
            "ai_npu_tops":           specs.ai_npu_tops,
            "ai_external_devices":   specs.ai_external_devices,
            "ai_gpu_tensor_cores":   specs.ai_gpu_tensor_cores,
            "ai_gpu_tensor_tops":    specs.ai_gpu_tensor_tops,
            "ai_total_tops":         specs.ai_total_tops,
            # システム健全性
            "trim_enabled":          specs.trim_enabled,
            "power_plan":            specs.power_plan,
            "startup_app_count":     specs.startup_app_count,
            "last_windows_update":   specs.last_windows_update,
            # PSU 推定
            "psu_estimated_tdp_w":   specs.psu_estimated_tdp_w,
            "psu_recommended_w":     specs.psu_recommended_w,
            # 筐体タイプ
            "is_laptop":             specs.is_laptop,
        },
        "profiles":        profiles_result,
        "default_profile": DEFAULT_PROFILE,
    }
