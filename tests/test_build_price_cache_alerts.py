"""価格キャッシュ生成バッチの健全性アラートのテスト

実ネットワーク・実楽天APIキーには依存せず、生成済みキャッシュの集計と
Webhook送信ペイロードだけを検証する。
"""
import os

import pytest

import scripts.build_price_cache as bpc


def _cache(price_hits: int, price_total: int = 60,
           bto_hits: int = 6, bto_total: int = 6) -> dict:
    prices = {
        f"part-{i}": ({"price": 1000 + i} if i < price_hits else None)
        for i in range(price_total)
    }
    bto = {
        f"bto-{i}": ([{"price": 100000 + i}] if i < bto_hits else [])
        for i in range(bto_total)
    }
    return {
        "generated_at": "2026-06-16T05:00:00+09:00",
        "ttl_hours": 24,
        "prices": prices,
        "bto": bto,
    }


@pytest.fixture(autouse=True)
def isolate_alert_env(monkeypatch):
    """アラート関連の環境変数をテストごとに初期化する"""
    for name in (
        bpc.ALERT_WEBHOOK_ENV,
        bpc.PRICE_MIN_HIT_RATIO_ENV,
        bpc.BTO_MIN_HITS_ENV,
    ):
        monkeypatch.delenv(name, raising=False)
    yield


class TestHealthEvaluation:
    def test_healthy_when_hits_are_enough(self):
        health = bpc.evaluate_health(_cache(price_hits=50, bto_hits=6))

        assert health["healthy"] is True
        assert health["reasons"] == []
        assert health["price_hits"] == 50
        assert health["price_total"] == 60
        assert health["bto_hits"] == 6

    def test_unhealthy_when_price_hits_are_below_half(self):
        health = bpc.evaluate_health(_cache(price_hits=29, bto_hits=6))

        assert health["healthy"] is False
        assert "価格ヒット数がしきい値未満" in health["reasons"][0]
        assert health["price_hits"] == 29

    def test_exactly_half_price_hits_are_healthy(self):
        health = bpc.evaluate_health(_cache(price_hits=30, bto_hits=6))

        assert health["healthy"] is True

    def test_unhealthy_when_bto_hits_are_zero(self):
        health = bpc.evaluate_health(_cache(price_hits=50, bto_hits=0))

        assert health["healthy"] is False
        assert any("BTOヒット数がしきい値未満" in r for r in health["reasons"])

    def test_unhealthy_when_exception_happened(self):
        health = bpc.evaluate_health(exception=RuntimeError("API rejected"))

        assert health["healthy"] is False
        assert "RuntimeError: API rejected" in health["reasons"][0]
        assert "generated_at" in health

    def test_thresholds_can_be_overridden_by_env(self, monkeypatch):
        monkeypatch.setenv(bpc.PRICE_MIN_HIT_RATIO_ENV, "0.8")
        monkeypatch.setenv(bpc.BTO_MIN_HITS_ENV, "2")

        health = bpc.evaluate_health(_cache(price_hits=47, bto_hits=1))

        assert health["healthy"] is False
        assert len(health["reasons"]) == 2


class TestAlertNotification:
    def test_webhook_unset_is_skipped(self, capsys):
        result = bpc.notify_unhealthy(bpc.evaluate_health(_cache(price_hits=29)))

        assert result == {"ok": False, "reason": "not_configured"}
        captured = capsys.readouterr()
        assert bpc.ALERT_WEBHOOK_ENV in captured.err

    def test_webhook_payload_contains_actionable_summary(self, monkeypatch):
        captured = {}

        def fake_post(url, payload):
            captured["url"] = url
            captured["payload"] = payload
            return 204

        monkeypatch.setenv(bpc.ALERT_WEBHOOK_ENV, "https://discord.example/webhook")
        monkeypatch.setattr(bpc, "_http_post_json", fake_post)

        health = bpc.evaluate_health(_cache(price_hits=20, bto_hits=0))
        result = bpc.notify_unhealthy(health)

        assert result == {"ok": True}
        assert captured["url"] == "https://discord.example/webhook"
        assert set(captured["payload"]) == {"content"}
        content = captured["payload"]["content"]
        assert "価格ヒット: 20/60" in content
        assert "BTOヒット: 0/6" in content
        assert "generated_at: 2026-06-16T05:00:00+09:00" in content
        assert "楽天IP許可リストの再確認" in content
        assert "eo光IP変動" in content

    def test_webhook_failure_does_not_raise(self, monkeypatch, capsys):
        def fake_post(url, payload):
            raise OSError("connection refused")

        monkeypatch.setenv(bpc.ALERT_WEBHOOK_ENV, "https://discord.example/webhook")
        monkeypatch.setattr(bpc, "_http_post_json", fake_post)

        result = bpc.notify_unhealthy(bpc.evaluate_health(_cache(price_hits=29)))

        assert result == {"ok": False, "reason": "network_error"}
        assert "異常通知の送信に失敗" in capsys.readouterr().err


class TestMainExitCode:
    def test_unhealthy_result_returns_nonzero_after_writing_cache(self, monkeypatch, tmp_path):
        monkeypatch.setattr(bpc, "is_configured", lambda: True)
        monkeypatch.setattr(bpc, "build_cache", lambda: _cache(price_hits=20, bto_hits=0))
        monkeypatch.setattr(bpc, "notify_unhealthy", lambda health: {"ok": True})

        out_path = tmp_path / "price_cache.json"
        assert bpc.main(["build_price_cache.py", os.fspath(out_path)]) == 1
        assert out_path.exists()

    def test_exception_returns_nonzero_and_notifies(self, monkeypatch, tmp_path):
        notified = {}

        def raise_build():
            raise RuntimeError("API rejected")

        def fake_notify(health):
            notified.update(health)
            return {"ok": True}

        monkeypatch.setattr(bpc, "is_configured", lambda: True)
        monkeypatch.setattr(bpc, "build_cache", raise_build)
        monkeypatch.setattr(bpc, "notify_unhealthy", fake_notify)

        out_path = tmp_path / "price_cache.json"
        assert bpc.main(["build_price_cache.py", os.fspath(out_path)]) == 1
        assert not out_path.exists()
        assert notified["healthy"] is False
        assert "API rejected" in notified["reasons"][0]
