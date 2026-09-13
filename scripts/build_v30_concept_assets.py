"""Slice V30 triptych source sheets into optimized revealed-page WebP assets.

Usage:
    python scripts/build_v30_concept_assets.py SOURCE_DIR OUTPUT_DIR

SOURCE_DIR must contain ``v30-02-triptych.png`` through
``v30-13-triptych.png``.  The generator occasionally varies panel widths, so
the script locates the two pale gutters near the expected thirds instead of
assuming exact pixel coordinates.
"""

from __future__ import annotations

import sys
from pathlib import Path
from statistics import pstdev

from PIL import Image, ImageFilter


TARGET_SIZE = (1600, 900)


def _column_score(image: Image.Image, x: int) -> float:
    samples = [image.getpixel((x, y)) for y in range(0, image.height, max(1, image.height // 80))]
    brightness = [sum(pixel[:3]) / 3 for pixel in samples]
    return sum(brightness) / len(brightness) - (pstdev(brightness) * 1.35)


def _gutter_center(image: Image.Image, expected: int) -> int:
    radius = max(28, image.width // 16)
    candidates = range(max(1, expected - radius), min(image.width - 1, expected + radius))
    return max(candidates, key=lambda x: _column_score(image, x))


def _presentation_frame(panel: Image.Image) -> Image.Image:
    target_w, target_h = TARGET_SIZE
    background = panel.copy()
    background.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)

    cover_scale = max(target_w / panel.width, target_h / panel.height)
    cover = panel.resize(
        (round(panel.width * cover_scale), round(panel.height * cover_scale)),
        Image.Resampling.LANCZOS,
    )
    left = (cover.width - target_w) // 2
    top = (cover.height - target_h) // 2
    canvas = cover.crop((left, top, left + target_w, top + target_h))
    canvas = canvas.filter(ImageFilter.GaussianBlur(34))

    foreground_scale = min(target_w / panel.width, (target_h * 1.12) / panel.height)
    foreground = panel.resize(
        (round(panel.width * foreground_scale), round(panel.height * foreground_scale)),
        Image.Resampling.LANCZOS,
    )
    if foreground.height > target_h:
        trim = (foreground.height - target_h) // 2
        foreground = foreground.crop((0, trim, foreground.width, trim + target_h))
    x = (target_w - foreground.width) // 2
    y = (target_h - foreground.height) // 2
    canvas.paste(foreground, (x, y))
    return canvas


def build(source_dir: Path, output_dir: Path) -> None:
    if output_dir.resolve().is_relative_to(Path(__file__).resolve().parents[1] / "static"):
        raise ValueError("Paid assets must be built outside public static; use private_assets/brand/concepts")
    output_dir.mkdir(parents=True, exist_ok=True)
    labels = ("hero", "diagram", "scene")
    for volume in range(2, 14):
        source = source_dir / f"v30-{volume:02d}-triptych.png"
        image = Image.open(source).convert("RGB")
        first = _gutter_center(image, image.width // 3)
        second = _gutter_center(image, image.width * 2 // 3)
        gutter_half = max(7, image.width // 180)
        bounds = (
            (0, first - gutter_half),
            (first + gutter_half, second - gutter_half),
            (second + gutter_half, image.width),
        )
        for label, (left, right) in zip(labels, bounds):
            panel = image.crop((left, 0, right, image.height))
            output = output_dir / f"v30-{volume:02d}-{label}.webp"
            _presentation_frame(panel).save(output, "WEBP", quality=82, method=6)
            print(f"{output.name}: {output.stat().st_size} bytes")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: build_v30_concept_assets.py SOURCE_DIR OUTPUT_DIR")
    build(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
