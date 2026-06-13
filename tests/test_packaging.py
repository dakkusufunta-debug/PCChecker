"""exe化(PyInstaller)対応のパス解決と起動シーケンスのテスト"""

import socket
import sys
from pathlib import Path

import app_paths
from app_paths import data_dir, env_path, is_frozen, resource_dir
from main import pick_port


PROJECT_DIR = Path(app_paths.__file__).parent


class TestNormalRun:
    """通常実行(非frozen)では従来通りプロジェクト直下を使う"""

    def test_not_frozen(self):
        assert is_frozen() is False

    def test_resource_dir_is_project_dir(self):
        assert resource_dir() == PROJECT_DIR

    def test_data_dir_is_project_dir(self):
        assert data_dir() == PROJECT_DIR

    def test_env_path_is_project_env(self):
        assert env_path() == PROJECT_DIR / ".env"


class TestFrozenRun:
    """凍結実行(exe)をモンキーパッチで再現"""

    def _freeze(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "meipass"), raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "dist" / "PCChecker.exe"))
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))

    def test_resource_dir_is_meipass(self, monkeypatch, tmp_path):
        self._freeze(monkeypatch, tmp_path)
        assert resource_dir() == tmp_path / "meipass"

    def test_data_dir_is_localappdata_and_created(self, monkeypatch, tmp_path):
        self._freeze(monkeypatch, tmp_path)
        result = data_dir()
        assert result == tmp_path / "appdata" / "PCChecker"
        assert result.is_dir()  # 自動作成される

    def test_env_path_prefers_exe_side(self, monkeypatch, tmp_path):
        self._freeze(monkeypatch, tmp_path)
        exe_dir = tmp_path / "dist"
        exe_dir.mkdir(parents=True)
        (exe_dir / ".env").write_text("RAKUTEN_APPLICATION_ID=x", encoding="utf-8")
        assert env_path() == exe_dir / ".env"

    def test_env_path_falls_back_to_data_dir(self, monkeypatch, tmp_path):
        self._freeze(monkeypatch, tmp_path)
        assert env_path() == tmp_path / "appdata" / "PCChecker" / ".env"


class TestIcon:
    """アプリアイコン(static/icon.ico)とspec/HTMLの結線"""

    def test_icon_exists_and_nonempty(self):
        icon = PROJECT_DIR / "static" / "icon.ico"
        assert icon.is_file()
        assert icon.stat().st_size > 0

    def test_spec_references_icon(self):
        spec = (PROJECT_DIR / "PCChecker.spec").read_text(encoding="utf-8")
        assert "icon=" in spec
        assert "static/icon.ico" in spec

    def test_index_html_references_favicon(self):
        html = (PROJECT_DIR / "templates" / "index.html").read_text(encoding="utf-8")
        assert "/static/icon.ico" in html


class TestPickPort:
    def test_returns_preferred_when_free(self):
        # 空きポートを一つ確保してから解放し、それを希望ポートとして渡す
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]
        assert pick_port(free_port) == free_port

    def test_falls_back_when_preferred_is_busy(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            busy_port = s.getsockname()[1]
            result = pick_port(busy_port)
        assert result != busy_port
        assert result > 0
