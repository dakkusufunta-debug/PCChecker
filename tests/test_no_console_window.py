"""外部コマンド実行時にコンソール窓を出さないためのテスト"""

import subprocess

import pc_analyzer


class _FakeStartupInfo:
    def __init__(self):
        self.dwFlags = 0
        self.wShowWindow = None


def test_run_hidden_adds_no_window_flags_on_windows(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(pc_analyzer.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(pc_analyzer.subprocess, "STARTF_USESHOWWINDOW", 0x00000001, raising=False)
    monkeypatch.setattr(pc_analyzer.subprocess, "SW_HIDE", 0, raising=False)
    monkeypatch.setattr(pc_analyzer.subprocess, "STARTUPINFO", _FakeStartupInfo, raising=False)
    monkeypatch.setattr(pc_analyzer.subprocess, "run", fake_run)

    result = pc_analyzer._run_hidden(["powershell"], capture_output=True, text=True, timeout=15)

    assert result.stdout == "ok"
    cmd, kwargs = calls[0]
    assert cmd == ["powershell"]
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["timeout"] == 15
    assert kwargs["creationflags"] == 0x08000000
    assert kwargs["startupinfo"].dwFlags & 0x00000001
    assert kwargs["startupinfo"].wShowWindow == 0


def test_run_hidden_keeps_existing_creationflags(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(pc_analyzer.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(pc_analyzer.subprocess, "STARTUPINFO", _FakeStartupInfo, raising=False)
    monkeypatch.setattr(pc_analyzer.subprocess, "run", fake_run)

    pc_analyzer._run_hidden(["fsutil"], creationflags=0x00000010)

    assert calls[0]["creationflags"] == 0x08000010


def test_run_hidden_does_not_add_creationflags_without_windows_constant(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(pc_analyzer.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    monkeypatch.setattr(pc_analyzer.subprocess, "run", fake_run)

    pc_analyzer._run_hidden(["echo"], timeout=1)

    assert calls[0] == {"timeout": 1}
