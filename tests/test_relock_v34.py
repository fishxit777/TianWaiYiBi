"""V34 contract checks: one new sealed volume, private illustrations, no reseeding loss.

All access and payment fixtures use the isolated local test app / mock provider.
No production accounts, real payments, delivery services, or vehicle I/O are used.
"""

import hashlib
import html
import json
import re
from pathlib import Path

import pytest

from conftest import set_public_csrf
from test_public_flow import create_order
from tianwai.db import BLINDBOX_SEEDS, get_db, init_db


SLUG = "sealed-concept-v14"
TITLE = "ReLock｜二次移動鎖"
SLOTS = ("hero", "diagram", "scene")
ASSETS = {slot: f"brand/concepts/v34-14-{slot}.webp" for slot in SLOTS}


def _v14_idea(app):
    with app.app_context():
        row = get_db().execute("SELECT * FROM ideas WHERE slug = ?", (SLUG,)).fetchone()
        assert row is not None, "V34 volume has not been integrated into the catalog"
        return dict(row)


def _activate_synthetic_reader(client, slug):
    """Exercise the existing mock checkout/activation without any external delivery."""
    order = create_order(client, slug=slug)
    payment = client.get(order["checkout_url"]).get_data(as_text=True)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', payment).group(1)
    token = re.search(r'name="payment_token" value="([^"]+)"', payment).group(1)
    completed = client.post(
        "/pay/mock/complete",
        data={"csrf_token": csrf, "payment_token": token},
        follow_redirects=True,
    )
    assert completed.status_code == 200
    body = completed.get_data(as_text=True)
    code = re.search(r"本機測試開通碼.*?<strong>([^<]+)</strong>", body, re.S).group(1)
    activation_path = re.search(r'href="(/activate/[^\"]+)"', body).group(1)
    activated = client.post(
        activation_path,
        data={"csrf_token": set_public_csrf(client), "activation_code": code},
        follow_redirects=False,
    )
    assert activated.status_code == 302
    return order["order_no"]


@pytest.fixture
def v14_reader(app, client):
    idea = _v14_idea(app)
    return client, _activate_synthetic_reader(client, SLUG), idea


def _webp_dimensions(data):
    """Read the three standard WebP frame headers without adding a runtime dependency."""
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    offset = 12
    while offset + 8 <= len(data):
        kind = data[offset:offset + 4]
        size = int.from_bytes(data[offset + 4:offset + 8], "little")
        chunk = data[offset + 8:offset + 8 + size]
        if kind == b"VP8X":
            return (
                1 + int.from_bytes(chunk[4:7], "little"),
                1 + int.from_bytes(chunk[7:10], "little"),
            )
        if kind == b"VP8 ":
            assert chunk[3:6] == b"\x9d\x01\x2a"
            return (
                int.from_bytes(chunk[6:8], "little") & 0x3FFF,
                int.from_bytes(chunk[8:10], "little") & 0x3FFF,
            )
        if kind == b"VP8L":
            assert chunk[0] == 0x2F
            bits = int.from_bytes(chunk[1:5], "little")
            return (1 + (bits & 0x3FFF), 1 + ((bits >> 14) & 0x3FFF))
        offset += 8 + size + size % 2
    raise AssertionError("WebP has no recognized image dimensions")


def test_v14_catalog_contract_and_six_implementation_steps(app):
    idea = _v14_idea(app)
    assert sum(seed["slug"] == SLUG for seed in BLINDBOX_SEEDS) == 1
    assert idea["title"] == TITLE
    assert idea["public_title"] == "封印盲策・第拾肆卷"
    assert (idea["primary_vein"], idea["secondary_vein"]) == ("守護脈", "靈機脈")
    assert (idea["published"], idea["workflow_status"], idea["sort_order"]) == (1, "published", 14)
    assert idea["price_override"] is None
    for slot, identifier in ASSETS.items():
        assert idea[slot + "_image"] == identifier
        assert idea[slot + "_caption"].strip()
    assert len({idea[slot + "_caption"] for slot in SLOTS}) == 3

    content = idea["paid_content"]
    assert len(content) >= 1500
    assert "模擬" in content
    assert any(label in content for label in ("原理", "機制"))
    assert "模組" in content
    assert "測試" in content
    assert "限制" in content
    numbered_steps = re.findall(
        r"(?m)^\s*(?:Micro-MVP\s*[｜|]\s*)?(?:步驟\s*)?([1-9]\d*)\s*[.、｜|：:)]", content
    )
    assert set(range(1, 7)).issubset({int(number) for number in numbered_steps})
    # These are delivery boundaries, not claims that the underlying concept works.
    assert "真車" in content
    assert any(term in content for term in ("未驗證", "待驗證", "不代表"))


@pytest.mark.parametrize("slot", SLOTS)
def test_v14_illustrations_are_real_compact_private_webp_files(app, client, slot):
    idea = _v14_idea(app)
    identifier = idea[slot + "_image"]
    asset = Path(app.config["PRIVATE_ASSET_ROOT"]) / identifier
    assert asset.is_file(), "V34 illustration is missing; generation is not yet complete"
    assert not (Path(app.static_folder) / identifier).exists()
    data = asset.read_bytes()
    assert 0 < len(data) < 700_000
    assert _webp_dimensions(data) == (1600, 900)
    for prefix in ("/static/", "/private_assets/"):
        response = client.get(prefix + identifier)
        assert response.status_code == 404
        assert not response.data.startswith(b"RIFF")


@pytest.mark.parametrize("path", ("/", "/api/ideas", "/ideas/" + SLUG, "/checkout/" + SLUG))
def test_v14_public_surfaces_only_contain_sealed_clues(app, client, path):
    idea = _v14_idea(app)
    response = client.get(path)
    assert response.status_code == 200
    # Flask may escape CJK in JSON; inspect decoded values rather than wire encoding.
    body = (
        json.dumps(response.get_json(), ensure_ascii=False)
        if response.is_json else html.unescape(response.get_data(as_text=True))
    )
    assert idea["public_title"] in body
    for private_value in (TITLE, "ReLock", "二次移動鎖", idea["paid_content"], *ASSETS.values()):
        assert private_value not in body
    assert "/library/assets/" not in body


@pytest.mark.parametrize("slot", SLOTS)
@pytest.mark.parametrize("method", ("GET", "HEAD"))
def test_v14_anonymous_asset_access_is_denied_without_cache(app, client, slot, method):
    idea = _v14_idea(app)
    response = client.open(
        f"/library/assets/{idea['id']}/{slot}",
        method=method,
        headers={"Range": "bytes=0-31", "If-None-Match": "*"},
    )
    assert response.status_code == 404
    assert "no-store" in response.headers["Cache-Control"]
    assert not response.data.startswith(b"RIFF")


@pytest.mark.parametrize("path", ("/", "/ideas/" + SLUG, "/checkout/" + SLUG))
def test_v14_public_scroll_uses_guardian_clue_not_twin_tire_art(client, path):
    body = client.get(path).get_data(as_text=True)
    if path == "/":
        body = re.search(r'href="/ideas/sealed-concept-v14".*?</a>', body, re.S).group(0)
    assert "觀險守程" in body
    assert "雙輪護陣" not in body
    assert '<circle cx="25" cy="34" r="12"' not in body


@pytest.mark.parametrize("slot", SLOTS)
def test_v14_correct_buyer_can_read_each_image_and_full_content(v14_reader, app, slot):
    client, order_no, idea = v14_reader
    asset_path = f"/library/assets/{idea['id']}/{slot}"
    expected = Path(app.config["PRIVATE_ASSET_ROOT"]) / ASSETS[slot]
    assert expected.is_file(), "V34 illustration is missing; generation is not yet complete"
    expected_hash = hashlib.sha256(expected.read_bytes()).digest()
    for method in ("GET", "HEAD"):
        response = client.open(asset_path, method=method, headers={"Range": "bytes=0-31", "If-None-Match": "*"})
        assert response.status_code == 200
        assert response.mimetype == "image/webp"
        assert "no-store" in response.headers["Cache-Control"]
        assert response.headers["Referrer-Policy"] == "no-referrer"
        for header in ("ETag", "Last-Modified", "Content-Range"):
            assert header not in response.headers
        if method == "GET":
            assert hashlib.sha256(response.data).digest() == expected_hash

    reading = client.get("/library/orders/" + order_no)
    assert reading.status_code == 200
    assert "no-store" in reading.headers["Cache-Control"]
    body = reading.get_data(as_text=True)
    assert TITLE in body
    assert 'class="manuscript-copy"' in body
    # The new manuscript presents headings/paragraphs separately, preserving every line.
    for line in idea["paid_content"].strip().splitlines():
        if line:
            assert line in html.unescape(body)
    assert 'volume-v34' in body
    assert 'v34-reader.css' in body
    assert body.count('class="v34-reader-section"') == 14
    assert len(re.findall(r'<h3>Micro-MVP｜步驟 [1-6]｜', body)) == 6
    for image_slot in SLOTS:
        assert f"/library/assets/{idea['id']}/{image_slot}" in body
        assert idea[image_slot + "_caption"] in body
    assert not any(identifier in body for identifier in ASSETS.values())


def test_v14_cannot_be_read_using_only_a_previous_volume_entitlement(app, client):
    idea = _v14_idea(app)
    previous_order = _activate_synthetic_reader(client, "sealed-twin-tire-safety")
    previous_reading = client.get("/library/orders/" + previous_order).get_data(as_text=True)
    assert 'class="manuscript-copy"' in previous_reading
    assert 'v34-reader.css' not in previous_reading
    assert 'volume-v34' not in previous_reading
    assert 'v34-reader-section' not in previous_reading
    for slot in SLOTS:
        response = client.get(f"/library/assets/{idea['id']}/{slot}")
        assert response.status_code == 404
        assert "no-store" in response.headers["Cache-Control"]
        assert not response.data.startswith(b"RIFF")


@pytest.mark.parametrize("separator", ("\n\n", "\r\n\r\n", "\n\n\n\n\n"))
def test_v14_edited_paragraphs_keep_text_and_do_not_become_headings(v14_reader, app, separator):
    client, order_no, _ = v14_reader
    newline = "\r\n" if "\r" in separator else "\n"
    paragraphs = [
        "概念原點" + newline + "合成段落甲。",
        "這是補充正文，不是新標題。",
        "概念機制" + newline + '合成段落乙，保留跳脫 <script>alert("fixture")</script>。',
    ]
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE ideas SET paid_content = ? WHERE slug = ?", (separator.join(paragraphs), SLUG))
        connection.commit()
    body = client.get("/library/orders/" + order_no).get_data(as_text=True)
    headings = re.findall(r'<section class="v34-reader-section">\s*<h3>(.*?)</h3>', body, re.S)
    assert headings == ["概念原點", "概念機制"]
    assert '<p class="manuscript-copy">這是補充正文，不是新標題。</p>' in body
    assert "合成段落甲。" in body
    assert '保留跳脫 <script>' not in body
    assert '保留跳脫 &lt;script&gt;' in body
    assert all(line in html.unescape(body) for paragraph in paragraphs for line in paragraph.splitlines())


@pytest.mark.parametrize("status", ("pending", "cancelled", "refunded"))
def test_v14_removed_entitlement_immediately_blocks_content_and_all_images(v14_reader, app, status):
    client, order_no, idea = v14_reader
    # Fixture-only entitlement changes; no refund/payment APIs or external effects.
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE orders SET status = ? WHERE order_no = ?", (status, order_no))
        connection.commit()
    reading = client.get("/library/orders/" + order_no)
    assert reading.status_code in (302, 404)
    assert 'class="manuscript-copy"' not in reading.get_data(as_text=True)
    for slot in SLOTS:
        for method in ("GET", "HEAD"):
            response = client.open(f"/library/assets/{idea['id']}/{slot}", method=method)
            assert response.status_code == 404
            assert "no-store" in response.headers["Cache-Control"]
            assert not response.data.startswith(b"RIFF")


def test_v14_upgrade_and_restarts_preserve_previous_content_and_pricing(app):
    with app.app_context():
        connection = get_db()
        # Reconstruct the already-migrated V33 fixture without touching real data.
        connection.execute("DELETE FROM ideas WHERE slug = ?", (SLUG,))
        old_slugs = tuple(seed["slug"] for seed in BLINDBOX_SEEDS if seed["slug"] != SLUG)
        assert len(old_slugs) == 13
        connection.execute(
            "UPDATE ideas SET paid_content = ?, price_override = ? WHERE slug = ?",
            ("保留既有管理者編修的完整內容", 731, old_slugs[0]),
        )
        connection.execute("UPDATE settings SET value = '863' WHERE key = 'idea_price'")
        connection.commit()
        previous = {
            row["slug"]: dict(row)
            for row in connection.execute("SELECT * FROM ideas WHERE published = 1").fetchall()
        }
        settings = [dict(row) for row in connection.execute("SELECT * FROM settings ORDER BY key").fetchall()]
        assert set(previous) == set(old_slugs)

        # The first start inserts only V34; the second must be fully idempotent.
        init_db()
        first_start = [dict(row) for row in connection.execute("SELECT * FROM ideas ORDER BY id").fetchall()]
        assert connection.execute("SELECT COUNT(*) FROM ideas WHERE slug = ?", (SLUG,)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM ideas WHERE published = 1").fetchone()[0] == 14
        for slug, original in previous.items():
            assert dict(connection.execute("SELECT * FROM ideas WHERE slug = ?", (slug,)).fetchone()) == original
        assert [dict(row) for row in connection.execute("SELECT * FROM settings ORDER BY key").fetchall()] == settings
        assert connection.execute("SELECT price_override FROM ideas WHERE slug = ?", (SLUG,)).fetchone()[0] is None

        init_db()
        assert [dict(row) for row in connection.execute("SELECT * FROM ideas ORDER BY id").fetchall()] == first_start
        assert [dict(row) for row in connection.execute("SELECT * FROM settings ORDER BY key").fetchall()] == settings
