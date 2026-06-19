"""
PCChecker - デスクトップショートカット作成

Storeアプリ(MSIX)はインストール時にデスクトップアイコンを作成できないため、
アプリ内から任意でデスクトップに .lnk を作成する手段を提供する。
実行形態に応じて、ショートカットの起動先を切り替える:

- Storeパッケージ実行 : AUMID(shell:AppsFolder\\<PFN>!<AppId>)を explorer 経由で起動
- PyInstaller凍結exe   : exe を直接起動
- 通常実行(開発)       : 起動先が確定しないため作成不可(reason=dev_mode)

win32com(pywin32)は関数内で遅延importし、非Windows環境でも本モジュールの
importが失敗しないようにしている(テスト容易性のため)。
"""

import os
import sys
from pathlib import Path

from app_paths import is_frozen, resource_dir

# AppxManifest.xml の Identity / Application より(Store登録値, 2026-06-16確定)
PACKAGE_FAMILY_NAME = "Mirato.PCChecker_n9bj028cvzf5c"
APP_ID = "PCChecker"
AUMID = f"{PACKAGE_FAMILY_NAME}!{APP_ID}"

SHORTCUT_NAME = "PCChecker.lnk"
SHORTCUT_DESCRIPTION = "PCChecker - PCスペック診断"

# GetCurrentPackageFullName が返す「パッケージ外」エラーコード
_APPMODEL_ERROR_NO_PACKAGE = 15700


def is_packaged() -> bool:
    """MSIX(Store)パッケージ内で実行されているかを判定する。

    Windows の GetCurrentPackageFullName を呼び、APPMODEL_ERROR_NO_PACKAGE
    以外が返ればパッケージ実行とみなす。
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        length = ctypes.c_uint32(0)
        rc = ctypes.windll.kernel32.GetCurrentPackageFullName(
            ctypes.byref(length), None
        )
        return rc != _APPMODEL_ERROR_NO_PACKAGE
    except Exception:
        return False


def _icon_path() -> str:
    """ショートカットに設定するアイコン(.ico)のパス。無ければ空文字。"""
    ico = resource_dir() / "static" / "icon.ico"
    return str(ico) if ico.exists() else ""


def resolve_target() -> dict | None:
    """ショートカットの起動先情報を返す。作成不可な実行形態なら None。

    返却dict: target(起動先exe), arguments(引数), icon, working_dir
    """
    win_dir = os.environ.get("SystemRoot", r"C:\Windows")
    explorer = str(Path(win_dir) / "explorer.exe")
    icon = _icon_path()

    if is_packaged():
        # Storeアプリは AppsFolder 経由で AUMID を起動する
        return {
            "target": explorer,
            "arguments": f"shell:AppsFolder\\{AUMID}",
            "icon": icon,
            "working_dir": "",
        }
    if is_frozen():
        # 非Storeの凍結exeは exe を直接起動する
        exe = str(Path(sys.executable))
        return {
            "target": exe,
            "arguments": "",
            "icon": icon,
            "working_dir": str(Path(sys.executable).parent),
        }
    # 開発実行(python)は起動先が確定しないため作成しない
    return None


def create_desktop_shortcut(
    desktop_dir: str | None = None, target: dict | None = None
) -> dict:
    """デスクトップに PCChecker のショートカットを作成する。

    desktop_dir / target はテスト用の注入口。未指定なら実環境から解決する。
    戻り値: {"ok": True, "path": <lnk>} もしくは {"ok": False, "reason": ...}
    """
    if sys.platform != "win32":
        return {"ok": False, "reason": "unsupported_os"}

    info = target or resolve_target()
    if info is None:
        return {"ok": False, "reason": "dev_mode"}

    try:
        import win32com.client  # pywin32
    except Exception:
        return {"ok": False, "reason": "no_pywin32"}

    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        # OneDriveのデスクトップリダイレクトにも追従するため SpecialFolders を使う
        desk = desktop_dir or shell.SpecialFolders("Desktop")
        lnk_path = str(Path(desk) / SHORTCUT_NAME)

        sc = shell.CreateShortcut(lnk_path)
        sc.TargetPath = info["target"]
        if info.get("arguments"):
            sc.Arguments = info["arguments"]
        if info.get("working_dir"):
            sc.WorkingDirectory = info["working_dir"]
        if info.get("icon"):
            sc.IconLocation = info["icon"]
        sc.Description = SHORTCUT_DESCRIPTION
        sc.Save()
        return {"ok": True, "path": lnk_path}
    except Exception as e:
        return {"ok": False, "reason": "error", "detail": str(e)}
