"""Isolated synthetic price tests; no production pricing or customer data."""

import sqlite3

import pytest

from conftest import login_admin
from tianwai.commerce import PRICING_BATCH_SLUGS
from tianwai.db import get_db, init_db, migrate_database


@pytest.fixture
def prepared_catalog(app):
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE ideas SET prepared_price = NULL, sale_state = 'preparing', release_ready = 0")
        connection.commit()
        first = connection.execute("SELECT id FROM ideas WHERE slug = ?", (PRICING_BATCH_SLUGS[0],)).fetchone()["id"]
    return first


def commerce_post(client, csrf, idea_id, **updates):
    data = {"prepared_price": 4217, "sale_state": "preparing", "release_ready": False}
    data.update(updates)
    return client.post(
        f"/admin/api/ideas/{idea_id}/commerce", json=data,
        headers={"X-CSRF-Token": csrf},
    )


def batch_entries():
    return [{"slug": slug, "prepared_price": 4217 + index} for index, slug in enumerate(PRICING_BATCH_SLUGS)]


def test_commerce_private_endpoint_requires_session_and_csrf(client, prepared_catalog):
    path = f"/admin/api/ideas/{prepared_catalog}/commerce"
    anonymous = client.get(path)
    assert anonymous.status_code == 401
    assert "no-store" in anonymous.headers["Cache-Control"]
    csrf = login_admin(client)
    denied = commerce_post(client, "wrong-token", prepared_catalog)
    assert denied.status_code == 403
    current = client.get(path)
    assert current.status_code == 200
    assert "no-store" in current.headers["Cache-Control"]
    assert current.json["commerce"]["prepared_price"] is None
    accepted = commerce_post(client, csrf, prepared_catalog)
    assert accepted.status_code == 200
    assert accepted.json["commerce"]["prepared_price"] == 4217
    assert "price" not in accepted.json["commerce"]
    assert accepted.json["preview"]["limitations"]


@pytest.mark.parametrize("value", [True, False, "4217", 4.5, -1, 0, 100001, [], {}])
def test_prepared_price_rejects_coercion_or_out_of_range_values(client, prepared_catalog, value):
    csrf = login_admin(client)
    result = commerce_post(client, csrf, prepared_catalog, prepared_price=value)
    assert result.status_code == 400


@pytest.mark.parametrize("value", [1, "true", None])
def test_ready_requires_a_real_json_boolean(client, prepared_catalog, value):
    csrf = login_admin(client)
    assert commerce_post(client, csrf, prepared_catalog, release_ready=value).status_code == 400


def test_explicit_public_confirmation_and_delivery_checks_cannot_be_skipped(app, client, prepared_catalog):
    csrf = login_admin(client)
    assert commerce_post(client, csrf, prepared_catalog, sale_state="price_listed").status_code == 409
    listed = commerce_post(client, csrf, prepared_catalog, sale_state="price_listed", confirm_publication=True)
    assert listed.status_code == 200
    assert listed.json["commerce"]["price"] == 4217
    assert not listed.json["commerce"]["can_purchase"]
    assert commerce_post(
        client, csrf, prepared_catalog, sale_state="for_sale", confirm_publication=True,
    ).status_code == 409
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE ideas SET hero_image = '' WHERE id = ?", (prepared_catalog,))
        connection.commit()
    missing = commerce_post(
        client, csrf, prepared_catalog, sale_state="for_sale", release_ready=True, confirm_publication=True,
    )
    assert missing.status_code == 409
    assert "主視覺" in missing.json["error"]
    # A safe return to preparation does not require another publication confirmation.
    assert commerce_post(client, csrf, prepared_catalog, prepared_price=None).status_code == 200


def test_commerce_accepts_fourteenth_but_cannot_overwrite_content_or_configure_archived(app, client, prepared_catalog):
    csrf = login_admin(client)
    assert commerce_post(client, csrf, prepared_catalog, title="Unexpected edit").status_code == 400
    with app.app_context():
        connection = get_db()
        last_id = connection.execute("SELECT id FROM ideas WHERE slug = 'sealed-concept-v14'").fetchone()["id"]
        archived_before = dict(connection.execute("SELECT * FROM ideas WHERE slug = 'mvp-sword-cut'").fetchone())
    accepted = commerce_post(client, csrf, last_id)
    assert accepted.status_code == 200
    assert accepted.json["commerce"]["in_pricing_batch"] is True
    assert accepted.json["commerce"]["prepared_price"] == 4217
    assert "price" not in accepted.json["commerce"]
    assert accepted.json["commerce"]["can_purchase"] is False
    assert commerce_post(client, csrf, archived_before["id"]).status_code == 409
    assert commerce_post(client, csrf, 999999).status_code == 404
    with app.app_context():
        assert dict(get_db().execute("SELECT * FROM ideas WHERE id = ?", (archived_before["id"],)).fetchone()) == archived_before


def test_batch_is_all_or_nothing_and_contains_no_price_audit(app, client, prepared_catalog):
    csrf = login_admin(client)
    with app.app_context():
        connection = get_db()
        before = [dict(row) for row in connection.execute("SELECT * FROM ideas ORDER BY id")]
    entries = batch_entries()
    assert PRICING_BATCH_SLUGS == (
        "sealed-twin-tire-safety",
        *(f"sealed-concept-v{number:02d}" for number in range(2, 15)),
    )
    assert len(entries) == 14
    result = client.post(
        "/admin/api/commerce/prepare", json={"entries": entries}, headers={"X-CSRF-Token": csrf},
    )
    assert result.status_code == 200
    assert result.json["prepared_count"] == 14
    with app.app_context():
        connection = get_db()
        after = [dict(row) for row in connection.execute("SELECT * FROM ideas ORDER BY id")]
        audit = " ".join(str(dict(row)) for row in connection.execute("SELECT * FROM audit_logs"))
    for old, new in zip(before, after):
        if old["slug"] not in PRICING_BATCH_SLUGS:
            assert new == old
        else:
            for field in old.keys() - {"prepared_price", "updated_at"}:
                assert old[field] == new[field]
            assert new["prepared_price"] == next(entry["prepared_price"] for entry in entries if entry["slug"] == old["slug"])
    assert all(str(entry["prepared_price"]) not in audit for entry in entries)
    # A non-preparing row blocks the entire next batch, including earlier entries.
    commerce_post(client, csrf, prepared_catalog, sale_state="price_listed", confirm_publication=True)
    blocked = client.post(
        "/admin/api/commerce/prepare",
        json={"entries": [{**entry, "prepared_price": entry["prepared_price"] + 1000} for entry in entries]},
        headers={"X-CSRF-Token": csrf},
    )
    assert blocked.status_code == 409
    with app.app_context():
        remaining = get_db().execute("SELECT prepared_price FROM ideas WHERE slug = ?", (PRICING_BATCH_SLUGS[-1],)).fetchone()
    assert remaining["prepared_price"] == entries[-1]["prepared_price"]


@pytest.mark.parametrize("mistake", ["old_thirteen", "extra_fifteenth", "duplicate", "fifteenth", "archived", "invalid", "extra_key"])
def test_batch_validates_every_entry_before_writing(app, client, prepared_catalog, mistake):
    csrf = login_admin(client)
    entries = batch_entries()
    assert len(entries) == 14
    with app.app_context():
        before = [dict(row) for row in get_db().execute("SELECT * FROM ideas ORDER BY id")]
    if mistake == "old_thirteen":
        assert entries.pop()["slug"] == "sealed-concept-v14"
    elif mistake == "extra_fifteenth":
        entries.append({"slug": "sealed-concept-v15", "prepared_price": 4231})
    elif mistake == "duplicate":
        entries[-1]["slug"] = entries[0]["slug"]
    elif mistake == "fifteenth":
        entries[-1]["slug"] = "sealed-concept-v15"
    elif mistake == "archived":
        entries[-1]["slug"] = "mvp-sword-cut"
    elif mistake == "invalid":
        entries[-1]["prepared_price"] = True
    else:
        entries[-1]["published"] = False
    result = client.post(
        "/admin/api/commerce/prepare", json={"entries": entries}, headers={"X-CSRF-Token": csrf},
    )
    assert result.status_code == 400
    with app.app_context():
        assert [dict(row) for row in get_db().execute("SELECT * FROM ideas ORDER BY id")] == before
        assert get_db().execute("SELECT COUNT(*) AS n FROM ideas WHERE prepared_price IS NOT NULL").fetchone()["n"] == 0


def test_additive_migration_does_not_copy_legacy_prices_or_reset_sales(app, prepared_catalog):
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE ideas SET price_override = 5123, prepared_price = 4217, sale_state = 'price_listed', release_ready = 1 WHERE id = ?", (prepared_catalog,))
        connection.commit()
        init_db()
        same = connection.execute("SELECT price_override, prepared_price, sale_state, release_ready FROM ideas WHERE id = ?", (prepared_catalog,)).fetchone()
        assert tuple(same) == (5123, 4217, "price_listed", 1)
        # Simulate an earlier schema without changing any underlying business rows.
        for column in ("prepared_price", "sale_state", "release_ready"):
            connection.execute(f"ALTER TABLE ideas DROP COLUMN {column}")
        connection.commit()
        migrate_database(connection)
        migrated = connection.execute("SELECT price_override, prepared_price, sale_state, release_ready FROM ideas WHERE id = ?", (prepared_catalog,)).fetchone()
        assert tuple(migrated) == (5123, None, "preparing", 0)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE ideas SET prepared_price = 2.5 WHERE id = ?", (prepared_catalog,))
        connection.rollback()


def test_batch_rolls_back_if_a_database_write_fails_midway(app, client, prepared_catalog):
    csrf = login_admin(client)
    with app.app_context():
        connection = get_db()
        connection.execute(
            "CREATE TRIGGER simulate_batch_failure BEFORE UPDATE OF prepared_price ON ideas "
            "WHEN NEW.slug = 'sealed-concept-v08' "
            "BEGIN SELECT RAISE(ABORT, 'synthetic write failure'); END"
        )
        connection.commit()
    with pytest.raises(sqlite3.IntegrityError, match="synthetic write failure"):
        client.post(
            "/admin/api/commerce/prepare", json={"entries": batch_entries()},
            headers={"X-CSRF-Token": csrf},
        )
    with app.app_context():
        connection = get_db()
        assert connection.execute("SELECT COUNT(*) AS n FROM ideas WHERE prepared_price IS NOT NULL").fetchone()["n"] == 0
        assert connection.execute("SELECT COUNT(*) AS n FROM audit_logs WHERE action = 'prepare_commerce_batch'").fetchone()["n"] == 0


def test_content_save_and_republication_reset_manual_sale_readiness(app, client, prepared_catalog):
    csrf = login_admin(client)
    opened = commerce_post(
        client, csrf, prepared_catalog, sale_state="for_sale", release_ready=True, confirm_publication=True,
    )
    assert opened.status_code == 200
    dashboard = client.get("/admin/api/dashboard").json
    idea = next(item for item in dashboard["ideas"] if item["id"] == prepared_catalog)
    idea["summary"] += "（合成測試修訂）"
    saved = client.post(f"/admin/api/ideas/{prepared_catalog}", json=idea, headers={"X-CSRF-Token": csrf})
    assert saved.status_code == 200
    closed = client.get(f"/admin/api/ideas/{prepared_catalog}/commerce").json["commerce"]
    assert closed["prepared_price"] == 4217
    assert closed["sale_state"] == "price_listed"
    assert not closed["release_ready"] and not closed["can_purchase"]
    commerce_post(client, csrf, prepared_catalog, sale_state="for_sale", release_ready=True, confirm_publication=True)
    client.post(f"/admin/api/ideas/{prepared_catalog}/publish", json={"published": False}, headers={"X-CSRF-Token": csrf})
    closed = client.get(f"/admin/api/ideas/{prepared_catalog}/commerce").json["commerce"]
    assert closed["sale_state"] == "price_listed"
    assert not closed["release_ready"] and not closed["price_visible"]
