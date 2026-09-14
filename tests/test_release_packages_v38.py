"""Private V38 preview and publication checks with synthetic data only."""

import re
import sqlite3

import pytest

from conftest import login_admin
from tianwai.commerce import PRICING_BATCH_SLUGS
from tianwai.db import get_db
from tianwai.release_packages import get_release_package, release_package_status, release_package_structure_gaps


def _synthetic_package():
    return {
        "title": "合成驗收套件", "scope": "合成圖文、規格與工作表", "boundary": "尚未實作或驗證；僅供合成驗收。",
        "flow_steps": [{"title": f"步驟 {i}", "body": "合成說明", "input": "合成輸入", "output": "合成輸出"} for i in range(6)],
        "figure_notes": {slot: "合成圖說" for slot in ("hero", "diagram", "scene")},
        "specs": [{"item": f"規格 {i}", "proposal": "概念提案", "verify": "待驗證"} for i in range(5)],
        "mvp_steps": [{"title": f"MVP {i}", "action": "合成行動", "record": "待填記錄", "stop": "不合條件即停止"} for i in range(6)],
        "tests": [{"case": f"案例 {i}", "setup": "合成設定", "expected": "預期非實測", "record": "未執行"} for i in range(6)],
        "handoff": [{"item": f"交付 {i}", "example": "示例", "fill_in": "後續待填"} for i in range(5)],
        "worksheets": [{"title": f"工作表 {i}", "columns": ["項目", "结果"], "rows": [["合成示例", ""]]} for i in range(3)],
        "sources": [{"label": "合成參考", "url": "https://example.com/docs", "note": "測試不會連網"}],
    }


@pytest.fixture
def release_catalog(app, monkeypatch):
    from tianwai import admin, release_packages

    packages = {slug: _synthetic_package() for slug in PRICING_BATCH_SLUGS[:13]}
    getter = lambda slug: packages.get(slug)
    monkeypatch.setattr(release_packages, "get_release_package", getter)
    monkeypatch.setattr(admin, "get_release_package", getter)
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE ideas SET prepared_price = NULL, sale_state = 'preparing', release_ready = 0")
        for index, slug in enumerate(PRICING_BATCH_SLUGS):
            connection.execute("UPDATE ideas SET prepared_price = ?, workflow_status = 'published', published = 1 WHERE slug = ?", (7821 + index, slug))
        connection.commit()
        ids = {row["slug"]: row["id"] for row in connection.execute("SELECT id, slug FROM ideas")}
    return {"app": app, "packages": packages, "ids": ids}


def _post(client, csrf, idea_id=None, data=None):
    path = f"/admin/api/ideas/{idea_id}/publish-package" if idea_id is not None else "/admin/api/release-packages/publish"
    return client.post(path, json={"confirm_publication": True} if data is None else data, headers={"X-CSRF-Token": csrf})


def _rows(app):
    with app.app_context():
        return [dict(row) for row in get_db().execute("SELECT * FROM ideas ORDER BY id")]


def test_actual_editorial_packages_cover_exact_first_thirteen_and_are_structurally_complete():
    for slug in PRICING_BATCH_SLUGS[:13]:
        package = get_release_package(slug)
        assert not release_package_structure_gaps(package), slug
    assert get_release_package("sealed-concept-v14") is None
    assert get_release_package("../../private") is None


@pytest.mark.parametrize("field", ["title", "scope", "boundary", "flow_steps", "figure_notes", "specs", "mvp_steps", "tests", "handoff", "worksheets", "sources"])
def test_missing_package_sections_fail_closed(field):
    package = _synthetic_package()
    package.pop(field)
    assert release_package_structure_gaps(package)


@pytest.mark.parametrize("mutation", ["short_flow", "short_mvp", "empty_input", "bad_source", "source_credentials", "bad_table_width", "dict_row", "duplicate_columns"])
def test_malformed_package_sections_fail_closed(mutation):
    package = _synthetic_package()
    if mutation == "short_flow":
        package["flow_steps"].pop()
    elif mutation == "short_mvp":
        package["mvp_steps"].pop()
    elif mutation == "empty_input":
        package["flow_steps"][0]["input"] = " "
    elif mutation == "bad_source":
        package["sources"][0]["url"] = "javascript:alert(1)"
    elif mutation == "source_credentials":
        package["sources"][0]["url"] = "https://synthetic:synthetic@example.com/"
    elif mutation == "bad_table_width":
        package["worksheets"][0]["rows"] = [["only one cell"]]
    elif mutation == "dict_row":
        package["worksheets"][0]["rows"] = [{"項目": "合成示例", "结果": ""}]
    else:
        package["worksheets"][0]["columns"] = ["重複", "重複"]
    assert release_package_structure_gaps(package)


def test_release_inventory_requires_admin_and_avoids_customer_tables(app, client, release_catalog):
    anonymous = client.get("/admin/api/release-packages")
    assert anonymous.status_code == 401
    assert "no-store" in anonymous.headers["Cache-Control"]
    login_admin(client)
    statements = []
    with app.app_context():
        get_db().set_trace_callback(statements.append)
        result = client.get("/admin/api/release-packages")
    assert result.status_code == 200
    assert "no-store" in result.headers["Cache-Control"]
    assert result.headers["Referrer-Policy"] == "no-referrer"
    assert "Cookie" in result.headers["Vary"]
    body = result.json
    assert len(body["cards"]) == 14
    assert body["excluded_count"] == 0 and body["counts"]["ready"] == 14
    assert body["can_publish_all"] is True
    assert [card["package_status"]["counts"]["figures"] for card in body["cards"]] == [3] * 13 + [4]
    assert all(not card["commerce"]["can_purchase"] for card in body["cards"])
    assert all(card["prepared_price"] >= 7821 for card in body["cards"])
    assert not any(re.search(r"\b(?:FROM|JOIN)\s+(?:orders|customers|customer_devices|customer_sessions|activation_codes)\b", sql, re.I) for sql in statements)
    for private_body in ("paid_content", "raw_idea", "customer_email", "payment_token", "hero_image"):
        assert private_body not in result.get_data(as_text=True)


def test_one_click_publication_requires_csrf_and_explicit_boolean(client, release_catalog):
    assert _post(client, "none").status_code == 401
    csrf = login_admin(client)
    assert _post(client, "wrong").status_code == 403
    for data in ({}, {"confirm_publication": False}, {"confirm_publication": 1}, {"confirm_publication": "true"}, {"confirm_publication": True, "prepared_price": 7821}):
        assert _post(client, csrf, data=data).status_code == 400


def test_package_status_distinguishes_editorial_readiness_from_payment(app, release_catalog):
    with app.app_context():
        idea = get_db().execute("SELECT * FROM ideas WHERE slug = ?", (PRICING_BATCH_SLUGS[0],)).fetchone()
        status = release_package_status(idea, {"ready": False})
    assert status["ready"] is True and status["gaps"] == []
    assert status["counts"] == {"flow_steps": 6, "specs": 5, "mvp_steps": 6, "tests": 6, "handoff": 5, "sources": 1, "worksheets": 3, "figures": 3}
    assert status["commerce"]["release_ready"] is False
    assert status["commerce"]["can_purchase"] is False


@pytest.mark.parametrize("missing", ["prepared_price", "paid_content", "workflow_status", "hero_image", "diagram_image", "scene_image", "package"])
def test_one_incomplete_volume_blocks_entire_batch_atomically(app, client, release_catalog, missing):
    csrf = login_admin(client)
    slug = PRICING_BATCH_SLUGS[12]
    if missing == "package":
        release_catalog["packages"].pop(slug)
    else:
        value = None if missing == "prepared_price" else "draft" if missing == "workflow_status" else ""
        with app.app_context():
            connection = get_db()
            connection.execute(f"UPDATE ideas SET {missing} = ? WHERE slug = ?", (value, slug))
            connection.commit()
    before = _rows(app)
    result = _post(client, csrf)
    assert result.status_code == 409
    assert result.json["gaps"]
    assert _rows(app) == before


def test_batch_publication_changes_only_listing_fields_and_is_idempotent(app, client, release_catalog):
    csrf = login_admin(client)
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE ideas SET published = 0, workflow_status = 'ready' WHERE slug = ?", (PRICING_BATCH_SLUGS[1],))
        connection.commit()
    before = _rows(app)
    published = _post(client, csrf)
    assert published.status_code == 200
    assert published.json["published_count"] == published.json["changed_count"] == 14
    after = _rows(app)
    changed_fields = {"published", "workflow_status", "sale_state", "updated_at"}
    for old, new in zip(before, after):
        if old["slug"] not in PRICING_BATCH_SLUGS:
            assert old == new
        else:
            assert new["published"] == 1 and new["workflow_status"] == "published"
            assert new["sale_state"] == "price_listed" and new["release_ready"] == 0
            assert all(old[key] == new[key] for key in old.keys() - changed_fields)
    again = _post(client, csrf)
    assert again.status_code == 200 and again.json["changed_count"] == 0
    assert _rows(app) == after
    with app.app_context():
        audit = [dict(row) for row in get_db().execute("SELECT * FROM audit_logs WHERE action = 'publish_release_packages'")]
        assert len(audit) == 1
        assert not any(str(row["prepared_price"]) in str(audit) for row in after if row["slug"] in PRICING_BATCH_SLUGS)
        assert get_db().execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"] == 0
    assert all(not item["can_purchase"] for item in client.get("/api/ideas").json["ideas"])


def test_single_volume_publication_rejects_archived_and_preserves_existing_sale_state(app, client, release_catalog):
    csrf = login_admin(client)
    first_id = release_catalog["ids"][PRICING_BATCH_SLUGS[0]]
    archived_id = next(value for slug, value in release_catalog["ids"].items() if slug not in PRICING_BATCH_SLUGS)
    assert _post(client, csrf, archived_id).status_code == 404
    assert _post(client, csrf, 999999).status_code == 404
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE ideas SET sale_state = 'for_sale', release_ready = 1 WHERE id = ?", (first_id,))
        connection.commit()
    before = _rows(app)
    result = _post(client, csrf, first_id)
    assert result.status_code == 200 and result.json["changed_count"] == 0
    assert result.json["states"][0]["sale_state"] == "for_sale"
    assert _rows(app) == before


def test_mid_batch_database_failure_rolls_back_every_listing(app, client, release_catalog):
    csrf = login_admin(client)
    with app.app_context():
        connection = get_db()
        connection.execute("CREATE TRIGGER synthetic_listing_failure BEFORE UPDATE OF sale_state ON ideas WHEN NEW.slug = 'sealed-concept-v08' BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
        connection.commit()
    before = _rows(app)
    with pytest.raises(sqlite3.IntegrityError, match="synthetic failure"):
        _post(client, csrf)
    assert _rows(app) == before


def test_admin_preview_renders_real_content_without_fabricated_order(app, client, release_catalog, monkeypatch):
    from tianwai import admin

    first_id = release_catalog["ids"][PRICING_BATCH_SLUGS[0]]
    assert client.get(f"/admin/ideas/{first_id}/preview").status_code == 302
    login_admin(client)
    captured = {}
    def render(name, **context):
        captured.update(context)
        assert name == "admin_package_preview.html"
        return "synthetic-private-preview"
    monkeypatch.setattr(admin, "render_template", render)
    with app.app_context():
        statements = []
        get_db().set_trace_callback(statements.append)
        result = client.get(f"/admin/ideas/{first_id}/preview")
        assert get_db().execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"] == 0
    assert result.status_code == 200 and "no-store" in result.headers["Cache-Control"]
    assert result.headers["Referrer-Policy"] == "no-referrer" and "Cookie" in result.headers["Vary"]
    assert captured["idea"]["paid_content"] and captured["package"]["flow_steps"]
    assert set(captured["asset_urls"]) == {"hero", "diagram", "scene"}
    # Exclude the test's own final count query from route-read inspection.
    assert not any(re.search(r"\b(?:FROM|JOIN)\s+(?:orders|customers|customer_devices|customer_sessions)\b", sql, re.I) for sql in statements[:-1])
    archived_id = next(value for slug, value in release_catalog["ids"].items() if slug not in PRICING_BATCH_SLUGS)
    assert client.get(f"/admin/ideas/{archived_id}/preview").status_code == 404


def test_preview_assets_require_live_admin_auth_and_never_reuse_cache(client, release_catalog):
    first_id = release_catalog["ids"][PRICING_BATCH_SLUGS[0]]
    path = f"/admin/ideas/{first_id}/assets/hero"
    assert client.get(path).status_code == 302
    csrf = login_admin(client)
    image = client.get(path)
    assert image.status_code == 200 and image.mimetype.startswith("image/")
    assert "no-store" in image.headers["Cache-Control"] and "Cookie" in image.headers["Vary"]
    assert image.headers["Referrer-Policy"] == "no-referrer"
    assert "ETag" not in image.headers and "Last-Modified" not in image.headers
    conditional = client.get(path, headers={"Range": "bytes=0-8", "If-Modified-Since": "Wed, 01 Jan 2099 00:00:00 GMT", "If-None-Match": '"synthetic"'})
    assert conditional.status_code == 200 and len(conditional.data) == len(image.data)
    client.post("/admin/logout", data={"csrf_token": csrf})
    assert client.get(path, headers={"Range": "bytes=0-8"}).status_code == 302


@pytest.mark.parametrize("slot", ["introduction", "unknown", "..%2F..%2Fprivate", "hero.webp"])
def test_preview_asset_slot_allowlist_and_archived_exclusion(client, release_catalog, slot):
    login_admin(client)
    first_id = release_catalog["ids"][PRICING_BATCH_SLUGS[0]]
    assert client.get(f"/admin/ideas/{first_id}/assets/{slot}").status_code == 404
    archived_id = next(value for slug, value in release_catalog["ids"].items() if slug not in PRICING_BATCH_SLUGS)
    assert client.get(f"/admin/ideas/{archived_id}/assets/hero").status_code == 404


@pytest.mark.parametrize("identifier", ["brand/../../outside.webp", "C:/private/file.webp", "brand/not-existing.webp"])
def test_preview_asset_never_serves_missing_or_escaped_stored_paths(app, client, release_catalog, identifier):
    csrf = login_admin(client)
    first_id = release_catalog["ids"][PRICING_BATCH_SLUGS[0]]
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE ideas SET diagram_image = ? WHERE id = ?", (identifier, first_id))
        connection.commit()
    assert client.get(f"/admin/ideas/{first_id}/assets/diagram").status_code == 404
    assert _post(client, csrf, first_id).status_code == 409


def test_existing_order_amount_and_paid_entitlement_survive_package_publication(app, client, release_catalog):
    from conftest import set_public_csrf
    from test_customer_access import _pay_and_get_activation

    first_id = release_catalog["ids"][PRICING_BATCH_SLUGS[0]]
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE ideas SET sale_state = 'for_sale', release_ready = 1 WHERE id = ?", (first_id,))
        connection.commit()
    order, activation_link, activation_code = _pay_and_get_activation(client)
    assert client.post(
        activation_link, data={"csrf_token": set_public_csrf(client), "activation_code": activation_code},
    ).status_code == 302
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE ideas SET sale_state = 'preparing', release_ready = 0 WHERE id = ?", (first_id,))
        connection.commit()
        before_order = dict(connection.execute("SELECT * FROM orders WHERE order_no = ?", (order["order_no"],)).fetchone())
    admin_client = app.test_client()
    csrf = login_admin(admin_client)
    assert _post(admin_client, csrf).status_code == 200
    with app.app_context():
        after_order = dict(get_db().execute("SELECT * FROM orders WHERE order_no = ?", (order["order_no"],)).fetchone())
    assert after_order == before_order and after_order["status"] == "paid"
    assert client.get("/library/orders/" + order["order_no"]).status_code == 200
    assert client.get(f"/admin/ideas/{first_id}/preview").status_code == 302
    assert client.get(f"/admin/ideas/{first_id}/assets/hero").status_code == 302
    for slot in ("hero", "diagram", "scene"):
        assert client.get(f"/library/assets/{first_id}/{slot}").status_code == 200
