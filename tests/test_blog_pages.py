"""SEOブログ記事の静的内容を検証するテスト"""

from html.parser import HTMLParser
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
BLOG_DIR = PROJECT_DIR / "docs" / "blog"
STORE_URL = "https://apps.microsoft.com/detail/9PJ0X9T3PDGL"


class _BlogPageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.images = []
        self.meta = []
        self.h1_count = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "a":
            self.links.append(attrs_dict.get("href", ""))
        if tag == "img":
            self.images.append(attrs_dict.get("src", ""))
        if tag == "meta":
            self.meta.append(attrs_dict)
        if tag == "h1":
            self.h1_count += 1


BLOG_PAGES = {
    "pc-replace-timing.html": {
        "title": "パソコン買い替え時期の目安｜PC寿命",
        "keywords": ["パソコンの買い替え時期", "PC寿命", "アップグレード"],
        "related": ["check-pc-spec.html", "memory-upgrade.html"],
    },
    "check-pc-spec.html": {
        "title": "PCスペック確認方法｜性能の調べ方",
        "keywords": ["PCのスペックを確認する方法", "パソコン性能の調べ方", "買い替え/アップグレード"],
        "related": ["pc-replace-timing.html", "memory-upgrade.html"],
    },
    "memory-upgrade.html": {
        "title": "メモリ増設の効果｜16GBと32GBの違い",
        "keywords": ["メモリ増設の効果", "16GBと32GBの違い", "アップグレード判断"],
        "related": ["pc-replace-timing.html", "check-pc-spec.html"],
    },
}


def _read_blog_page(filename: str) -> str:
    return (BLOG_DIR / filename).read_text(encoding="utf-8")


def test_blog_pages_exist_and_have_required_seo():
    for filename, expected in BLOG_PAGES.items():
        text = _read_blog_page(filename)
        parser = _BlogPageParser()
        parser.feed(text)

        assert '<html lang="ja">' in text
        assert f"<title>{expected['title']}</title>" in text
        assert 'name="description"' in text
        assert 'property="og:title"' in text
        assert 'property="og:description"' in text
        assert 'property="og:type" content="article"' in text
        assert 'property="og:image" content="https://dakkusufunta-debug.github.io/PCCustomSupport/img/screen1.png"' in text
        assert 'rel="stylesheet" href="../lp.css"' in text
        assert 'rel="stylesheet" href="blog.css"' in text
        assert parser.h1_count == 1
        assert "../index.html" in parser.links
        assert STORE_URL in parser.links
        assert "../privacy-policy.html" in parser.links
        assert "../img/screen1.png" in text or parser.images
        assert "公開日: 2026-06-17 / 更新日: 2026-06-17" in text

        for keyword in expected["keywords"]:
            assert keyword in text


def test_blog_pages_have_required_cta_disclosure_and_related_links():
    for filename, expected in BLOG_PAGES.items():
        text = _read_blog_page(filename)
        parser = _BlogPageParser()
        parser.feed(text)

        assert "公開準備中" not in text
        assert "アフィリエイト開示" in text
        assert "成果報酬型のアフィリエイトリンク" in text
        assert "氏名やPC名などの個人情報を外部へ送信することはありません" in text
        assert "提供元 Mirato" in text
        # 楽天アフィリエイトの正規リンク(短縮URL)を掲載済み。TODOプレースホルダは残さない
        assert "https://a.r10.to/" in text
        assert "TODO" not in text

        for related in expected["related"]:
            assert related in parser.links


def test_blog_index_links_to_all_articles():
    text = _read_blog_page("index.html")
    parser = _BlogPageParser()
    parser.feed(text)

    assert '<html lang="ja">' in text
    assert "../index.html" in parser.links
    assert "../privacy-policy.html" in parser.links
    for filename in BLOG_PAGES:
        assert filename in parser.links
