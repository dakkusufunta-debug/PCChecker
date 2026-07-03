"""ランディングページの静的内容を検証するテスト"""

from html.parser import HTMLParser
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


class _LandingPageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.links = []
        self.images = []
        self.meta = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        self.tags.append((tag, attrs_dict))
        if tag == "a":
            self.links.append(attrs_dict.get("href", ""))
        if tag == "img":
            self.images.append(attrs_dict)
        if tag == "meta":
            self.meta.append(attrs_dict)


def _read_landing_page() -> str:
    return (PROJECT_DIR / "docs" / "index.html").read_text(encoding="utf-8")


def test_landing_page_has_required_seo_and_links():
    text = _read_landing_page()
    parser = _LandingPageParser()
    parser.feed(text)

    assert '<html lang="ja">' in text
    assert "PCカスタムサポート｜Windows PCの無料スペック診断・アップグレード/買い替え判定ツール" in text
    assert 'name="description"' in text
    assert 'property="og:title"' in text
    assert 'property="og:description"' in text
    assert 'property="og:type" content="website"' in text
    assert 'property="og:image" content="https://dakkusufunta-debug.github.io/PCCustomSupport/img/screen1.png"' in text
    assert 'property="og:url" content="https://dakkusufunta-debug.github.io/PCCustomSupport/"' in text
    assert "https://apps.microsoft.com/detail/9PJ0X9T3PDGL" in parser.links
    assert "privacy-policy.html" in parser.links
    assert "https://webservice.rakuten.co.jp/" in parser.links


def test_landing_page_uses_all_required_screenshots():
    parser = _LandingPageParser()
    parser.feed(_read_landing_page())

    image_sources = {image.get("src") for image in parser.images}
    for index in range(1, 5):
        path = f"img/screen{index}.png"
        assert path in image_sources
        assert (PROJECT_DIR / "docs" / path).is_file()


def test_landing_page_contains_required_product_claims():
    text = _read_landing_page()

    required_phrases = [
        "あなたのPC、まだ使えますか？",
        "買い替え・アップグレード判定を無料で",
        "氏名やPC名などの個人情報を外部へ送信することはありません",
        "CPU",
        "GPU",
        "メモリ",
        "ストレージ",
        "Windows 10/11",
        "フィードバック送信は任意",
        "楽天市場の参考値",
        "アフィリエイトリンク",
        "&copy;2026 Mirato",
    ]
    for phrase in required_phrases:
        assert phrase in text

    assert "TODO" not in text
