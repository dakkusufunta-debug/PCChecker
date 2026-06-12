拡張機能の実装案
ご要望の2機能と、関連する追加機能の優先度別の立案です。

A. AIアクセラレータ分析（TPU/NPU/Tensor Core）
「TPU」は厳密には Google の AI 専用ASICですが、最近のPC環境では AI推論アクセラレータ 全般を指すことが多いため、以下を統合的に検出する設計を提案します。

検出対象と方法
種類	例	検出方法
CPU内蔵 NPU	Intel AI Boost (Core Ultra)、AMD Ryzen AI (XDNA)	Win32_PnPEntity で *AI Boost*, *IPU*, *Neural*, *XDNA* を検索
外付け TPU	Google Coral USB / M.2 / PCIe	Win32_PnPEntity で VID 1A6E（Google）/ 03E7（Intel Movidius）
GPU の Tensor Core	NVIDIA RTX 20/30/40/50 シリーズ	GPU 名から判定（RTX シリーズ全機種に Tensor Core あり）
Hailo-8 等	Hailo-8 PCIe AI アクセラレータ	PCI デバイスID から検出
データ構造への追加

@dataclass
class PCSpecs:
    ...
    # AI アクセラレータ
    ai_npu_name: str = ""           # "Intel AI Boost", "AMD Ryzen AI" など
    ai_npu_tops: float = 0.0        # 性能 (TOPS)
    ai_external_devices: list[dict] = field(default_factory=list)
                                     # [{"name": "Coral USB Accelerator", "tops": 4}, ...]
    ai_gpu_tensor_cores: bool = False
    ai_gpu_tensor_tops: float = 0.0  # GPU 名→TOPSテーブル（RTX 4070=466 等）
    ai_total_tops: float = 0.0       # 合算
TOPS 推定テーブル例

NPU_TOPS = {
    "Intel AI Boost": 11.0,         # Core Ultra (Meteor Lake)
    "Intel AI Boost (Lunar Lake)": 48.0,
    "AMD Ryzen AI": 16.0,           # Ryzen 7040/8040
    "AMD Ryzen AI (Strix)": 50.0,
}
GPU_TENSOR_TOPS = {
    "RTX 4090": 1321, "RTX 4080": 780, "RTX 4070 Ti SUPER": 706,
    "RTX 4070": 466, "RTX 4060 Ti": 353, "RTX 4060": 242,
    "RTX 3090": 285, "RTX 3080": 238, "RTX 3070": 163,
    # ...
}
EXTERNAL_TPU_TOPS = {
    "Coral USB": 4, "Coral M.2": 4, "Hailo-8": 26,
}
プロファイル基準への追加

"ai_accelerator": {
    "low":  {"min_tops": 0,    "label": "AI機能なし可"},
    "mid":  {"min_tops": 50,   "label": "NPU内蔵またはRTX 4060以上"},
    "high": {"min_tops": 200,  "label": "RTX 4070+ または NPU+TPU構成"},
}
提案するアップグレードパーツ
low/mid: Coral USB Accelerator (約 ¥9,000)
mid: Intel Core Ultra 7 / Ryzen AI 9（CPU 自体のアップグレード）
high: NVIDIA RTX 4070 Ti SUPER, Hailo-8 PCIe カード
実装難易度
中：NPUとTPUのVID/PIDマッピングテーブルが必要。GPU名→TOPSテーブルは公式仕様書ベース。

B. ストレージ寿命・健全性監視
検出方法（3レベル）
レベル	取得手段	取得情報	追加依存
L1: 基本	MSFT_PhysicalDisk.HealthStatus	Healthy / Warning / Unhealthy	なし（既存WMI）
L2: 中	PowerShell Get-StorageReliabilityCounter	摩耗度(Wear)、Power-On Hours、温度、読書エラー回数	なし（subprocess）
L3: 詳細	smartctl (smartmontools)	SMART全項目、TBW、寿命予測	smartmontools のインストールが必要
L2 推奨実装（追加依存ゼロ）

import subprocess, json

def get_storage_health() -> list[dict]:
    """PowerShell経由でストレージ健全性情報を取得"""
    cmd = ["powershell", "-NoProfile", "-Command",
           "Get-PhysicalDisk | Get-StorageReliabilityCounter | "
           "Select-Object DeviceId, Wear, PowerOnHours, Temperature, "
           "ReadErrorsTotal, WriteErrorsTotal | ConvertTo-Json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return json.loads(result.stdout) if result.stdout else []
データ構造

# storage_list の各エントリに追加
{
    "model": ..., "size_gb": ..., ...,
    # 健全性情報（追加）
    "health_status": "Healthy",      # Healthy / Warning / Unhealthy / Unknown
    "wear_percent": 5,                # 摩耗度 0-100 (SSDのみ)
    "power_on_hours": 12500,          # 通電時間
    "temperature_c": 42,              # 温度（℃）
    "read_errors": 0, "write_errors": 0,
    "estimated_life_remaining_pct": 95,  # 推定寿命残量
    "warning_level": "ok",            # ok / caution / warning / critical
}
評価ロジック

def evaluate_storage_health(disk: dict) -> tuple[str, list[str]]:
    """警告レベルとメッセージを返す"""
    warnings = []
    level = "ok"

    # 摩耗度
    if disk.get("wear_percent", 0) >= 90:
        level = "critical"
        warnings.append(f"摩耗度 {disk['wear_percent']}% - 早急な交換を推奨します。")
    elif disk.get("wear_percent", 0) >= 70:
        level = "warning"
        warnings.append(f"摩耗度 {disk['wear_percent']}% - 重要データのバックアップを推奨。")

    # 温度
    if disk.get("temperature_c", 0) >= 70:
        level = max(level, "warning", key=["ok","caution","warning","critical"].index)
        warnings.append(f"温度 {disk['temperature_c']}℃ - 冷却強化を推奨します。")

    # 通電時間（一般的SSD寿命: 5万時間目安）
    poh = disk.get("power_on_hours", 0)
    if poh >= 40000:
        warnings.append(f"通電時間 {poh:,}時間 - 経年的な交換時期に近づいています。")

    # エラー数
    err = disk.get("read_errors", 0) + disk.get("write_errors", 0)
    if err > 100:
        level = "critical"
        warnings.append(f"読書エラー {err}回 - ディスク障害の兆候があります。")

    return level, warnings
UI 表示
ストレージカードに「健康状態バッジ」を追加：

🟢 良好 (ok)
🟡 注意 (caution / warning)
🔴 警告 (critical)
詳細モーダルに摩耗度バー、温度、通電時間、推定残り寿命を表示。

実装難易度
中：PowerShell の Get-StorageReliabilityCounter が安定しており、subprocess で十分。NVMe の TBW 取得は smartmontools が必要なため Phase 2 とする。

C. その他のおすすめ機能（優先度別）
優先度 ★★★（実用価値が高く実装が現実的）
C-1. システム健全性チェック
ストレージ寿命と並列で実装すると効果的。

TRIM 有効/無効（SSD用）: fsutil behavior query DisableDeleteNotify
電源プラン: Win32_PowerPlan から「高パフォーマンス」「バランス」判定
Windows Update 状況: Win32_QuickFixEngineering の最新適用日
スタートアップアプリ数: レジストリの Run キー数 + パフォーマンス影響評価
ページファイル設定: Win32_PageFileUsage
BIOS バージョン年代（既存 bios_version を活用、メーカーDB照合）
→ 「システム最適化スコア」 として独立カードで表示。

→ コスト 0 円のアップグレード手段として価値が高い。

C-2. リアルタイムモニタリング（軽量版）
分析画面とは別に「モニター」タブを追加。

CPU/RAM/ディスク使用率の折れ線グラフ（過去30秒）
ネットワーク送受信速度
必要技術: psutil + WebSocket（FastAPI標準対応）
データ更新は1秒間隔程度で軽量
C-3. 電源ユニット (PSU) 容量推定
CPU TDP テーブル + GPU TDP テーブル + その他 100W で推定消費電力を算出
推定値の 1.5倍 を推奨 PSU 容量として提案
80Plus 認証ランクの推奨（Bronze / Gold / Platinum）
ユーザー入力欄: 現在のPSU容量を入力すると余裕度判定
→ ハードウェア追加なしで実装可能、配線時の判断材料になる。

優先度 ★★（実装価値はあるが工数大）
C-4. 用途別評価モード
既存 PROFILES の "汎用基準" に加え、用途別の重み付けを追加：

🎮 ゲーム: GPU 0.50, CPU 0.20, RAM 0.15, Storage 0.10, Display 0.05
🎬 動画編集: CPU 0.30, GPU 0.25, RAM 0.25, Storage 0.20
🤖 AI/ML: GPU 0.45, RAM 0.25, CPU 0.20, Storage 0.10
📺 配信: CPU 0.35, GPU 0.30, Network 0.15, RAM 0.20
💼 オフィス: CPU 0.30, RAM 0.30, Display 0.20, Storage 0.20
UI: プロファイル切替タブと並列に「用途タブ」を追加（2軸選択）。

C-5. アップグレード予算プランナー
入力: 「予算 ¥50,000」「目標プロファイル: ハイ」
出力: ROI（投資効果）の高い順にパーツリスト
例:「RAM 16→32GB ¥10,000 で総合スコア +8」
例:「Storage HDD→NVMe ¥12,000 で総合スコア +15」
段階的アップグレードプラン提示
C-6. 構成相性チェック
CPU ソケット ↔ マザーボードチップセット
RAM 規格 (DDR4/DDR5) ↔ マザーボード対応
GPU 長 ↔ ケースサイズ（要ユーザー入力）
PSU 容量 ↔ 構成消費電力
優先度 ★（あれば嬉しい）
C-7. レポート出力
Markdown / PDF / JSON 形式でエクスポート
パーツショップ持参用「アップグレード相談シート」
C-8. 履歴・比較機能
ローカルJSONに分析結果を保存
「3ヶ月前と比較」モード
スコア推移グラフ
C-9. パーツ詳細リンク
アップグレード候補に Amazon / 価格.com の検索URLボタン
注意: アフィリエイトリンクではない、検索結果へのジャンプのみ
C-10. 異常検知・通知
CPU 温度 90℃以上の警告
メモリ使用率の常時 90%超
ストレージ残量 5%以下 → デスクトップ通知（win10toast）
推奨実装順序

Phase A: 要望対応（最優先）
  1. AIアクセラレータ分析（TPU/NPU/Tensor Core）
  2. ストレージ寿命・健全性監視（L2レベル）

Phase B: 補完強化（実装容易・効果大）
  3. システム健全性チェック（TRIM、電源プラン、スタートアップ等）
  4. PSU 容量推定

Phase C: UX 拡張
  5. 用途別評価モード
  6. リアルタイムモニタリング
  7. アップグレード予算プランナー

Phase D: ポリッシュ
  8. レポート出力
  9. 履歴比較
  10. パーツ詳細リンク
実装担当モデルへの引き継ぎ用メモ
共通の追加依存
subprocess / json (標準ライブラリのみで OK)
拡張時のみ: smartmontools (Phase A の L3)、win10toast (C-10)
設計の継承ポイント
PROFILES 構造をそのまま流用: AIアクセラレータも standards["ai_accelerator"] と upgrade_options["ai_accelerator"] に追加
ストレージ健全性は既存 storage_list の各エントリを拡張: 別カードを増やすか既存に統合かは UI 検討事項
テスト: WMI/PowerShell 呼び出しは pure 関数化してフィクスチャでテスト可能に
実装担当への注意点
TOPS テーブルは公式仕様書ベースで作る（出典明記）
PowerShell 呼び出しは Windows 限定 → 既存の WMI/winreg と同じ前提でOK
健全性スコアはあくまで 目安 として表示（メーカー保証ではない旨を注記）
優先度 ★★★ から順に実装担当に渡すと、最小工数で最大の機能追加になります。