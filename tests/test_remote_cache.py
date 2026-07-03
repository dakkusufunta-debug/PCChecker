"""配布版のリモート価格キャッシュ参照(中継サーバー連携)のテスト

ローカル鍵が無い配布版で、search_part / search_bto が CDN 上の日次キャッシュ
を参照し、ヒット・ミス・通信失敗フォールバックを正しく扱うことを検証する。
実ネットワーク・実APIキーには一切依存しない(取得処理をモックする)。
"""
import json
from pathlib import Path

import pytest

import rakuten_client as rc

# 中継サーバーが生成する配信JSONを模したサンプル。
# キーは normalize_keyword 適用後の正規化キーワードであることに注意。
SAMPLE_CACHE = {
    "generated_at": "2026-06-13T12:00:00+09:00",
    "ttl_hours": 24,
    "prices": {
        "NVIDIA RTX 5060": {
            "price": 56000, "item_name": "玄人志向 RTX 5060 8GB",
            "url": "https://example.com/a", "shop": "ショップA",
        },
        # 中継サーバー側でもヒットしなかったパーツは null として記録される
        "AMD Ryzen5 7600": None,
    },
    "bto": {
        "ゲーミングPC RTX 5060 搭載 新品": [
            {"price": 155400, "item_name": "BTOゲーミングPC RTX5060",
             "url": "https://example.com/b", "shop": "ショップB"},
        ],
    },
}


@pytest.fixture(autouse=True)
def isolate_remote(monkeypatch, tmp_path):
    """配布版(鍵なし)を強制し、プロセス内メモ・ローカルファイルを隔離する"""
    monkeypatch.setattr(rc, "is_configured", lambda: False)
    monkeypatch.setattr(rc, "REMOTE_CACHE_PATH", tmp_path / "remote_cache.json")
    monkeypatch.setattr(rc, "_remote_mem", None, raising=False)
    monkeypatch.setattr(rc, "_remote_mem_at", 0.0, raising=False)
    yield


class TestRemotePriceLookup:
    def test_hit_returns_cached_entry(self, monkeypatch):
        monkeypatch.setattr(rc, "_http_get_json", lambda url: dict(SAMPLE_CACHE))
        result = rc.search_part("NVIDIA RTX 3050")  # 引数名は何でもよい
        # 正規化キーワードでヒットすること
        result = rc.search_part("NVIDIA RTX 5060")
        assert result == SAMPLE_CACHE["prices"]["NVIDIA RTX 5060"]

    def test_normalized_key_is_used(self, monkeypatch):
        # 「AMD Ryzen 5 7600」→「AMD Ryzen5 7600」に正規化して引く。
        # サンプルでは null 記録なので None が返る。
        monkeypatch.setattr(rc, "_http_get_json", lambda url: dict(SAMPLE_CACHE))
        assert rc.search_part("AMD Ryzen 5 7600") is None

    def test_miss_returns_none(self, monkeypatch):
        monkeypatch.setattr(rc, "_http_get_json", lambda url: dict(SAMPLE_CACHE))
        assert rc.search_part("存在しないパーツ XYZ999") is None


class TestRemoteBtoLookup:
    def test_hit_returns_item_list(self, monkeypatch):
        monkeypatch.setattr(rc, "_http_get_json", lambda url: dict(SAMPLE_CACHE))
        items = rc.search_bto("ゲーミングPC RTX 5060 搭載 新品", ref_price=200000)
        assert items == SAMPLE_CACHE["bto"]["ゲーミングPC RTX 5060 搭載 新品"]

    def test_miss_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr(rc, "_http_get_json", lambda url: dict(SAMPLE_CACHE))
        assert rc.search_bto("ノートパソコン 新品 16GB SSD", ref_price=90000) == []


class TestNetworkFailureFallback:
    def _raise(self, url):
        raise OSError("network down")

    def test_price_falls_back_to_none(self, monkeypatch):
        monkeypatch.setattr(rc, "_http_get_json", self._raise)
        # 通信失敗 & ローカルキャッシュ無し → 空dict扱い → None(UIはハードコード価格)
        assert rc.search_part("NVIDIA RTX 5060") is None

    def test_bto_falls_back_to_empty(self, monkeypatch):
        monkeypatch.setattr(rc, "_http_get_json", self._raise)
        assert rc.search_bto("ゲーミングPC RTX 5060 搭載 新品", ref_price=200000) == []

    def test_stale_local_cache_used_on_failure(self, monkeypatch, tmp_path):
        # 期限切れ(_fetched_at が十分過去)のローカルキャッシュを用意
        stale = dict(SAMPLE_CACHE)
        stale["_fetched_at"] = 0.0
        rc.REMOTE_CACHE_PATH.write_text(
            json.dumps(stale, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(rc, "_http_get_json", self._raise)
        # CDN取得は失敗するが、古いローカルキャッシュで応答できる
        result = rc.search_part("NVIDIA RTX 5060")
        assert result == SAMPLE_CACHE["prices"]["NVIDIA RTX 5060"]


class TestRemoteCacheFetchBehavior:
    def test_remote_cache_user_agent_is_ascii(self):
        """HTTPヘッダーはASCIIにし、Pythonの送信前エラーを避ける。"""
        source = Path(rc.__file__).read_text(encoding="utf-8")
        assert '"User-Agent": "PCCustomSupport"' in source

    def test_fetched_once_within_refetch_window(self, monkeypatch):
        calls = {"n": 0}

        def counting_get(url):
            calls["n"] += 1
            return dict(SAMPLE_CACHE)

        monkeypatch.setattr(rc, "_http_get_json", counting_get)
        rc.search_part("NVIDIA RTX 5060")
        rc.search_part("存在しないパーツ XYZ999")
        rc.search_bto("ゲーミングPC RTX 5060 搭載 新品", ref_price=200000)
        # 再取得間隔内なのでHTTP取得は1回だけ(プロセス内メモが効く)
        assert calls["n"] == 1


class TestIsAvailable:
    def test_available_when_remote_url_set(self, monkeypatch):
        monkeypatch.setattr(rc, "REMOTE_CACHE_URL", "https://example.com/x.json")
        assert rc.is_available() is True

    def test_unavailable_when_no_key_and_no_url(self, monkeypatch):
        monkeypatch.setattr(rc, "REMOTE_CACHE_URL", "")
        assert rc.is_available() is False
