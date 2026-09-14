"""V35 delivery authorization and V36 storyboard introduction regressions.

Checkout, payment, access and revocation use only the isolated test database,
mock payment provider and local outbox. No production customer data is used.
"""

import hashlib
import html
import json
from html.parser import HTMLParser
from pathlib import Path

import pytest

from test_relock_v34 import _activate_synthetic_reader, _v14_idea, _webp_dimensions
from tianwai.db import BLINDBOX_SEEDS, get_db, init_db, utc_now


SLUG = "sealed-concept-v14"
INTRODUCTION = "brand/concepts/v36-14-introduction.webp"
OLD_SLOTS = ("hero", "diagram", "scene")
OLD_SLUGS = tuple(seed["slug"] for seed in BLINDBOX_SEEDS if seed["slug"] != SLUG)
REQUEST_HEADERS = (
    {},
    {"Range": "bytes=0-31"},
    {"If-None-Match": "*"},
    {"If-Modified-Since": "Wed, 31 Dec 2099 23:59:59 GMT"},
)


class _ReaderElements(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.elements = []
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def _guide():
    from tianwai.concept_guides import get_concept_guide

    return get_concept_guide(SLUG)


def _private_guide_text(guide):
    yield from (guide["title"], guide["lead"], guide["caption"], guide["state_summary"], guide["boundary"])
    for step in guide["steps"]:
        yield step["title"]
        yield step["body"]
    for scenario in guide["validation_scenarios"]:
        yield scenario["title"]
        yield scenario["body"]


def _assert_denied(response):
    assert response.status_code == 404
    assert "no-store" in response.headers.get("Cache-Control", "")
    assert response.mimetype != "image/webp"
    assert not response.data.startswith(b"RIFF")
    for header in ("ETag", "Last-Modified", "Content-Range"):
        assert header not in response.headers


@pytest.fixture
def introduction_reader(app, client):
    idea = _v14_idea(app)
    return client, _activate_synthetic_reader(client, SLUG), idea


def test_introduction_registry_is_pure_complete_and_limited_to_volume_14():
    # These calls intentionally run without a Flask app/request context or DB.
    from tianwai.concept_guides import (
        CONCEPT_GUIDES,
        RETIRED_GUIDE_ASSETS,
        get_concept_guide,
        supplemental_asset_identifiers,
    )

    assert set(CONCEPT_GUIDES) == {SLUG}
    guide = get_concept_guide(SLUG)
    assert isinstance(guide, dict)
    assert guide["asset"] == INTRODUCTION
    for key in ("title", "lead", "caption", "state_summary", "boundary"):
        assert isinstance(guide[key], str) and guide[key].strip()
    assert isinstance(guide["steps"], tuple) and len(guide["steps"]) == 7
    for step in guide["steps"]:
        assert isinstance(step, dict)
        assert isinstance(step["title"], str) and step["title"].strip()
        assert isinstance(step["body"], str) and step["body"].strip()
    scenarios = guide["validation_scenarios"]
    assert isinstance(scenarios, tuple) and len(scenarios) == 3
    for scenario in scenarios:
        assert set(scenario) == {"title", "body"}
        assert "待驗證模擬情境" in scenario["title"]
        assert isinstance(scenario["body"], str) and scenario["body"].strip()
    assert RETIRED_GUIDE_ASSETS == ("brand/concepts/v35-14-introduction.webp",)
    identifiers = supplemental_asset_identifiers()
    assert isinstance(identifiers, (list, tuple))
    assert tuple(identifiers) == (INTRODUCTION,)
    assert not get_concept_guide("unknown-synthetic-volume")
    assert len(OLD_SLUGS) == 13
    assert all(not get_concept_guide(slug) for slug in OLD_SLUGS)


def test_introduction_does_not_replace_existing_art_or_add_schema(app):
    idea = _v14_idea(app)
    assert tuple(idea[slot + "_image"] for slot in OLD_SLOTS) == tuple(
        f"brand/concepts/v34-14-{slot}.webp" for slot in OLD_SLOTS
    )
    with app.app_context():
        columns = {row["name"] for row in get_db().execute("PRAGMA table_info(ideas)")}
    assert not any("introduction" in column or "guide" in column for column in columns)


def test_v36_storyboard_keeps_uncertainty_and_research_exceptions_explicit():
    guide = _guide()
    assert tuple(step["title"].split("：", 1)[0] for step in guide["steps"]) == (
        "正常行駛", "疑似碰撞", "資料品質與事件判讀", "維持事件後移動限制",
        "駕駛再次請求", "獨立重新授權檢查", "重新授權後持續觀察",
    )
    assert "保留為未知" in guide["steps"][2]["body"]
    assert "不表示車輛會自動停下" in guide["steps"][3]["body"]
    assert "不是解鎖條件" in guide["steps"][4]["body"]
    assert "判讀結果不能自行解鎖" in guide["steps"][5]["body"]
    assert "未知，回到維持限制" in guide["state_summary"]
    assert "新事件也必須回到事件評估" in guide["state_summary"]
    assert "不是必經狀態或預設放行" in guide["state_summary"]
    assert not any("條件慢移" in step["title"] for step in guide["steps"])
    assert "不是主流程的必經步驟或安全保證" in guide["boundary"]
    assert "不代表已能辨識人體" in guide["validation_scenarios"][0]["body"]
    assert "不能因場景標為紙箱就預先判定安全" in guide["validation_scenarios"][1]["body"]
    assert "尚無實測成功或不誤判的證據" in guide["validation_scenarios"][2]["body"]
    copy = "".join(_private_guide_text(guide))
    for unsupported in ("94%", "5%", "5 km/h", "自動停止", "安全慢移"):
        assert unsupported not in copy


def test_introduction_is_a_real_compact_portrait_private_webp(app):
    asset = Path(app.config["PRIVATE_ASSET_ROOT"]) / INTRODUCTION
    assert asset.is_file(), "V36 introduction image generation is not yet complete"
    assert not (Path(app.static_folder) / INTRODUCTION).exists()
    data = asset.read_bytes()
    assert 0 < len(data) <= 2_000_000
    assert _webp_dimensions(data) == (2048, 2560)


def test_introduction_never_leaks_into_public_catalog_or_checkout(client):
    guide = _guide()
    paths = ["/", "/api/ideas"]
    paths.extend("/ideas/" + seed["slug"] for seed in BLINDBOX_SEEDS)
    paths.extend("/checkout/" + seed["slug"] for seed in BLINDBOX_SEEDS)
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200
        body = (
            json.dumps(response.get_json(), ensure_ascii=False)
            if response.is_json else html.unescape(response.get_data(as_text=True))
        )
        assert INTRODUCTION not in body
        assert "/library/assets/" not in body
        assert 'id="concept-introduction"' not in body
        # A generic short heading may also appear publicly; the substantive
        # introduction copy must only be exposed after the buyer is authorized.
        for text in (
            guide["lead"], guide["caption"], guide["state_summary"], guide["boundary"],
            *(step["body"] for step in guide["steps"]),
            *(scenario["body"] for scenario in guide["validation_scenarios"]),
            *(scenario["title"] for scenario in guide["validation_scenarios"]),
        ):
            assert text not in body


@pytest.mark.parametrize("method", ("GET", "HEAD"))
def test_public_introduction_asset_alias_stays_denied_with_range_and_conditionals(client, method):
    for headers in REQUEST_HEADERS:
        _assert_denied(client.open("/static/" + INTRODUCTION, method=method, headers=headers))
        direct = client.open("/private_assets/" + INTRODUCTION, method=method, headers=headers)
        assert direct.status_code == 404
        assert not direct.data.startswith(b"RIFF")


def test_accidental_public_introduction_copy_is_denied(app, client, tmp_path):
    copied_static = tmp_path / "public"
    copied_asset = copied_static / INTRODUCTION
    copied_asset.parent.mkdir(parents=True)
    copied_asset.write_bytes(b"RIFF-synthetic-private-image-never-serve")
    app.static_folder = str(copied_static)
    for method in ("GET", "HEAD"):
        _assert_denied(client.open("/static/" + INTRODUCTION, method=method))


@pytest.mark.parametrize("method", ("GET", "HEAD"))
def test_anonymous_introduction_get_head_range_and_conditionals_are_denied(app, client, method):
    idea = _v14_idea(app)
    for headers in REQUEST_HEADERS:
        _assert_denied(client.open(
            f"/library/assets/{idea['id']}/introduction", method=method, headers=headers,
        ))


def test_correct_buyer_reads_complete_introduction_bytes_without_reusable_cache(introduction_reader, app):
    client, _order_no, idea = introduction_reader
    expected = Path(app.config["PRIVATE_ASSET_ROOT"]) / INTRODUCTION
    assert expected.is_file(), "V36 introduction image generation is not yet complete"
    expected_bytes = expected.read_bytes()
    expected_hash = hashlib.sha256(expected_bytes).digest()
    for method in ("GET", "HEAD"):
        for headers in REQUEST_HEADERS:
            response = client.open(
                f"/library/assets/{idea['id']}/introduction", method=method, headers=headers,
            )
            assert response.status_code == 200
            assert response.mimetype == "image/webp"
            assert "no-store" in response.headers["Cache-Control"]
            assert response.headers["Referrer-Policy"] == "no-referrer"
            assert "Cookie" in response.headers.get("Vary", "")
            assert int(response.headers["Content-Length"]) == len(expected_bytes)
            for header in ("ETag", "Last-Modified", "Content-Range"):
                assert header not in response.headers
            if method == "GET":
                assert hashlib.sha256(response.data).digest() == expected_hash
            else:
                assert response.data == b""


def test_paid_reader_gets_guide_text_navigation_lightbox_and_original_three_images(introduction_reader):
    client, order_no, idea = introduction_reader
    response = client.get("/library/orders/" + order_no)
    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
    body = response.get_data(as_text=True)
    unescaped = html.unescape(body)
    guide = _guide()
    for text in _private_guide_text(guide):
        assert text in unescaped
    elements = _ReaderElements(body).elements
    assert sum(attrs.get("id") == "concept-introduction" for _, attrs in elements) == 1
    assert any(tag == "a" and attrs.get("href") == "#concept-introduction" for tag, attrs in elements)
    image_path = f"/library/assets/{idea['id']}/introduction"
    assert any(
        tag == "a" and attrs.get("href") == image_path and "data-flow-image" in attrs
        for tag, attrs in elements
    )
    assert sum(tag == "img" and attrs.get("src") == image_path for tag, attrs in elements) == 1
    assert any(
        tag == "a" and attrs.get("href") == image_path
        and attrs.get("target") == "_blank" and "noopener" in attrs.get("rel", "")
        and "data-flow-image" not in attrs
        for tag, attrs in elements
    ), "Portrait details must also open in the browser's zoomable image viewer"
    assert sum(
        tag == "img" and attrs.get("src", "").startswith(f"/library/assets/{idea['id']}/")
        for tag, attrs in elements
    ) == 4
    for slot in OLD_SLOTS:
        old_path = f"/library/assets/{idea['id']}/{slot}"
        assert any(tag == "img" and attrs.get("src") == old_path for tag, attrs in elements)
        assert idea[slot + "_caption"] in unescaped
        assert idea[slot + "_image"] not in body
    assert INTRODUCTION not in body
    assert sum(tag == "dialog" and "data-flow-image-dialog" in attrs for tag, attrs in elements) == 1
    # Keep the original written delivery alongside the new introduction.
    for line in idea["paid_content"].strip().splitlines():
        if line:
            assert line in unescaped


@pytest.mark.parametrize("slug", OLD_SLUGS)
def test_each_previous_volume_has_no_introduction_and_cannot_access_volume_14(app, client, slug):
    v14 = _v14_idea(app)
    order_no = _activate_synthetic_reader(client, slug)
    with app.app_context():
        previous_id = get_db().execute("SELECT id FROM ideas WHERE slug = ?", (slug,)).fetchone()["id"]
    reading = client.get("/library/orders/" + order_no)
    assert reading.status_code == 200
    body = reading.get_data(as_text=True)
    assert 'class="manuscript-copy"' in body
    assert "concept-introduction" not in body
    assert "/introduction" not in body
    for idea_id in (previous_id, v14["id"]):
        for method in ("GET", "HEAD"):
            _assert_denied(client.open(
                f"/library/assets/{idea_id}/introduction",
                method=method, headers={"Range": "bytes=0-31"},
            ))


@pytest.mark.parametrize("state", (
    "pending", "cancelled", "refunded", "wrong_owner", "revoked_session", "revoked_device",
))
def test_entitlement_session_or_device_revocation_immediately_denies_introduction(introduction_reader, app, state):
    client, order_no, idea = introduction_reader
    asset_path = f"/library/assets/{idea['id']}/introduction"
    # Confirm this exact reader could obtain the asset before changing only its
    # isolated entitlement/session/device record; there is no real refund call.
    assert client.get(asset_path).status_code == 200
    with app.app_context():
        connection = get_db()
        if state in {"pending", "cancelled", "refunded"}:
            connection.execute("UPDATE orders SET status = ? WHERE order_no = ?", (state, order_no))
        elif state == "wrong_owner":
            connection.execute(
                "UPDATE orders SET customer_email = ? WHERE order_no = ?",
                ("other-synthetic-reader@example.invalid", order_no),
            )
        elif state == "revoked_session":
            connection.execute("UPDATE customer_sessions SET revoked_at = ?", (utc_now(),))
        elif state == "revoked_device":
            connection.execute("UPDATE customer_devices SET revoked_at = ?", (utc_now(),))
        connection.commit()
    for method in ("GET", "HEAD"):
        for headers in REQUEST_HEADERS:
            _assert_denied(client.open(asset_path, method=method, headers=headers))
    reading = client.get("/library/orders/" + order_no)
    assert reading.status_code in (302, 404)
    assert 'id="concept-introduction"' not in reading.get_data(as_text=True)


def test_introduction_lookup_uses_authorized_database_slug(introduction_reader, app):
    client, order_no, idea = introduction_reader
    asset_path = f"/library/assets/{idea['id']}/introduction"
    assert client.get(asset_path).status_code == 200
    with app.app_context():
        connection = get_db()
        connection.execute(
            "UPDATE ideas SET slug = ? WHERE id = ?", ("synthetic-no-guide-volume", idea["id"]),
        )
        connection.commit()
    # ID, title and the paid order remain the same. A removed registry mapping
    # must stop the extra image without disabling the original purchased text.
    _assert_denied(client.get(asset_path))
    reading = client.get("/library/orders/" + order_no)
    assert reading.status_code == 200
    body = reading.get_data(as_text=True)
    assert 'class="manuscript-copy"' in body
    assert "concept-introduction" not in body
    for slot in OLD_SLOTS:
        assert client.get(f"/library/assets/{idea['id']}/{slot}").status_code == 200


@pytest.mark.parametrize("custom_fields", ((), ("paid_content",), ("deliverables",), ("paid_content", "deliverables")))
def test_v35_copy_upgrade_is_exact_per_field_and_preserves_custom_edits(app, custom_fields):
    from tianwai.v34_catalog import V35_RELOCK_COPY_UPDATES

    with app.app_context():
        connection = get_db()
        others_before = [dict(row) for row in connection.execute("SELECT * FROM ideas WHERE slug != ? ORDER BY id", (SLUG,))]
        settings_before = [dict(row) for row in connection.execute("SELECT * FROM settings ORDER BY key")]
        expected = {}
        for field, previous, current in V35_RELOCK_COPY_UPDATES:
            value = "保留本卷自訂編修文字" if field in custom_fields else previous
            connection.execute(f"UPDATE ideas SET {field} = ? WHERE slug = ?", (value, SLUG))
            expected[field] = value if field in custom_fields else current
        connection.commit()
        init_db()
        actual = dict(connection.execute("SELECT * FROM ideas WHERE slug = ?", (SLUG,)).fetchone())
        for field, value in expected.items():
            assert actual[field] == value
        assert [dict(row) for row in connection.execute("SELECT * FROM ideas WHERE slug != ? ORDER BY id", (SLUG,))] == others_before
        assert [dict(row) for row in connection.execute("SELECT * FROM settings ORDER BY key")] == settings_before
        init_db()
        assert dict(connection.execute("SELECT * FROM ideas WHERE slug = ?", (SLUG,)).fetchone()) == actual
