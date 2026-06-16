# PCChecker 価格キャッシュ 日次更新ラッパー
#   1) build_price_cache.py で楽天APIからキャッシュJSONを生成(異常時はWebhook通知・非0終了)
#   2) 生成が正常(終了コード0)のときだけ Cloudflare Pages へ配信
#      ※異常時に配信しない=Cloudflare上の「最後に成功したキャッシュ」を温存する
#
# 事前設定:
#   - 環境変数 PCCHECKER_ALERT_WEBHOOK にDiscordなどのWebhook URLを設定しておく
#     (setx PCCHECKER_ALERT_WEBHOOK "https://discord.com/api/webhooks/....")
#   - 初回のみ: npx wrangler login でCloudflare認証を済ませておく
#
# 手動実行例:
#   powershell -File scripts\daily_cache_update.ps1
[CmdletBinding()]
param(
    [string]$OutDir = "C:\PCCheckerCache",
    [string]$ProjectName = "pcchecker-cache"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$OutFile = Join-Path $OutDir "price_cache.json"

New-Item -ItemType Directory -Force $OutDir | Out-Null

# 1) キャッシュ生成(.envと登録済みIPで楽天APIを叩く)。CWDをリポジトリ直下にして.envを解決
Push-Location $RepoRoot
try {
    & "python" (Join-Path $RepoRoot "scripts\build_price_cache.py") $OutFile
    $genExit = $LASTEXITCODE
}
finally {
    Pop-Location
}

# 2) 生成が正常(0)のときだけ配信。異常時は配信せずCloudflareの前回分を温存
if ($genExit -eq 0 -and (Test-Path $OutFile)) {
    Write-Host "Deploying $OutFile to Cloudflare Pages project '$ProjectName'..."
    & npx --yes wrangler pages deploy $OutDir --project-name=$ProjectName --commit-dirty=true
}
else {
    Write-Warning "キャッシュ生成が異常終了(コード $genExit)のため配信をスキップしました。Webhook通知を確認してください。"
}

exit $genExit
