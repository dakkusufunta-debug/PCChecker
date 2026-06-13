"""feedback_client のテスト(ネットワーク・実送信先不要)

フィードバック送信の検証ロジック(カテゴリ・空コメント・文字数上限・
診断データのサイズ上限)と、送信成功/通信失敗/サーバーエラーの扱いを検証する。
実際のHTTP送信はモックする。
"""
import pytest

import feedback_client as fc


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    """送信先を設定済みにし、HTTP送信を既定で成功(204)にする"""
    monkeypatch.setattr(fc, "FEEDBACK_URL", "https://example.workers.dev")
    monkeypatch.setattr(fc, "_http_post_json", lambda url, payload: 204)
    yield


class TestValidation:
    def test_rejects_empty_comment(self):
        assert fc.submit_feedback("bug", "   ") == {"ok": False, "reason": "empty_comment"}

    def test_rejects_unknown_category(self):
        res = fc.submit_feedback("spam", "本文あり")
        assert res == {"ok": False, "reason": "bad_category"}

    def test_accepts_known_categories(self):
        for cat in ("bug", "request", "other"):
            assert fc.submit_feedback(cat, "テスト本文") == {"ok": True}

    def test_not_configured(self, monkeypatch):
        monkeypatch.setattr(fc, "FEEDBACK_URL", "")
        assert fc.submit_feedback("bug", "本文") == {"ok": False, "reason": "not_configured"}


class TestPayload:
    def test_comment_is_truncated_to_max_len(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(fc, "_http_post_json",
                            lambda url, payload: captured.update(payload) or 204)
        long_comment = "あ" * (fc.MAX_COMMENT_LEN + 500)
        assert fc.submit_feedback("bug", long_comment) == {"ok": True}
        assert len(captured["comment"]) == fc.MAX_COMMENT_LEN

    def test_payload_includes_version_and_timestamp(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(fc, "_http_post_json",
                            lambda url, payload: captured.update(payload) or 204)
        fc.submit_feedback("request", "機能要望です")
        assert captured["app_version"] == fc.APP_VERSION
        assert "submitted_at" in captured and "platform" in captured

    def test_diagnostics_attached_when_provided(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(fc, "_http_post_json",
                            lambda url, payload: captured.update(payload) or 204)
        diag = {"specs": {"cpu_name": "Ryzen 5 7600"}, "profiles": {}}
        fc.submit_feedback("bug", "不具合です", diagnostics=diag)
        assert captured["diagnostics"] == diag

    def test_oversized_diagnostics_are_dropped(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(fc, "_http_post_json",
                            lambda url, payload: captured.update(payload) or 204)
        huge = {"blob": "x" * (fc.MAX_DIAGNOSTICS_BYTES + 10)}
        assert fc.submit_feedback("bug", "本文", diagnostics=huge) == {"ok": True}
        # サイズ超過の診断データは付かないが、コメント本文は送られる
        assert "diagnostics" not in captured
        assert captured["comment"] == "本文"


class TestTransport:
    def test_network_error_reported(self, monkeypatch):
        def boom(url, payload):
            raise OSError("connection refused")
        monkeypatch.setattr(fc, "_http_post_json", boom)
        assert fc.submit_feedback("bug", "本文") == {"ok": False, "reason": "network_error"}

    def test_server_error_reported(self, monkeypatch):
        monkeypatch.setattr(fc, "_http_post_json", lambda url, payload: 500)
        assert fc.submit_feedback("bug", "本文") == {"ok": False, "reason": "server_error"}

    def test_2xx_is_success(self, monkeypatch):
        monkeypatch.setattr(fc, "_http_post_json", lambda url, payload: 200)
        assert fc.submit_feedback("other", "本文") == {"ok": True}


class TestIsConfigured:
    def test_true_when_url_set(self):
        assert fc.is_feedback_configured() is True

    def test_false_when_url_empty(self, monkeypatch):
        monkeypatch.setattr(fc, "FEEDBACK_URL", "")
        assert fc.is_feedback_configured() is False
