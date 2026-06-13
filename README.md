# PCChecker

お使いのWindows PCのスペックを自動診断し、用途に合わせたアップグレードパーツを提案するデスクトップアプリです。

## 特徴

- **ワンクリック診断** — CPU / RAM / GPU / ストレージ / ディスプレイ / ネットワーク / マザーボードを自動収集し、0〜100点でスコアリング
- **3段階のプロファイル** — ロースペック(コスパ重視)/ ミドルスペック(汎用)/ ハイスペック(クリエイター・ゲーマー向け)を切り替えて評価
- **具体的なアップグレード提案** — 不足しているパーツに対して、価格目安付きの候補を提示
- **AIアクセラレータ分析** — NPU / GPU Tensor Core / 外付けTPUを検出し、合計TOPSを算出
- **ストレージ健全性チェック** — 摩耗度・温度・通電時間から警告レベルを表示
- **システム健全性チェック** — TRIM設定・電源プラン・スタートアップアプリ数などを確認
- **PSU容量推定** — 構成から推定消費電力と推奨電源容量を算出

スペック情報はすべてお使いのPC上でローカルに収集され、外部には送信されません。

## 動作環境

- Windows 10 / 11
- Python 3.11+

## セットアップ

```powershell
pip install -r requirements.txt
python main.py
```

ブラウザが自動で開きます(http://localhost:8000)。

## 開発

```powershell
pip install -r requirements-dev.txt
python -m pytest tests -q
```

## exe ビルド(配布用)

単一ファイルの Windows 実行ファイル(ウィンドウなし・起動するとブラウザが自動で開く)を生成します。

```powershell
pip install -r requirements-dev.txt
python scripts/make_icon.py              # static/icon.ico を生成
python -m PyInstaller PCChecker.spec --noconfirm
```

出力: `dist/PCChecker.exe`

- ビルド定義は `PCChecker.spec`、アイコンは `static/icon.ico`。
- exe 実行時のログは `%LOCALAPPDATA%\PCChecker\pcchecker.log`。
- 楽天価格連携を使う場合は `.env`(`.env.example` 参照)を exe と同じフォルダに置きます。秘密鍵を含むため配布物には同梱しないでください。

## 免責事項

本アプリの診断結果・推定値(ストレージ寿命、PSU容量、パーツ価格など)はあくまで目安であり、動作や寿命を保証するものではありません。パーツの購入・交換はご自身の責任で行ってください。
