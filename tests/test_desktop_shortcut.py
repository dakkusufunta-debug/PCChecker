"""デスクトップショートカット作成機能のテスト"""

import sys
from pathlib import Path

import pytest

import desktop_shortcut as ds


def test_aumid_matches_manifest():
    """AUMIDがAppxManifestのPFN!AppIdと一致すること"""
    assert ds.AUMID == "Mirato.PCChecker_n9bj028cvzf5c!PCChecker"


def test_resolve_target_dev_returns_none(monkeypatch):
    """開発実行(非パッケージ・非凍結)では起動先が確定せずNoneを返す"""
    monkeypatch.setattr(ds, "is_packaged", lambda: False)
    monkeypatch.setattr(ds, "is_frozen", lambda: False)
    assert ds.resolve_target() is None


def test_resolve_target_packaged(monkeypatch):
    """Storeパッケージ実行ではAppsFolder経由でAUMIDを起動する"""
    monkeypatch.setattr(ds, "is_packaged", lambda: True)
    info = ds.resolve_target()
    assert info is not None
    assert "explorer.exe" in info["target"].lower()
    assert info["arguments"] == f"shell:AppsFolder\\{ds.AUMID}"


def test_resolve_target_frozen(monkeypatch):
    """非Storeの凍結exeではexeを直接起動する"""
    monkeypatch.setattr(ds, "is_packaged", lambda: False)
    monkeypatch.setattr(ds, "is_frozen", lambda: True)
    info = ds.resolve_target()
    assert info is not None
    assert info["arguments"] == ""
    assert info["target"] == str(Path(sys.executable))


def test_create_dev_mode(monkeypatch):
    """起動先が解決できない開発実行ではdev_modeを返す"""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ds, "resolve_target", lambda: None)
    result = ds.create_desktop_shortcut()
    assert result["ok"] is False
    assert result["reason"] == "dev_mode"


def test_create_unsupported_os(monkeypatch):
    """Windows以外ではunsupported_osを返す"""
    monkeypatch.setattr(sys, "platform", "linux")
    assert ds.create_desktop_shortcut() == {"ok": False, "reason": "unsupported_os"}


def test_create_with_injected_target(tmp_path, monkeypatch):
    """注入したターゲットで一時フォルダに.lnkが作成されること(pywin32必須)"""
    monkeypatch.setattr(sys, "platform", "win32")
    target = {
        "target": r"C:\Windows\explorer.exe",
        "arguments": f"shell:AppsFolder\\{ds.AUMID}",
        "icon": "",
        "working_dir": "",
    }
    result = ds.create_desktop_shortcut(desktop_dir=str(tmp_path), target=target)
    if result.get("reason") == "no_pywin32":
        pytest.skip("pywin32 未導入のためスキップ")
    assert result["ok"] is True
    lnk = tmp_path / ds.SHORTCUT_NAME
    assert lnk.exists()
    assert result["path"] == str(lnk)


def test_endpoint_returns_json():
    """エンドポイントがJSON(okキー付き)を返すこと"""
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)
    res = client.post("/api/create-desktop-shortcut")
    assert res.status_code == 200
    assert "ok" in res.json()
