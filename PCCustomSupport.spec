# -*- mode: python ; coding: utf-8 -*-
# PCカスタムサポート のPyInstallerビルド定義
#   ビルド: python -m PyInstaller PCCustomSupport.spec --noconfirm
#   出力:   dist/PCCustomSupport.exe (単一ファイル・ウィンドウなし)

from PyInstaller.utils.hooks import collect_submodules

# uvicorn は実行時に文字列指定でモジュールを動的importするため明示的に同梱する
hiddenimports = (
    collect_submodules("uvicorn")
    + [
        "anyio._backends._asyncio",  # starlette/anyio が遅延importする
        "wmi",                       # WMI経由のスペック収集
        "pythoncom",
        "win32com",
        "win32com.client",
    ]
)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("templates", "templates"),
        ("static", "static"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "PyInstaller"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PCCustomSupport",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # ウィンドウなし(ログは %LOCALAPPDATA%\PCカスタムサポート\pccustomsupport.log)
    disable_windowed_traceback=False,
    icon="static/icon.ico",
)
