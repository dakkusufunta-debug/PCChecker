# Microsoft Store 提出手順

PCChecker を Microsoft Store に提出するための MSIX パッケージ作成手順です。

> **進捗(2026-06-20時点 / v1.0.1)**: 手順1〜4は完了済み。Partner Center の個人開発者登録・アプリ名予約(Store ID `9PJ0X9T3PDGL` / PFN `Mirato.PCChecker_n9bj028cvzf5c`)・`packaging/AppxManifest.xml` への実値反映・MSIXビルド(`dist/msix/PCChecker.msix`)まで済んでいる。**2026-06-20に以下のビルド検証を完了。残りは手順6(Partner Centerへのアップロード・審査提出)のみ。**
>
> ### ビルド検証記録 (2026-06-20 / commit a064c47)
>
> | 項目 | 値 |
> |---|---|
> | バージョン | 1.0.1 (Manifest: `1.0.1.0`) |
> | commit | `a064c47` |
> | テスト | 273 passed |
> | ファイル | `dist/msix/PCChecker.msix` |
> | サイズ | 18,039,948 bytes |
> | SHA-256 | `6C53E3BEAA81D1ADC147AFA49E99C305B5673941BDD60886982C836757321AD6` |
> | パッケージ内容 | `.env`・秘密鍵なし 確認済み |
> | 直接 exe スモーク | `dist/PCChecker.exe` 起動 → `http://127.0.0.1:8000/` が HTTP 200・PCChecker 画面を返した |
>
> **サイドロード確認の注意事項**: 自己署名証明書を **CurrentUser Root** ストアへ追加するのは避けること（システム全体の信頼チェーンを緩める可能性があるため）。CurrentUser TrustedPeople への追加では `0x800B0109` エラーが発生するが、これは想定内の動作。安全な次の検証ステップは Partner Center へアップロードし、Microsoft の再署名・審査フローで確認することを推奨する。

## 1. Partner Center に登録する

Microsoft Partner Center で **個人(Individual)** 開発者アカウントを登録します（ソロ開発では個人で十分。法人より安く本人確認も簡素）。

- **費用**: 登録は一度きりの登録料（個人アカウントで約 $19 USD 相当。為替により ¥2,000〜3,000 程度。最新額は登録ページで要確認）。年額ではなく買い切り。
- **本人確認**: 氏名・住所・連絡先。個人アカウントは法人(D-U-N-S番号等)より手続きが軽い。確認完了まで数日かかる場合がある。
- **支払い/税務プロファイルは今回スキップ可**: PCChecker は **無料アプリ**で、収益は楽天アフィリエイト（Store外）で得る。Store からの売上分配は受け取らないため、**銀行口座・税務(W-8/W-9等)プロファイルの登録は不要**。登録で最も手間のかかる部分を省ける。将来 Store 内課金を入れる場合のみ設定する。

## 2. アプリ名を予約する

Partner Center で「新しいアプリ」を作成し、Store 表示名として `PCChecker` を予約します。

- 名前予約はアカウント登録さえ済めば**パッケージ未完成でも今すぐ無料で行える**（早い者勝ちなので先に押さえると良い）。
- 予約後、`製品 > 製品管理 > 製品ID` で Store 提出に必要なパッケージ ID 情報を取得できる（次節で manifest に反映）。

## 3. Manifest の TODO を差し替える

`packaging/AppxManifest.xml` の次の値を Partner Center の表示に合わせて差し替えます。

- `Identity/@Name`: Partner Center の Package/Identity Name
- `Identity/@Publisher`: Partner Center の Publisher
- `Identity/@Version`: 提出するパッケージバージョン。例: `1.0.0.0`
- `Properties/PublisherDisplayName`: Partner Center の Publisher display name

Store 予約アプリ名は `DisplayName=PCChecker` として設定済みです。予約名を変更した場合は `DisplayName` も合わせて更新してください。

## 4. MSIX をビルドする

Windows SDK をインストールして、`makeappx.exe` と `signtool.exe` が利用できる状態にします。PATH に無い場合でも、スクリプトは標準的な SDK パス `C:\Program Files (x86)\Windows Kits\10\bin\*\x64` から自動探索します。

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_msix.ps1
```

出力先は `dist\msix\PCChecker.msix` です。既存の `dist\PCChecker.exe` を使う場合は `-SkipPyInstaller` を指定します。

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_msix.ps1 -SkipPyInstaller
```

## 5. 自己署名でサイドロード確認する

Store 提出時は Microsoft が再署名します。自己署名証明書はローカルのサイドロード動作確認専用です。

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_msix.ps1 -Sign -InstallCertificate
```

`-InstallCertificate` は作成した証明書を CurrentUser の Trusted People に追加します。署名済み MSIX は Windows のアプリインストーラー、または PowerShell の `Add-AppxPackage` で検証できます。

```powershell
Add-AppxPackage .\dist\msix\PCChecker.msix
```

## 6. Partner Center にアップロードする

Partner Center の対象アプリでパッケージ提出画面を開き、`dist\msix\PCChecker.msix` をアップロードして審査へ進みます。価格、年齢区分、プライバシー、スクリーンショット、説明文も Store 側で設定します。

## 審査上の注意

- PCChecker はローカルで FastAPI/uvicorn の Web サーバを起動し、既定ブラウザを開きます。Store 説明文や審査メモで、診断 UI をローカルブラウザで表示するデスクトップアプリであることを明記してください。
- WMI やローカルシステム情報の取得、ブラウザ起動、同梱 exe の通常起動が必要なため、Manifest は `EntryPoint=Windows.FullTrustApplication` + `runFullTrust` capability を使う Desktop Bridge 構成です（純 Win32 アプリのため `windows.fullTrustProcess` 拡張は不要）。審査メモでは、PC スペック診断をローカルで完結させるためのフルトラスト権限であることを説明してください。
- `.env` は秘密鍵を含むため MSIX に同梱しません。楽天 API キーが無い環境でも、価格表示は同梱済みキャッシュやフォールバック表示で動作することを事前に確認してください。
- PyInstaller の onefile 形式は、MSIX 内から起動しても実行時に毎回一時ディレクトリへ展開されるため、起動が遅くなる可能性があります。Store 版の起動時間が問題になる場合は、将来的に `PCChecker.spec` を onedir 形式へ変更することを検討してください。
