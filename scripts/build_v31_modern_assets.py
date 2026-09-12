"""Normalize standalone V31 concept visuals for the revealed-page layout.

Usage:
    python scripts/build_v31_modern_assets.py SOURCE_DIR OUTPUT_DIR

SOURCE_DIR contains independently generated ``v31-XX-{hero,diagram,scene}.png``
files.  Originals stay outside the repository; this script creates compact
1600 x 900 WebP delivery assets without cropping away engineering details.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageFilter


TARGET_SIZE = (1600, 900)


def _presentation_frame(source: Image.Image) -> Image.Image:
    target_w, target_h = TARGET_SIZE
    source = source.convert("RGB")

    cover_scale = max(target_w / source.width, target_h / source.height)
    cover = source.resize(
        (round(source.width * cover_scale), round(source.height * cover_scale)),
        Image.Resampling.LANCZOS,
    )
    left = (cover.width - target_w) // 2
    top = (cover.height - target_h) // 2
    canvas = cover.crop((left, top, left + target_w, top + target_h))
    canvas = canvas.filter(ImageFilter.GaussianBlur(30))

    contain_scale = min(target_w / source.width, target_h / source.height)
    foreground = source.resize(
        (round(source.width * contain_scale), round(source.height * contain_scale)),
        Image.Resampling.LANCZOS,
    )
    x = (target_w - foreground.width) // 2
    y = (target_h - foreground.height) // 2
    canvas.paste(foreground, (x, y))
    return canvas


def build(source_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = {
        f"v31-{volume:02d}-{kind}.png"
        for volume in range(2, 14)
        for kind in ("hero", "diagram", "scene")
    }
    available = {path.name for path in source_dir.glob("v31-*.png")}
    missing = sorted(expected - available)
    if missing:
        raise SystemExit(f"missing V31 sources: {', '.join(missing)}")

    for name in sorted(expected):
        source = Image.open(source_dir / name)
        output = output_dir / f"{Path(name).stem}.webp"
        _presentation_frame(source).save(output, "WEBP", quality=84, method=6)
        print(f"{output.name}: {output.stat().st_size} bytes")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: build_v31_modern_assets.py SOURCE_DIR OUTPUT_DIR")
    build(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
