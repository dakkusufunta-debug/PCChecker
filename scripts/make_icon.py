"""PCカスタムサポート のアプリアイコン(static/icon.ico)を生成する。

素材を持たないため、シェアカード(app.js drawShareCard)と同じダークテーマ配色で
ブランドアイコンをプログラム生成する。マルチサイズ(16/32/48/256)の .ico を出力。

実行: python scripts/make_icon.py
依存: Pillow(requirements-dev.txt)
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# シェアカードと共通の配色
BG = (15, 17, 23)          # #0f1117 ベース背景
PANEL = (30, 33, 48)       # #1e2130 パネル
BORDER = (45, 49, 72)      # #2d3148 枠線
ACCENT = (108, 99, 255)    # #6c63ff アクセント(紫)
TEXT = (232, 234, 240)     # #e8eaf0 テキスト

SIZE = 256  # 基準解像度(縮小して各サイズを生成)
ICO_SIZES = [(16, 16), (32, 32), (48, 48), (256, 256)]

OUT_PATH = Path(__file__).resolve().parent.parent / "static" / "icon.ico"


def _load_bold_font(px: int) -> ImageFont.FreeTypeFont:
    """太字TrueTypeフォントを優先順に探す。見つからなければデフォルト。"""
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf",  # Segoe UI Bold
        r"C:\Windows\Fonts\arialbd.ttf",   # Arial Bold
        r"C:\Windows\Fonts\YuGothB.ttc",   # Yu Gothic Bold
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, px)
            except OSError:
                continue
    return ImageFont.load_default()


def _rounded_rect(draw: ImageDraw.ImageDraw, box, radius, **kw) -> None:
    draw.rounded_rectangle(box, radius=radius, **kw)


def build_base() -> Image.Image:
    """256x256 の基準アイコンを描画する。"""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 角丸の濃色背景パネル
    margin = 12
    _rounded_rect(
        d,
        (margin, margin, SIZE - margin, SIZE - margin),
        radius=48,
        fill=PANEL,
        outline=BORDER,
        width=4,
    )

    # PCモニターのモチーフ(アクセント色の角丸枠)
    mon = (54, 60, SIZE - 54, 150)
    _rounded_rect(d, mon, radius=14, outline=ACCENT, width=8)
    # スタンド
    foot_w = 46
    cx = SIZE // 2
    d.rectangle((cx - 8, 150, cx + 8, 174), fill=ACCENT)
    _rounded_rect(d, (cx - foot_w, 174, cx + foot_w, 188), radius=6, fill=ACCENT)

    # 「PC」テキスト(モニター内)
    font = _load_bold_font(64)
    text = "PC"
    tb = d.textbbox((0, 0), text, font=font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    d.text(
        ((SIZE - tw) / 2 - tb[0], (60 + 150) / 2 - th / 2 - tb[1]),
        text,
        font=font,
        fill=TEXT,
    )

    # 下部にアクセントの診断バー(スコアゲージ風)
    bar_y = 206
    d.rounded_rectangle((54, bar_y, SIZE - 54, bar_y + 18), radius=9, fill=BG)
    d.rounded_rectangle((54, bar_y, 168, bar_y + 18), radius=9, fill=ACCENT)

    return img


def main() -> None:
    base = build_base()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    base.save(OUT_PATH, format="ICO", sizes=ICO_SIZES)
    print(f"アイコンを生成しました: {OUT_PATH} ({', '.join(f'{w}x{h}' for w, h in ICO_SIZES)})")


if __name__ == "__main__":
    main()
