"""
PCカスタムサポート - 実行環境に応じたパス解決

通常実行(python main.py / uvicorn)とPyInstaller凍結実行(exe)の両方で
リソース(templates/static)とユーザーデータ(.env / 価格キャッシュ)の
置き場所を正しく解決する。

- リソース: 凍結時は PyInstaller が展開する一時フォルダ(sys._MEIPASS)
- ユーザーデータ: 凍結時は %LOCALAPPDATA%\\PCカスタムサポート(exe内は読み取り専用のため)
- .env: 凍結時は exe と同じフォルダ → データフォルダの順に探す
"""

import os
import sys
from pathlib import Path

_MODULE_DIR = Path(__file__).parent

APP_NAME = "PCカスタムサポート"
APP_VERSION = "1.0.2"


def is_frozen() -> bool:
    """PyInstallerでexe化された実行環境かどうか"""
    return getattr(sys, "frozen", False)


def resource_dir() -> Path:
    """templates/static など同梱リソースの場所"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", _MODULE_DIR))
    return _MODULE_DIR


def data_dir() -> Path:
    """書き込み可能なユーザーデータフォルダ(なければ作成する)"""
    if is_frozen():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / APP_NAME
    else:
        path = _MODULE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def env_path() -> Path:
    """.env の探索: exeと同じフォルダ → データフォルダ(開発時はプロジェクト直下)"""
    if is_frozen():
        exe_side = Path(sys.executable).parent / ".env"
        if exe_side.exists():
            return exe_side
        return data_dir() / ".env"
    return _MODULE_DIR / ".env"
