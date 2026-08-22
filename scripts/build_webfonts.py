"""Build the two self-hosted Bakudai WOFF2 subsets used by the public site.

Install the optional build dependencies with:
    python -m pip install fonttools brotli
"""

from __future__ import annotations

import argparse
from pathlib import Path

from fontTools import subset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_TEXT_SOURCES = (
    "templates/base.html",
    "templates/home.html",
    "templates/idea_detail.html",
    "templates/checkout.html",
    "templates/mock_payment.html",
    "templates/order_access.html",
    "templates/message.html",
    "templates/transmission.html",
    "static/app.js",
    "tianwai/public.py",
    "tianwai/payments.py",
    "tianwai/schema.sql",
)


def collect_codepoints() -> set[int]:
    text = "".join(
        (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        for relative_path in PUBLIC_TEXT_SOURCES
    )
    codepoints = {ord(character) for character in text}
    codepoints.update(range(0x20, 0x7F))
    codepoints.update(range(0x3000, 0x3040))
    return codepoints


def subset_font(source: Path, destination: Path, codepoints: set[int]) -> None:
    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.recalc_timestamp = False
    options.canonical_order = True

    font = subset.load_font(str(source), options)
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=codepoints)
    subsetter.subset(font)
    destination.parent.mkdir(parents=True, exist_ok=True)
    subset.save_font(font, str(destination), options)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--regular", required=True, type=Path)
    parser.add_argument("--medium", required=True, type=Path)
    arguments = parser.parse_args()

    codepoints = collect_codepoints()
    outputs = (
        (arguments.regular, PROJECT_ROOT / "static/fonts/tianwai-bakudai-regular.woff2"),
        (arguments.medium, PROJECT_ROOT / "static/fonts/tianwai-bakudai-medium.woff2"),
    )

    for source, destination in outputs:
        subset_font(source, destination, codepoints)
        print(f"{destination.name}|{destination.stat().st_size}")
    print(f"codepoints|{len(codepoints)}")


if __name__ == "__main__":
    main()
