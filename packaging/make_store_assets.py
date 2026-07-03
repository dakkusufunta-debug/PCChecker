"""PCカスタムサポート の Microsoft Store / MSIX 用 PNG アセットを生成する。"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ICON = REPO_ROOT / "static" / "icon.ico"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "images"
BACKGROUND = (16, 24, 32, 255)

# Manifest から参照する基本アセット。
# Square44x44Logo: タスクバー/小タイル、Square71x71Logo: 小タイル、
# Square150x150Logo: 中タイル、Wide310x150Logo: ワイドタイル、
# Square310x310Logo: 大タイル、StoreLogo: パッケージ/Store表示、
# SplashScreen: 起動スプラッシュ。
BASE_ASSETS = {
    "Square44x44Logo.png": (44, 44),
    "Square71x71Logo.png": (71, 71),
    "Square150x150Logo.png": (150, 150),
    "Wide310x150Logo.png": (310, 150),
    "Square310x310Logo.png": (310, 310),
    "StoreLogo.png": (50, 50),
    "SplashScreen.png": (620, 300),
}

# Windows のスケール修飾子。代表サイズ生成で Store/タイルの検証に必要な実体を揃える。
SCALES = {
    "scale-125": 1.25,
    "scale-150": 1.5,
    "scale-200": 2.0,
    "scale-400": 4.0,
}


def load_icon(icon_path: Path) -> Image.Image:
    """ico から最大解像度の画像を取り出す。"""

    if not icon_path.is_file():
        raise FileNotFoundError(f"アイコンが見つかりません: {icon_path}")

    with Image.open(icon_path) as icon:
        frames = getattr(icon, "n_frames", 1)
        largest = None
        for frame in range(frames):
            icon.seek(frame)
            candidate = icon.convert("RGBA").copy()
            if largest is None or candidate.width * candidate.height > largest.width * largest.height:
                largest = candidate

    if largest is None:
        raise ValueError(f"アイコンを読み込めません: {icon_path}")
    return largest


def compose_asset(icon: Image.Image, size: tuple[int, int]) -> Image.Image:
    """背景付きキャンバス中央にアイコンを配置する。"""

    width, height = size
    canvas = Image.new("RGBA", size, BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    inset = max(4, int(min(width, height) * 0.18))
    max_icon_size = (max(1, width - inset * 2), max(1, height - inset * 2))
    rendered_icon = icon.copy()
    rendered_icon.thumbnail(max_icon_size, Image.Resampling.LANCZOS)
    x = (width - rendered_icon.width) // 2
    y = (height - rendered_icon.height) // 2
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=max(2, min(width, height) // 18), fill=BACKGROUND)
    canvas.alpha_composite(rendered_icon, (x, y))
    return canvas


def generate_assets(icon_path: Path = DEFAULT_ICON, output_dir: Path = DEFAULT_OUTPUT_DIR) -> list[Path]:
    """基本アセットと scale-125/150/200/400 バリアントを生成する。"""

    icon = load_icon(icon_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for name, size in BASE_ASSETS.items():
        path = output_dir / name
        compose_asset(icon, size).save(path)
        written.append(path)

        stem = path.stem
        for suffix, scale in SCALES.items():
            scaled_size = (round(size[0] * scale), round(size[1] * scale))
            scaled_path = output_dir / f"{stem}.{suffix}.png"
            compose_asset(icon, scaled_size).save(scaled_path)
            written.append(scaled_path)

    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="MSIX/Store 用 PNG アセットを生成します。")
    parser.add_argument("--icon", type=Path, default=DEFAULT_ICON, help="入力 ico ファイル")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="PNG 生成先")
    args = parser.parse_args()

    written = generate_assets(args.icon, args.output_dir)
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
