"""Read-only public catalog verifier that prints aggregate results only."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tianwai.db import BLINDBOX_SEEDS


def fetch(base: str, path: str, method: str = "GET") -> tuple[int, str]:
    request = Request(
        base.rstrip("/") + path,
        headers={"User-Agent": "Tianwai-readonly-catalog-verifier/1.0"},
        method=method,
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace") if method == "GET" else ""
            return response.status, body
    except HTTPError as error:
        return error.code, ""


def verify(base: str) -> dict[str, int]:
    health_status, health = fetch(base, "/healthz")
    home_status, home = fetch(base, "/")
    _, public_api = fetch(base, "/api/ideas")

    with ThreadPoolExecutor(max_workers=12) as pool:
        details = list(pool.map(lambda idea: fetch(base, f"/ideas/{idea['slug']}"), BLINDBOX_SEEDS))
        checkouts = list(pool.map(lambda idea: fetch(base, f"/checkout/{idea['slug']}"), BLINDBOX_SEEDS))
        asset_paths = [
            "/static/" + idea[key]
            for idea in BLINDBOX_SEEDS[1:]
            for key in ("hero_image", "diagram_image", "scene_image")
        ]
        assets = list(pool.map(lambda path: fetch(base, path, "HEAD"), asset_paths))
        retired = list(
            pool.map(
                lambda path: fetch(base, path),
                ("/transmission", "/dev/line", "/dev/line/reply", "/line/webhook"),
            )
        )

    public_text = home + public_api
    return {
        "health_http": health_status,
        "health_v31": int(json.loads(health).get("release") == "modern-buildable-visuals-v31"),
        "home_http": home_status,
        "published_cards": home.count('class="idea-card sealed-card'),
        "public_titles_present": sum(idea["public_title"] in home for idea in BLINDBOX_SEEDS),
        "private_title_leaks": sum(idea["title"] in public_text for idea in BLINDBOX_SEEDS),
        "private_detail_leaks": sum(
            idea["title"] in body or idea["paid_content"] in body
            for idea, (_, body) in zip(BLINDBOX_SEEDS, details)
        ),
        "detail_200": sum(status == 200 for status, _ in details),
        "checkout_200": sum(status == 200 for status, _ in checkouts),
        "checkout_forms": sum('id="order-form"' in body for _, body in checkouts),
        "home_checkout_links": home.count('href="/checkout/'),
        "payment_closed": int("公開收款仍關閉" in home),
        "new_assets_200": sum(status == 200 for status, _ in assets),
        "retired_routes_404": sum(status == 404 for status, _ in retired),
    }


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5088"
    results = verify(base)
    for key, value in results.items():
        print(f"{key}={value}")

    expected = {
        "health_http": 200,
        "health_v30": 1,
        "home_http": 200,
        "published_cards": 13,
        "public_titles_present": 13,
        "private_title_leaks": 0,
        "private_detail_leaks": 0,
        "detail_200": 13,
        "checkout_200": 13,
        "checkout_forms": 0,
        "home_checkout_links": 0,
        "payment_closed": 1,
        "new_assets_200": 36,
        "retired_routes_404": 4,
    }
    if results != expected:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
