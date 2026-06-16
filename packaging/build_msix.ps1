[CmdletBinding()]
param(
    [switch]$SkipPyInstaller,
    [switch]$Sign,
    [switch]$InstallCertificate,
    [string]$CertificateSubject = "CN=PCChecker Local Test",
    [string]$CertificatePassword = "PCCheckerLocalTest",
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DistExe = Join-Path $RepoRoot "dist\PCChecker.exe"
$LayoutDir = Join-Path $RepoRoot "build\msix-layout"
$OutputDir = Join-Path $RepoRoot "dist\msix"
$ManifestPath = Join-Path $PSScriptRoot "AppxManifest.xml"
$ImagesDir = Join-Path $PSScriptRoot "images"
$MsixPath = Join-Path $OutputDir "PCChecker.msix"
$CertDir = Join-Path $RepoRoot "build\cert"
$PfxPath = Join-Path $CertDir "PCChecker.LocalTest.pfx"

function Find-WindowsSdkTool {
    param([Parameter(Mandatory = $true)][string]$Name)

    # 複数該当しても必ず単一の文字列パスを返す(配列を返すと & 呼び出しでパスを誤解釈する)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return @($command)[0].Source
    }

    $sdkBinRoot = "C:\Program Files (x86)\Windows Kits\10\bin"
    if (Test-Path $sdkBinRoot) {
        $candidates = @(Get-ChildItem -Path $sdkBinRoot -Directory |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName "x64\$Name" } |
            Where-Object { Test-Path $_ })

        if ($candidates.Count -gt 0) {
            return [string]$candidates[0]
        }
    }

    throw "Windows SDK が必要です。$Name が PATH または $sdkBinRoot\*\x64 に見つかりません。"
}

function Find-PythonTool {
    $python = Get-Command "python" -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    $py = Get-Command "py" -ErrorAction SilentlyContinue
    if ($py) {
        return $py.Source
    }

    throw "Python が必要です。python または py を PATH から実行できる状態にしてください。"
}

function New-LocalSigningCertificate {
    param(
        [Parameter(Mandatory = $true)][string]$Subject,
        [Parameter(Mandatory = $true)][string]$PfxFile,
        [Parameter(Mandatory = $true)][string]$Password
    )

    New-Item -ItemType Directory -Force (Split-Path $PfxFile) | Out-Null
    $securePassword = ConvertTo-SecureString $Password -AsPlainText -Force
    $cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $Subject `
        -KeyUsage DigitalSignature `
        -FriendlyName "PCChecker Local MSIX Test Certificate" `
        -CertStoreLocation "Cert:\CurrentUser\My"

    Export-PfxCertificate -Cert $cert -FilePath $PfxFile -Password $securePassword | Out-Null
    return $cert
}

function Install-LocalSigningCertificate {
    param([Parameter(Mandatory = $true)]$Certificate)

    # Store提出時は Microsoft が再署名する。この証明書はサイドロード検証専用。
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store("TrustedPeople", "CurrentUser")
    $store.Open("ReadWrite")
    try {
        $store.Add($Certificate)
    }
    finally {
        $store.Close()
    }
}

function Invoke-PyInstallerBuild {
    param([Parameter(Mandatory = $true)][string]$Python)

    Push-Location $RepoRoot
    try {
        & $Python -m PyInstaller PCChecker.spec --noconfirm
    }
    finally {
        Pop-Location
    }
}

function Copy-CleanDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    if (Test-Path $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }
    New-Item -ItemType Directory -Force $Destination | Out-Null
    Copy-Item -Path (Join-Path $Source "*") -Destination $Destination -Recurse -Force
}

function New-PackageLayout {
    if (-not (Test-Path $DistExe)) {
        throw "dist\PCChecker.exe が見つかりません。-SkipPyInstaller を外してビルドするか、先に PyInstaller を実行してください。"
    }

    if (Test-Path $LayoutDir) {
        Remove-Item -LiteralPath $LayoutDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force $LayoutDir | Out-Null

    Copy-Item -LiteralPath $DistExe -Destination (Join-Path $LayoutDir "PCChecker.exe") -Force
    Copy-Item -LiteralPath $ManifestPath -Destination (Join-Path $LayoutDir "AppxManifest.xml") -Force
    Copy-CleanDirectory -Source (Join-Path $RepoRoot "templates") -Destination (Join-Path $LayoutDir "templates")
    Copy-CleanDirectory -Source (Join-Path $RepoRoot "static") -Destination (Join-Path $LayoutDir "static")
    Copy-CleanDirectory -Source $ImagesDir -Destination (Join-Path $LayoutDir "images")

    # 秘密鍵を含む .env は MSIX に同梱しない。
    $unexpectedEnv = Join-Path $LayoutDir ".env"
    if (Test-Path $unexpectedEnv) {
        Remove-Item -LiteralPath $unexpectedEnv -Force
    }
}

function Invoke-MakeAppxPack {
    param([Parameter(Mandatory = $true)][string]$MakeAppx)

    New-Item -ItemType Directory -Force $OutputDir | Out-Null
    if (Test-Path $MsixPath) {
        Remove-Item -LiteralPath $MsixPath -Force
    }

    & $MakeAppx pack /d $LayoutDir /p $MsixPath /o
}

function Invoke-SignMsix {
    param(
        [Parameter(Mandatory = $true)][string]$SignTool,
        [Parameter(Mandatory = $true)][string]$PackagePath
    )

    if (-not (Test-Path $PfxPath)) {
        $cert = New-LocalSigningCertificate -Subject $CertificateSubject -PfxFile $PfxPath -Password $CertificatePassword
        if ($InstallCertificate) {
            Install-LocalSigningCertificate -Certificate $cert
        }
    }
    elseif ($InstallCertificate) {
        Write-Warning "既存 PFX からの自動インストールは行いません。必要なら証明書 MMC で Trusted People に追加してください。"
    }

    # Store提出時は Microsoft が再署名するため、自己署名はローカルのサイドロード検証用。
    & $SignTool sign /fd SHA256 /f $PfxPath /p $CertificatePassword $PackagePath
}

Push-Location $RepoRoot
try {
    $python = Find-PythonTool

    if (-not $SkipPyInstaller) {
        Invoke-PyInstallerBuild -Python $python
    }

    & $python (Join-Path $PSScriptRoot "make_store_assets.py") --output-dir $ImagesDir

    $makeAppx = Find-WindowsSdkTool -Name "makeappx.exe"
    New-PackageLayout
    Invoke-MakeAppxPack -MakeAppx $makeAppx

    if ($Sign) {
        $signTool = Find-WindowsSdkTool -Name "signtool.exe"
        Invoke-SignMsix -SignTool $signTool -PackagePath $MsixPath
    }

    Write-Host "MSIX output: $MsixPath"
}
finally {
    Pop-Location
}
