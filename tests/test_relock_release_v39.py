"""Fourteenth-volume release gates; only disposable synthetic prices and data."""

from copy import deepcopy
import re

import pytest

from conftest import login_admin, set_public_csrf
from tianwai.commerce import PRICING_BATCH_SLUGS
from tianwai.concept_guides import get_concept_guide
from tianwai.db import get_db
from tianwai.release_packages import get_release_package, release_package_status


RELOCK = "sealed-concept-v14"


@pytest.fixture
def relock_catalog(app):
    with app.app_context():
        connection = get_db()
        # The shared fixture supplies synthetic prices; retain those, never real ones.
        connection.execute("UPDATE ideas SET sale_state = 'preparing', release_ready = 0")
        connection.commit()
        return {row["slug"]: row["id"] for row in connection.execute("SELECT id, slug FROM ideas")}


def _rows(app):
    with app.app_context():
        return [dict(row) for row in get_db().execute("SELECT * FROM ideas ORDER BY id")]


def _publish(client, csrf, idea_id=None, payload=None):
    url = f"/admin/api/ideas/{idea_id}/publish-package" if idea_id else "/admin/api/release-packages/publish"
    return client.post(url, json={"confirm_publication": True} if payload is None else payload, headers={"X-CSRF-Token": csrf})


def test_real_fourteen_inventory_reports_actual_relock_format(app, client, relock_catalog):
    assert len(PRICING_BATCH_SLUGS) == len(set(PRICING_BATCH_SLUGS)) == 14
    assert PRICING_BATCH_SLUGS[-1] == RELOCK and get_release_package(RELOCK) is None
    login_admin(client)
    response = client.get("/admin/api/release-packages")
    assert response.status_code == 200
    assert response.json["counts"] == {"total": 14, "ready": 14, "listed": 0, "blocked": 0}
    assert response.json["excluded_count"] == 0 and response.json["can_publish_all"] is True
    card = response.json["cards"][-1]
    guide = get_concept_guide(RELOCK)
    assert card["package"] == {"format": "concept_guide", "title": guide["title"], "scope": guide["lead"], "boundary": guide["boundary"]}
    assert card["package_status"]["counts"] == {
        "figures": 4, "flow_steps": 7, "mvp_steps": 6, "tests": 3,
        "specs": 0, "worksheets": 0, "handoff": 0, "sources": 0,
    }
    assert card["commerce"]["in_pricing_batch"] is True
    assert card["commerce"]["release_ready"] is card["commerce"]["can_purchase"] is False
    assert all(item["package"]["format"] == "research_package" for item in response.json["cards"][:13])
    assert "no-store" in response.headers["Cache-Control"]


@pytest.mark.parametrize("field", ["title", "lead", "caption", "state_summary", "boundary", "asset", "steps", "validation_scenarios"])
def test_missing_guide_field_blocks_single_and_entire_batch_without_writes(app, client, relock_catalog, monkeypatch, field):
    from tianwai import concept_guides

    guide = deepcopy(get_concept_guide(RELOCK))
    guide.pop(field)
    monkeypatch.setitem(concept_guides.CONCEPT_GUIDES, RELOCK, guide)
    csrf = login_admin(client)
    before = _rows(app)
    for idea_id in (relock_catalog[RELOCK], None):
        response = _publish(client, csrf, idea_id)
        assert response.status_code == 409
        assert response.json["gaps"][-1]["slug"] == RELOCK
        assert _rows(app) == before
    assert client.get("/admin/api/release-packages").json["can_publish_all"] is False


@pytest.mark.parametrize("mutation", ["missing_guide", "wrong_guide_type", "short_steps", "empty_step", "duplicate_steps", "extra_scenario", "empty_scenario", "duplicate_scenarios", "missing_introduction", "escaped_introduction", "duplicate_asset"])
def test_malformed_guide_and_fourth_asset_fail_closed(app, client, relock_catalog, monkeypatch, mutation):
    from tianwai import concept_guides

    guide = deepcopy(get_concept_guide(RELOCK))
    if mutation == "missing_guide":
        guide = None
    elif mutation == "wrong_guide_type":
        guide = "not a guide"
    elif mutation == "short_steps":
        guide["steps"] = guide["steps"][:-1]
    elif mutation == "empty_step":
        guide["steps"][0]["body"] = " "
    elif mutation == "duplicate_steps":
        guide["steps"][1]["title"] = guide["steps"][0]["title"]
    elif mutation == "extra_scenario":
        guide["validation_scenarios"] += (guide["validation_scenarios"][0],)
    elif mutation == "empty_scenario":
        guide["validation_scenarios"][0]["body"] = ""
    elif mutation == "duplicate_scenarios":
        guide["validation_scenarios"][1]["title"] = guide["validation_scenarios"][0]["title"]
    elif mutation == "missing_introduction":
        guide["asset"] = "brand/concepts/synthetic-missing-v39.webp"
    elif mutation == "escaped_introduction":
        guide["asset"] = "brand/../../outside.webp"
    else:
        guide["asset"] = next(row for row in _rows(app) if row["slug"] == RELOCK)["hero_image"]
    monkeypatch.setitem(concept_guides.CONCEPT_GUIDES, RELOCK, guide)
    csrf = login_admin(client)
    before = _rows(app)
    assert _publish(client, csrf).status_code == 409
    assert _rows(app) == before
    card = client.get("/admin/api/release-packages").json["cards"][-1]
    assert card["package_status"]["ready"] is False and card["package_status"]["gaps"]
    if mutation in {"missing_introduction", "escaped_introduction", "missing_guide", "wrong_guide_type"}:
        assert client.get(f"/admin/ideas/{relock_catalog[RELOCK]}/assets/introduction").status_code == 404


@pytest.mark.parametrize("section", [*(f"Micro-MVP｜步驟 {n}｜" for n in range(1, 7)), "模組與圖號對照", "狀態與人工操作", "測試空白紀錄", "限制與未知", "安全與使用邊界"])
def test_missing_manuscript_section_blocks_all_volumes(app, client, relock_catalog, section):
    with app.app_context():
        connection = get_db()
        row = connection.execute("SELECT * FROM ideas WHERE slug = ?", (RELOCK,)).fetchone()
        blocks = row["paid_content"].split("\n\n")
        assert sum(block.startswith(section) for block in blocks) == 1
        manuscript = "\n\n".join(block for block in blocks if not block.startswith(section))
        connection.execute("UPDATE ideas SET paid_content = ? WHERE slug = ?", (manuscript, RELOCK))
        connection.commit()
    csrf = login_admin(client)
    before = _rows(app)
    assert _publish(client, csrf).status_code == 409
    assert _rows(app) == before


def test_fourteenth_preview_is_complete_private_and_reads_no_customer_tables(app, client, relock_catalog, monkeypatch):
    from tianwai import admin

    idea_id = relock_catalog[RELOCK]
    assert client.get(f"/admin/ideas/{idea_id}/preview").status_code == 302
    login_admin(client)
    captured, statements = {}, []
    def render(template, **context):
        assert template == "admin_package_preview.html"
        captured.update(context)
        return "synthetic-admin-preview"
    monkeypatch.setattr(admin, "render_template", render)
    with app.app_context():
        get_db().set_trace_callback(statements.append)
        result = client.get(f"/admin/ideas/{idea_id}/preview")
    assert result.status_code == 200 and "no-store" in result.headers["Cache-Control"]
    assert result.headers["Referrer-Policy"] == "no-referrer" and "Cookie" in result.headers["Vary"]
    assert captured["package"] is None and captured["concept_guide"] == get_concept_guide(RELOCK)
    assert set(captured["asset_urls"]) == {"hero", "diagram", "scene", "introduction"}
    assert "Micro-MVP｜步驟 6｜" in captured["idea"]["paid_content"]
    assert not any(re.search(r"\b(?:FROM|JOIN)\s+(?:orders|customers|customer_devices|customer_sessions|activation_codes)\b", sql, re.I) for sql in statements)


@pytest.mark.parametrize("slot", ["hero", "diagram", "scene", "introduction"])
def test_fourteenth_assets_require_live_auth_and_ignore_conditional_cache(client, relock_catalog, slot):
    path = f"/admin/ideas/{relock_catalog[RELOCK]}/assets/{slot}"
    assert client.get(path).status_code == 302
    csrf = login_admin(client)
    response = client.get(path, headers={"Range": "bytes=0-4", "If-None-Match": '"synthetic"', "If-Modified-Since": "Wed, 01 Jan 2099 00:00:00 GMT"})
    assert response.status_code == 200 and response.mimetype.startswith("image/")
    assert len(response.data) > 5 and "ETag" not in response.headers and "Last-Modified" not in response.headers
    assert "no-store" in response.headers["Cache-Control"] and response.headers["Referrer-Policy"] == "no-referrer"
    assert "Cookie" in response.headers["Vary"]
    assert client.head(path).status_code == 200
    client.post("/admin/logout", data={"csrf_token": csrf})
    assert client.head(path).status_code == 302


def test_fourteenth_single_listing_preserves_first_thirteen_then_batch_is_atomic_and_idempotent(app, client, relock_catalog):
    csrf = login_admin(client)
    before = _rows(app)
    idea_id = relock_catalog[RELOCK]
    result = _publish(client, csrf, idea_id)
    assert result.status_code == 200 and result.json["changed_count"] == result.json["published_count"] == 1
    after_single = _rows(app)
    for old, new in zip(before, after_single):
        if old["slug"] != RELOCK:
            assert old == new
        else:
            assert new["sale_state"] == "price_listed" and new["release_ready"] == 0
            assert all(old[key] == new[key] for key in old.keys() - {"sale_state", "updated_at"})
    assert _publish(client, csrf, idea_id).json["changed_count"] == 0
    batch = _publish(client, csrf)
    assert batch.status_code == 200 and batch.json["changed_count"] == 13 and batch.json["published_count"] == 14
    after_batch = _rows(app)
    assert _publish(client, csrf).json["changed_count"] == 0 and _rows(app) == after_batch
    assert all(not idea["can_purchase"] for idea in app.test_client().get("/api/ideas").json["ideas"])


def test_fourteenth_publish_requires_admin_csrf_and_strict_confirmation(app, client, relock_catalog):
    idea_id = relock_catalog[RELOCK]
    before = _rows(app)
    assert _publish(client, "none", idea_id).status_code == 401
    csrf = login_admin(client)
    assert _publish(client, "wrong", idea_id).status_code == 403
    for data in ({}, {"confirm_publication": False}, {"confirm_publication": 1}, {"confirm_publication": "true"}, {"confirm_publication": True, "release_ready": True}):
        assert _publish(client, csrf, idea_id, data).status_code == 400
    assert _rows(app) == before


def test_fifteenth_volume_cannot_enter_commerce_listing_preview_or_assets(app, client, relock_catalog):
    with app.app_context():
        connection = get_db()
        row = connection.execute("SELECT * FROM ideas WHERE slug = ?", (RELOCK,)).fetchone()
        fields = [field for field in row.keys() if field != "id"]
        values = ["sealed-concept-v15" if field == "slug" else row[field] for field in fields]
        cursor = connection.execute(f"INSERT INTO ideas ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})", values)
        idea_id = cursor.lastrowid
        connection.commit()
        unknown = connection.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        assert release_package_status(unknown, {"ready": True})["ready"] is False
    csrf = login_admin(client)
    before = _rows(app)
    assert _publish(client, csrf, idea_id).status_code == 404
    assert client.post(f"/admin/api/ideas/{idea_id}/commerce", json={"prepared_price": row["prepared_price"], "sale_state": "preparing", "release_ready": False}, headers={"X-CSRF-Token": csrf}).status_code == 409
    assert client.get(f"/admin/ideas/{idea_id}/preview").status_code == 404
    for slot in ("hero", "diagram", "scene", "introduction"):
        assert client.get(f"/admin/ideas/{idea_id}/assets/{slot}").status_code == 404
    assert _rows(app) == before


def test_fourteenth_listing_preserves_preexisting_paid_order_and_entitlement(app, client, relock_catalog):
    from test_customer_access import _pay_and_get_activation

    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE ideas SET sale_state = 'for_sale', release_ready = 1 WHERE slug = ?", (PRICING_BATCH_SLUGS[0],))
        connection.commit()
    order, activation_link, activation_code = _pay_and_get_activation(client)
    assert client.post(activation_link, data={"csrf_token": set_public_csrf(client), "activation_code": activation_code}).status_code == 302
    with app.app_context():
        before = dict(get_db().execute("SELECT * FROM orders WHERE order_no = ?", (order["order_no"],)).fetchone())
    admin_client = app.test_client()
    csrf = login_admin(admin_client)
    assert _publish(admin_client, csrf, relock_catalog[RELOCK]).status_code == 200
    with app.app_context():
        assert dict(get_db().execute("SELECT * FROM orders WHERE order_no = ?", (order["order_no"],)).fetchone()) == before
    assert client.get("/library/orders/" + order["order_no"]).status_code == 200
