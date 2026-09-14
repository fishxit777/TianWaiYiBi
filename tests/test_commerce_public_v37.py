"""Staged commerce contracts using only isolated databases and synthetic prices."""

import re

import pytest

from conftest import login_admin, set_public_csrf
from test_customer_access import _pay_and_get_activation
from test_public_flow import create_order
from tianwai import create_app
from tianwai.db import get_db


FIRST_SLUG = "sealed-twin-tire-safety"
LAST_SLUG = "sealed-concept-v14"
STAGED_PRICE = 7319


@pytest.fixture
def catalog_app(app, tmp_path):
    """Fresh startup defaults, deliberately bypassing the legacy sales fixture."""
    return create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "fresh-staged-catalog.db"),
        "SESSION_COOKIE_SECURE": False,
    })


def _configure_idea(application, *, state, ready, price=STAGED_PRICE, published=1):
    with application.app_context():
        connection = get_db()
        connection.execute(
            "UPDATE ideas SET prepared_price = ?, sale_state = ?, release_ready = ?, "
            "published = ? WHERE slug = ?",
            (price, state, int(ready), published, FIRST_SLUG),
        )
        connection.commit()


def _payment_gate(monkeypatch, is_open):
    """Exercise the real production gate with dummy credentials, without I/O."""
    monkeypatch.setenv("PAYMENT_PROVIDER", "ecpay")
    monkeypatch.setenv("ECPAY_MODE", "production")
    monkeypatch.setenv("ECPAY_MERCHANT_ID", "synthetic-merchant")
    monkeypatch.setenv("ECPAY_HASH_KEY", "synthetic-key")
    monkeypatch.setenv("ECPAY_HASH_IV", "synthetic-iv")
    monkeypatch.setenv("ECPAY_LIVE_CONFIRMED", "true" if is_open else "false")


def _post_order(client, slug=FIRST_SLUG):
    return client.post(
        "/api/orders",
        json={
            "idea_slug": slug,
            "customer_name": "隔離測試",
            "customer_email": "staged-catalog@example.invalid",
            "purchase_notice_consent": True,
            "digital_content_consent": True,
        },
        headers={"X-CSRF-Token": set_public_csrf(client)},
    )


def _public_idea(client, slug=FIRST_SLUG):
    return next(item for item in client.get("/api/ideas").get_json()["ideas"] if item["slug"] == slug)


def test_fresh_catalog_defaults_hide_legacy_price_and_deny_direct_orders(catalog_app):
    client = catalog_app.test_client()
    with catalog_app.app_context():
        rows = get_db().execute(
            "SELECT prepared_price, sale_state, release_ready FROM ideas WHERE published = 1"
        ).fetchall()
        assert len(rows) == 14
        assert all(tuple(row) == (None, "preparing", 0) for row in rows)
    for path in ("/", "/ideas/" + FIRST_SLUG, "/checkout/" + FIRST_SLUG):
        response = client.get(path)
        assert response.status_code == 200
        assert "NT$199" not in response.get_data(as_text=True)
    payload = client.get("/api/ideas").get_json()
    assert all("price" not in item and item["price_visible"] is False for item in payload["ideas"])
    assert _post_order(client).status_code in (403, 409, 503)


@pytest.mark.parametrize("state", ["preparing", "price_listed", "for_sale"])
@pytest.mark.parametrize("release_ready", [False, True])
@pytest.mark.parametrize("payment_open", [False, True])
def test_public_price_and_purchase_matrix(catalog_app, monkeypatch, state, release_ready, payment_open):
    _configure_idea(catalog_app, state=state, ready=release_ready)
    _payment_gate(monkeypatch, payment_open)
    client = catalog_app.test_client()
    visible = state in {"price_listed", "for_sale"}
    purchasable = state == "for_sale" and release_ready and payment_open

    item = _public_idea(client)
    assert item["sale_state"] == state
    assert item["price_visible"] is visible
    assert item["can_purchase"] is purchasable
    assert ("price" in item) is visible
    if visible:
        assert item["price"] == STAGED_PRICE
    for path in ("/", "/ideas/" + FIRST_SLUG, "/checkout/" + FIRST_SLUG):
        body = client.get(path).get_data(as_text=True)
        assert (str(STAGED_PRICE) in body) is visible
        assert "prepared_price" not in body
        if path.startswith("/checkout/"):
            assert ('id="order-form"' in body) is purchasable
        if path.startswith("/ideas/"):
            assert ('href="/checkout/' + FIRST_SLUG + '"' in body) is purchasable

    response = _post_order(client)
    if purchasable:
        assert response.status_code == 201
        assert response.get_json()["amount"] == STAGED_PRICE
    else:
        assert response.status_code in (403, 409, 503)
    with catalog_app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM orders").fetchone()[0] == int(purchasable)


@pytest.mark.parametrize("state", ["preparing", "price_listed", "for_sale"])
def test_missing_prepared_price_never_falls_back_to_legacy_sale_price(catalog_app, state):
    _configure_idea(catalog_app, state=state, ready=True, price=None)
    with catalog_app.app_context():
        connection = get_db()
        connection.execute("UPDATE ideas SET price_override = 8427 WHERE slug = ?", (FIRST_SLUG,))
        connection.execute("UPDATE settings SET value = '9463' WHERE key = 'idea_price'")
        connection.commit()
    client = catalog_app.test_client()
    item = _public_idea(client)
    assert "price" not in item
    assert item["price_visible"] is False
    assert item["can_purchase"] is False
    for path in ("/", "/ideas/" + FIRST_SLUG, "/checkout/" + FIRST_SLUG):
        body = client.get(path).get_data(as_text=True)
        assert "8427" not in body and "9463" not in body
    assert _post_order(client).status_code in (403, 409, 503)


def test_preparing_price_is_not_exposed_in_static_client_scripts(catalog_app):
    _configure_idea(catalog_app, state="preparing", ready=False)
    client = catalog_app.test_client()
    body = client.get("/ideas/" + FIRST_SLUG).get_data(as_text=True)
    paths = re.findall(r'<script[^>]+src="([^"]+)"', body)
    assert paths
    for path in paths:
        if path.startswith("/static/"):
            script = client.get(path).get_data(as_text=True)
            assert str(STAGED_PRICE) not in script


def test_unpublished_item_cannot_be_purchased_even_when_other_gates_are_ready(catalog_app):
    _configure_idea(catalog_app, state="for_sale", ready=True, published=0)
    client = catalog_app.test_client()
    assert all(item["slug"] != FIRST_SLUG for item in client.get("/api/ideas").get_json()["ideas"])
    assert client.get("/ideas/" + FIRST_SLUG).status_code == 404
    assert client.get("/checkout/" + FIRST_SLUG).status_code == 404
    assert _post_order(client).status_code == 404


def test_preparing_first_thirteen_preserves_fourteenth_and_keeps_all_prices_private(catalog_app, monkeypatch):
    client = catalog_app.test_client()
    csrf = login_admin(client)
    with catalog_app.app_context():
        connection = get_db()
        entries = [
            {"slug": row["slug"], "prepared_price": 7600 + row["sort_order"]}
            for row in connection.execute(
                "SELECT slug, sort_order FROM ideas WHERE published = 1 AND sort_order BETWEEN 1 AND 13"
            )
        ]
        fourteenth_before = dict(connection.execute("SELECT * FROM ideas WHERE slug = ?", (LAST_SLUG,)).fetchone())
    response = client.post(
        "/admin/api/commerce/prepare", json={"entries": entries}, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200
    _payment_gate(monkeypatch, True)
    public_client = catalog_app.test_client()
    public_bodies = [public_client.get("/").get_data(as_text=True), public_client.get("/api/ideas").get_data(as_text=True)]
    for entry in entries:
        public_bodies.extend(public_client.get(prefix + entry["slug"]).get_data(as_text=True) for prefix in ("/ideas/", "/checkout/"))
    for entry in entries:
        assert all(str(entry["prepared_price"]) not in body for body in public_bodies)
    assert _post_order(public_client, LAST_SLUG).status_code in (403, 409, 503)
    assert _public_idea(public_client, LAST_SLUG)["can_purchase"] is False
    with catalog_app.app_context():
        connection = get_db()
        assert dict(connection.execute("SELECT * FROM ideas WHERE slug = ?", (LAST_SLUG,)).fetchone()) == fourteenth_before
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_open_first_thirteen_does_not_open_display_only_fourteenth(catalog_app, monkeypatch):
    with catalog_app.app_context():
        connection = get_db()
        connection.execute(
            "UPDATE ideas SET prepared_price = ?, sale_state = 'for_sale', release_ready = 1 "
            "WHERE published = 1 AND sort_order BETWEEN 1 AND 13",
            (STAGED_PRICE,),
        )
        connection.commit()
    _payment_gate(monkeypatch, True)
    client = catalog_app.test_client()
    items = client.get("/api/ideas").get_json()["ideas"]
    assert len(items) == 14
    assert sum(item["can_purchase"] for item in items) == 13
    assert client.get("/ideas/" + LAST_SLUG).status_code == 200
    assert "price" not in _public_idea(client, LAST_SLUG)
    assert _post_order(client, LAST_SLUG).status_code in (403, 409, 503)
    assert _post_order(client, FIRST_SLUG).status_code == 201
    with catalog_app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1


def test_staged_price_changes_apply_only_to_new_order_snapshots(app, client):
    old_order = create_order(client)
    csrf = login_admin(client)
    with app.app_context():
        idea_id = get_db().execute("SELECT id FROM ideas WHERE slug = ?", (FIRST_SLUG,)).fetchone()[0]
    changed = client.post(
        f"/admin/api/ideas/{idea_id}/commerce",
        json={"prepared_price": STAGED_PRICE, "sale_state": "for_sale", "release_ready": True, "confirm_publication": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert changed.status_code == 200
    new_order = create_order(client)
    assert old_order["amount"] == 199
    assert new_order["amount"] == STAGED_PRICE
    payment_page = client.get(old_order["checkout_url"]).get_data(as_text=True)
    assert "NT$199" in payment_page
    assert str(STAGED_PRICE) not in payment_page
    payment_csrf = re.search(r'name="csrf_token" value="([^"]+)"', payment_page).group(1)
    payment_token = re.search(r'name="payment_token" value="([^"]+)"', payment_page).group(1)
    completed = client.post("/pay/mock/complete", data={"csrf_token": payment_csrf, "payment_token": payment_token})
    assert completed.status_code == 302
    with app.app_context():
        stored = get_db().execute("SELECT amount, status FROM orders WHERE order_no = ?", (old_order["order_no"],)).fetchone()
        assert tuple(stored) == (199, "paid")


@pytest.mark.parametrize("new_state", ["preparing", "price_listed"])
def test_existing_paid_rights_survive_sale_closure_and_price_changes(app, client, monkeypatch, new_state):
    order, link, code = _pay_and_get_activation(client)
    assert client.post(link, data={"csrf_token": set_public_csrf(client), "activation_code": code}).status_code == 302
    _configure_idea(app, state=new_state, ready=False, price=STAGED_PRICE)
    _payment_gate(monkeypatch, False)
    content = client.get("/library/orders/" + order["order_no"])
    assert content.status_code == 200
    with app.app_context():
        stored = get_db().execute("SELECT idea_id, amount, status FROM orders WHERE order_no = ?", (order["order_no"],)).fetchone()
        idea_id = stored["idea_id"]
        assert stored["amount"] == 199 and stored["status"] == "paid"
    for slot in ("hero", "diagram", "scene"):
        asset = client.get(f"/library/assets/{idea_id}/{slot}")
        assert asset.status_code == 200
        assert asset.mimetype == "image/webp"
    assert _post_order(app.test_client()).status_code in (403, 409, 503)
