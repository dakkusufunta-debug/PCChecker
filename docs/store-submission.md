# Microsoft Store 提出手順

PCカスタムサポート を Microsoft Store に提出するための MSIX パッケージ作成手順です。

> **進捗メモ**: 2026-06-25 に Microsoft Partner Center の Product Identity を確認し、既存Store製品の固定IDに合わせて新名称MSIXを再作成しました。Store上の表示名、実行ファイル名、MSIXファイル名は `PCカスタムサポート` / `PCCustomSupport` へ変更済みです。既存製品更新として受理させるため、`Package/Identity/Name` と PFN は Partner Center 指定値を維持します。
>
> ### ビルド検証記録 (2026-06-25 / base commit 785feb4 + local changes)
>
> | 項目 | 値 |
> |---|---|
> | バージョン | 1.0.2 (Manifest: `1.0.2.0`) |
> | Store固定ID | `Mirato.PCChecker` |
> | PFN | `Mirato.PCChecker_n9bj028cvzf5c` |
> | Publisher | `CN=3F06A858-7418-4AB5-A1BD-FD856E9B75B0` |
> | アプリID | `PCCustomSupport` |
> | 実行ファイル | `PCCustomSupport.exe` |
> | 表示名 | `PCカスタムサポート` |
> | テスト | `python -m pytest tests -q` で確認する |
> | ファイル | `dist/msix/PCCustomSupport.msix` |
> | サイズ | 18,040,069 bytes |
> | SHA-256 | `4601684D0CB72F74E68E77B7B58D94A5A0B29056C206723A39F3F647A4B5C531` |
> | パッケージ内容 | `.env`・秘密鍵なし 確認済み |
> | MSIX展開確認 | `makeappx unpack` で `AppxManifest.xml` を確認済み |
>
> **サイドロード確認の注意事項**: 自己署名証明書を **CurrentUser Root** ストアへ追加するのは避けること（システム全体の信頼チェーンを緩める可能性があるため）。CurrentUser TrustedPeople への追加では `0x800B0109` エラーが発生するが、これは想定内の動作。安全な次の検証ステップは Partner Center へアップロードし、Microsoft の再署名・審査フローで確認することを推奨する。

## 1. Partner Center に登録する

Microsoft Partner Center で **個人(Individual)** 開発者アカウントを登録します（ソロ開発では個人で十分。法人より安く本人確認も簡素）。

- **費用**: 登録は一度きりの登録料（個人アカウントで約 $19 USD 相当。為替により ¥2,000〜3,000 程度。最新額は登録ページで要確認）。年額ではなく買い切り。
- **本人確認**: 氏名・住所・連絡先。個人アカウントは法人(D-U-N-S番号等)より手続きが軽い。確認完了まで数日かかる場合がある。
- **支払い/税務プロファイルは今回スキップ可**: PCカスタムサポート は **無料アプリ**で、収益は楽天アフィリエイト（Store外）で得る。Store からの売上分配は受け取らないため、**銀行口座・税務(W-8/W-9等)プロファイルの登録は不要**。登録で最も手間のかかる部分を省ける。将来 Store 内課金を入れる場合のみ設定する。

## 2. アプリ名を予約する

Partner Center で「新しいアプリ」を作成し、Store 表示名として `PCカスタムサポート` を予約します。

- 名前予約はアカウント登録さえ済めば**パッケージ未完成でも今すぐ無料で行える**（早い者勝ちなので先に押さえると良い）。
- 予約後、`製品 > 製品管理 > 製品ID` で Store 提出に必要なパッケージ ID 情報を取得できる（次節で manifest に反映）。

## 3. Manifest の製品識別情報を照合する

`packaging/AppxManifest.xml` には Partner Center で確認した既存Store製品の識別情報を反映済みです。提出前に次の値が Partner Center の表示と一致していることを再確認します。

- `Identity/@Name`: `Mirato.PCChecker`
- `Identity/@Publisher`: `CN=3F06A858-7418-4AB5-A1BD-FD856E9B75B0`
- `Identity/@Version`: `1.0.2.0`
- `Properties/PublisherDisplayName`: `Mirato`

Store 予約アプリ名は `DisplayName=PCカスタムサポート` として設定済みです。予約名を変更した場合は `DisplayName` も合わせて更新してください。

## 4. MSIX をビルドする

Windows SDK をインストールして、`makeappx.exe` と `signtool.exe` が利用できる状態にします。PATH に無い場合でも、スクリプトは標準的な SDK パス `C:\Program Files (x86)\Windows Kits\10\bin\*\x64` から自動探索します。

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_msix.ps1
```

出力先は `dist\msix\PCCustomSupport.msix` です。既存の `dist\PCCustomSupport.exe` を使う場合は `-SkipPyInstaller` を指定します。

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
Add-AppxPackage .\dist\msix\PCCustomSupport.msix
```

## 6. Partner Center にアップロードする

Partner Center の対象アプリでパッケージ提出画面を開き、`dist\msix\PCCustomSupport.msix` をアップロードして審査へ進みます。価格、年齢区分、プライバシー、スクリーンショット、説明文も Store 側で設定します。

## 審査上の注意

- PCカスタムサポート はローカルで FastAPI/uvicorn の Web サーバを起動し、既定ブラウザを開きます。Store 説明文や審査メモで、診断 UI をローカルブラウザで表示するデスクトップアプリであることを明記してください。
- WMI やローカルシステム情報の取得、ブラウザ起動、同梱 exe の通常起動が必要なため、Manifest は `EntryPoint=Windows.FullTrustApplication` + `runFullTrust` capability を使う Desktop Bridge 構成です（純 Win32 アプリのため `windows.fullTrustProcess` 拡張は不要）。審査メモでは、PC スペック診断をローカルで完結させるためのフルトラスト権限であることを説明してください。
- `.env` は秘密鍵を含むため MSIX に同梱しません。楽天 API キーが無い環境でも、価格表示は同梱済みキャッシュやフォールバック表示で動作することを事前に確認してください。
- PyInstaller の onefile 形式は、MSIX 内から起動しても実行時に毎回一時ディレクトリへ展開されるため、起動が遅くなる可能性があります。Store 版の起動時間が問題になる場合は、将来的に `PCCustomSupport.spec` を onedir 形式へ変更することを検討してください。
