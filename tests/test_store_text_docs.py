"""Microsoft Store 提出用テキスト文書のテスト"""

from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


def _read_docs(path: str) -> str:
    return (PROJECT_DIR / path).read_text(encoding="utf-8")


def test_privacy_policy_markdown_has_required_facts():
    text = _read_docs("docs/privacy-policy.md")

    required = [
        "最終更新日: 2026-06-16",
        "提供者: Mirato",
        "ローカルに実行され、既定では外部に送信されません",
        "楽天市場",
        "フィードバックフォームから任意で送信した場合にのみ",
        "アプリバージョン、OS/実行環境情報、送信時刻",
        "「診断結果を添付する」チェックを有効にした場合に限り",
        "氏名、PC 名などの個人情報は含めない設計",
        "アフィリエイトリンク",
        "行動追跡や広告配信",
        "アプリ内のフィードバックフォームからご連絡ください",
    ]
    for phrase in required:
        assert phrase in text

    # 連絡先はアプリ内フィードバックに一本化(個人メール露出を避けるため未掲載)
    assert "TODO" not in text
    assert "@" not in text


def test_privacy_policy_html_is_standalone_and_consistent():
    text = _read_docs("docs/privacy-policy.html")

    assert "<!DOCTYPE html>" in text
    assert "<style>" in text
    assert "PCカスタムサポート プライバシーポリシー" in text
    assert "最終更新日: 2026-06-16" in text
    assert "提供者: Mirato" in text
    assert "既定では外部に送信されません" in text
    assert "アプリバージョン、OS/実行環境情報、送信時刻" in text
    assert "アプリ内のフィードバックフォームからご連絡ください" in text
    assert "TODO" not in text


def test_store_submission_doc_has_v1_0_2_build_record():
    text = _read_docs("docs/store-submission.md")

    assert "TODO" not in text

    # バージョンとStore固定ID
    assert "1.0.2" in text
    assert "1.0.2.0" in text
    assert "Mirato.PCChecker" in text
    assert "Mirato.PCChecker_n9bj028cvzf5c" in text

    # MSIX ハッシュ (大文字で記録)
    assert "SHA-256" in text
    assert "算出待ち" not in text

    # 自己署名 Root 追加を避ける旨の注意
    assert "Root" in text
    assert "0x800B0109" in text

    # 次の確認手段として Partner Center が明記されていること
    assert "Partner Center" in text


def test_store_listing_has_submission_sections():
    text = _read_docs("docs/store-listing.md")

    required_headings = [
        "## 製品名",
        "## 短い説明",
        "## 詳細説明",
        "## 主な機能",
        "## 検索キーワード",
        "## カテゴリ案",
        "## 推奨年齢区分の補足",
        "## 審査メモ用の補足文",
    ]
    for heading in required_headings:
        assert heading in text

    assert "無料" in text
    assert "お使いのパソコンの性能をわかりやすく解説" in text
    assert "パーツ交換やパソコンの買い替えをアドバイス" in text
    assert "今の PC がまだ使えるか" in text
    assert "部品別" not in text
    assert "参考候補" not in text
    assert "価格目安" not in text
    public_text = text.split("## 審査メモ用の補足文", maxsplit=1)[0]
    assert "氏名や PC 名などの個人情報を外部へ送信することはありません" not in public_text
    assert "127.0.0.1" in text
    assert "フルトラスト権限" in text
    assert ".env" in text
    assert "フォールバック" in text
    assert "アプリバージョン、OS/実行環境情報、送信時刻" in text
