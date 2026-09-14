import hashlib
from pathlib import Path

import pytest

from conftest import set_public_csrf
from test_customer_access import _pay_and_get_activation
from tianwai.db import BLINDBOX_SEEDS, get_db, utc_now
from tianwai.concept_guides import supplemental_asset_identifiers


CURRENT_ASSETS = [idea[key] for idea in BLINDBOX_SEEDS for key in ("hero_image", "diagram_image", "scene_image")] + list(supplemental_asset_identifiers())
LEGACY_ASSETS = CURRENT_ASSETS + [path.replace("v31-", "v30-") for path in CURRENT_ASSETS if "/v31-" in path]


@pytest.fixture
def paid_reader(client, app):
    order, link, code = _pay_and_get_activation(client)
    csrf = set_public_csrf(client)
    assert client.post(link, data={"csrf_token": csrf, "activation_code": code}).status_code == 302
    with app.app_context():
        idea_id = get_db().execute("SELECT idea_id FROM orders WHERE order_no = ?", (order["order_no"],)).fetchone()["idea_id"]
    return client, order, idea_id


def test_all_current_and_retired_assets_are_private(app, client):
    assert len(LEGACY_ASSETS) == 79
    assert sum("/v34-14-" not in path and "/v35-14-" not in path for path in LEGACY_ASSETS) == 75
    assert sum("/v34-14-" in path for path in LEGACY_ASSETS) == 3
    assert sum("/v35-14-" in path for path in LEGACY_ASSETS) == 1
    private_root = Path(app.config["PRIVATE_ASSET_ROOT"])
    for asset in LEGACY_ASSETS:
        assert (private_root / asset).is_file()
        assert not (Path(app.static_folder) / asset).exists()
        response = client.head("/static/" + asset)
        assert response.status_code == 404
        assert "no-store" in response.headers["Cache-Control"]


def test_public_html_and_api_never_contain_paid_asset_identifiers(client):
    bodies = [client.get("/").get_data(as_text=True), client.get("/api/ideas").get_data(as_text=True)]
    bodies.extend(client.get("/ideas/" + idea["slug"]).get_data(as_text=True) for idea in BLINDBOX_SEEDS)
    for body in bodies:
        assert not any(path in body for path in CURRENT_ASSETS)
        assert "/library/assets/" not in body


@pytest.mark.parametrize("slot", ["hero", "diagram", "scene"])
@pytest.mark.parametrize("headers", [{}, {"Range": "bytes=0-31"}, {"If-None-Match": "*"}, {"If-Modified-Since": "Wed, 31 Dec 2099 23:59:59 GMT"}])
def test_valid_buyer_gets_only_authorized_private_asset(paid_reader, app, slot, headers):
    client, order, idea_id = paid_reader
    path = f"/library/assets/{idea_id}/{slot}"
    with app.app_context():
        idea = get_db().execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        expected_hash = hashlib.sha256((Path(app.config["PRIVATE_ASSET_ROOT"]) / idea[slot + "_image"]).read_bytes()).digest()
    for method in ("GET", "HEAD"):
        response = client.open(path, method=method, headers=headers)
        assert response.status_code == 200
        assert response.mimetype == "image/webp"
        assert "no-store" in response.headers["Cache-Control"]
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert "ETag" not in response.headers
        assert "Last-Modified" not in response.headers
        assert "Content-Range" not in response.headers
        if method == "GET":
            assert response.data.startswith(b"RIFF")
            assert hashlib.sha256(response.data).digest() == expected_hash
    body = client.get("/library/orders/" + order["order_no"]).get_data(as_text=True)
    assert path in body
    assert not any(asset in body for asset in CURRENT_ASSETS)


@pytest.mark.parametrize("state", ["anonymous", "wrong_owner", "wrong_volume", "pending", "refunded", "revoked", "expired", "inactive_customer", "revoked_device"])
def test_no_paid_bytes_for_invalid_entitlement_or_session(paid_reader, app, state):
    client, order, idea_id = paid_reader
    if state == "anonymous":
        client = app.test_client()
    with app.app_context():
        connection = get_db()
        if state == "wrong_volume":
            idea_id = connection.execute("SELECT id FROM ideas WHERE id <> ? LIMIT 1", (idea_id,)).fetchone()["id"]
        elif state == "wrong_owner":
            connection.execute("UPDATE orders SET customer_email = ? WHERE order_no = ?", ("other-buyer@example.invalid", order["order_no"]))
        elif state in {"pending", "refunded"}:
            connection.execute("UPDATE orders SET status = ? WHERE order_no = ?", (state, order["order_no"]))
        elif state == "revoked":
            connection.execute("UPDATE customer_sessions SET revoked_at = ?", (utc_now(),))
        elif state == "expired":
            connection.execute("UPDATE customer_sessions SET expires_at = '2000-01-01T00:00:00+00:00'")
        elif state == "inactive_customer":
            connection.execute("UPDATE customers SET status = 'suspended'")
        elif state == "revoked_device":
            connection.execute("UPDATE customer_devices SET revoked_at = ?", (utc_now(),))
        connection.commit()
    if state != "wrong_volume":
        response = client.get("/library/orders/" + order["order_no"])
        assert response.status_code in {302, 404}
        assert 'class="manuscript-copy"' not in response.get_data(as_text=True)
    for method in ("GET", "HEAD"):
        for headers in ({}, {"Range": "bytes=0-31"}, {"If-None-Match": "*"}, {"If-Modified-Since": "Wed, 31 Dec 2099 23:59:59 GMT"}):
            response = client.open(f"/library/assets/{idea_id}/hero", method=method, headers=headers)
            assert response.status_code == 404
            assert response.mimetype != "image/webp"
            assert "no-store" in response.headers["Cache-Control"]
            assert not response.data.startswith(b"RIFF")


def test_private_asset_resolution_never_reads_public_or_traversal_files(app):
    from tianwai.private_content import resolve_private_asset

    with app.app_context():
        for value in ("../requirements.txt", "brand/../../requirements.txt", "/etc/passwd", "brand\\logo.png", "https://invalid.test/a.png", "brand/logo-transparent-512.png"):
            assert resolve_private_asset(value) is None
        assert resolve_private_asset(CURRENT_ASSETS[0]).is_file()


def test_public_branding_and_unknown_slots_remain_safe(paid_reader):
    client, _order, idea_id = paid_reader
    assert "no-store" in client.get("/library").headers["Cache-Control"]
    assert client.get("/static/brand/logo-transparent-512.png").status_code == 200
    assert client.get(f"/library/assets/{idea_id}/paid_content").status_code == 404
    assert client.get("/private_assets/" + CURRENT_ASSETS[0]).status_code == 404


def test_accidentally_reintroduced_public_copy_is_still_denied(app, client, tmp_path):
    copied_static = tmp_path / "public"
    file = copied_static / CURRENT_ASSETS[0]
    file.parent.mkdir(parents=True)
    file.write_bytes(b"not-real-image")
    app.static_folder = str(copied_static)
    assert client.get("/static/" + CURRENT_ASSETS[0]).status_code == 404


@pytest.mark.parametrize("prefix", ["/static/", "/static/brand/../"])
def test_legacy_images_never_emit_conditional_or_range_bytes(client, prefix):
    path = prefix + CURRENT_ASSETS[0]
    for method in ("GET", "HEAD"):
        for headers in ({"Range": "bytes=0-31"}, {"If-None-Match": "*"}, {"If-Modified-Since": "Wed, 31 Dec 2099 23:59:59 GMT"}):
            response = client.open(path, method=method, headers=headers)
            assert response.status_code == 404
            assert not response.data.startswith(b"RIFF")
