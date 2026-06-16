"""Microsoft Store 用アセット生成のテスト"""

from pathlib import Path
import importlib.util

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image


PROJECT_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_DIR / "packaging" / "make_store_assets.py"
SPEC = importlib.util.spec_from_file_location("make_store_assets", MODULE_PATH)
make_store_assets = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(make_store_assets)

BASE_ASSETS = make_store_assets.BASE_ASSETS
SCALES = make_store_assets.SCALES
generate_assets = make_store_assets.generate_assets


def test_generate_store_assets_from_icon(tmp_path):
    icon_path = tmp_path / "icon.ico"
    icon = Image.new("RGBA", (256, 256), (16, 24, 32, 255))
    icon.save(icon_path, sizes=[(256, 256)])

    output_dir = tmp_path / "images"
    written = generate_assets(icon_path=icon_path, output_dir=output_dir)
    written_paths = {Path(path) for path in written}

    for name, size in BASE_ASSETS.items():
        asset_path = output_dir / name
        assert asset_path in written_paths
        assert asset_path.is_file()
        with Image.open(asset_path) as asset:
            assert asset.size == size

        stem = asset_path.stem
        for suffix, scale in SCALES.items():
            scaled_path = output_dir / f"{stem}.{suffix}.png"
            assert scaled_path in written_paths
            assert scaled_path.is_file()
            with Image.open(scaled_path) as scaled_asset:
                assert scaled_asset.size == (round(size[0] * scale), round(size[1] * scale))
