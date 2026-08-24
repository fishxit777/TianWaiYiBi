import re
import inspect

from conftest import login_admin, set_public_csrf
from tianwai.db import get_db
from tianwai.payments import ecpay_check_mac_value, process_payment_event


def _configure_live_verification(monkeypatch):
    monkeypatch.setenv("PAYMENT_PROVIDER", "ecpay")
    monkeypatch.setenv("ECPAY_MODE", "production")
    monkeypatch.setenv("ECPAY_MERCHANT_ID", "verification-merchant")
    monkeypatch.setenv("ECPAY_HASH_KEY", "verification-hash-key")
    monkeypatch.setenv("ECPAY_HASH_IV", "verification-hash-iv")
    monkeypatch.setenv("ECPAY_STORE_ID", "TWYB")
    monkeypatch.setenv("ECPAY_VERIFICATION_ENABLED", "true")
    monkeypatch.setenv("PAYMENT_VERIFICATION_EMAIL", "owner@example.com")
    monkeypatch.delenv("ECPAY_LIVE_CONFIRMED", raising=False)


def _create_verification_order(client, monkeypatch):
    _configure_live_verification(monkeypatch)
    csrf = login_admin(client)
    response = client.post(
        "/admin/api/payment-verification/orders",
        json={"confirm_amount": 5},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201
    return csrf, response.get_json()


def _paid_notice(order, payment_type="Credit_CreditCard"):
    parameters = {
        "MerchantID": "verification-merchant",
        "MerchantTradeNo": order["order_no"],
        "StoreID": "TWYB",
        "RtnCode": "1",
        "RtnMsg": "Success",
        "TradeNo": "2608241234567890",
        "TradeAmt": "5",
        "PaymentDate": "2026/08/24 12:34:56",
        "PaymentType": payment_type,
        "PaymentTypeChargeFee": "1",
        "TradeDate": "2026/08/24 12:33:00",
        "SimulatePaid": "0",
    }
    parameters["CheckMacValue"] = ecpay_check_mac_value(
        parameters,
        "verification-hash-key",
        "verification-hash-iv",
    )
    return parameters


def test_verification_order_requires_admin_csrf_and_explicit_live_switch(client, monkeypatch):
    _configure_live_verification(monkeypatch)
    unauthenticated = client.post(
        "/admin/api/payment-verification/orders", json={"confirm_amount": 5}
    )
    assert unauthenticated.status_code == 401

    csrf = login_admin(client)
    no_csrf = client.post(
        "/admin/api/payment-verification/orders", json={"confirm_amount": 5}
    )
    assert no_csrf.status_code == 403

    monkeypatch.setenv("ECPAY_VERIFICATION_ENABLED", "false")
    disabled = client.post(
        "/admin/api/payment-verification/orders",
        json={"confirm_amount": 5},
        headers={"X-CSRF-Token": csrf},
    )
    assert disabled.status_code == 409


def test_verification_order_uses_ecpay_minimum_credit_amount_without_opening_public_sales(
    client, app, monkeypatch
):
    csrf, order = _create_verification_order(client, monkeypatch)

    assert csrf
    assert order["amount"] == 5
    assert order["order_no"].startswith("TWYBV")
    assert len(order["order_no"]) <= 20
    assert order["checkout_url"].startswith("/pay/ecpay/")
    assert "owner@example.com" not in str(order)
    assert "verification-hash" not in str(order)

    redirect_page = client.get(order["checkout_url"])
    assert redirect_page.status_code == 200
    assert b'name="TotalAmount" value="5"' in redirect_page.data
    assert b'name="ChoosePayment" value="Credit"' in redirect_page.data
    assert b'name="UnionPay" value="2"' in redirect_page.data
    assert b'name="BindingCard" value="0"' in redirect_page.data
    assert b'name="StoreID" value="TWYB"' in redirect_page.data
    assert b"verification-hash-key" not in redirect_page.data
    assert b"verification-hash-iv" not in redirect_page.data

    public_checkout = client.get("/checkout/brand-world-forge")
    assert "正式付款尚未開放" in public_checkout.get_data(as_text=True)

    public_csrf = set_public_csrf(client, "public-sales-stay-closed")
    public_order = client.post(
        "/api/orders",
        json={
            "idea_slug": "brand-world-forge",
            "customer_name": "一般訪客",
            "customer_email": "visitor@example.com",
            "purchase_notice_consent": True,
            "digital_content_consent": True,
        },
        headers={"X-CSRF-Token": public_csrf},
    )
    assert public_order.status_code == 503

    with app.app_context():
        stored = get_db().execute(
            "SELECT amount, purpose, status FROM orders WHERE order_no = ?",
            (order["order_no"],),
        ).fetchone()
        assert dict(stored) == {"amount": 5, "purpose": "verification", "status": "pending"}


def test_pending_verification_order_can_be_safely_replaced_for_a_fresh_ecpay_session(
    client, app, monkeypatch
):
    csrf, first = _create_verification_order(client, monkeypatch)

    existing = client.post(
        "/admin/api/payment-verification/orders",
        json={"confirm_amount": 5},
        headers={"X-CSRF-Token": csrf},
    )
    assert existing.status_code == 200
    assert existing.get_json()["result"] == "existing_pending"
    assert existing.get_json()["order_no"] == first["order_no"]

    wrong = client.post(
        "/admin/api/payment-verification/orders",
        json={"confirm_amount": 5, "retry_order_no": "TWYBV-WRONG"},
        headers={"X-CSRF-Token": csrf},
    )
    assert wrong.status_code == 409

    replacement = client.post(
        "/admin/api/payment-verification/orders",
        json={"confirm_amount": 5, "retry_order_no": first["order_no"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert replacement.status_code == 201
    replacement_data = replacement.get_json()
    assert replacement_data["result"] == "replaced"
    assert replacement_data["order_no"] != first["order_no"]

    with app.app_context():
        rows = get_db().execute(
            "SELECT order_no, status FROM orders WHERE purpose = 'verification' ORDER BY id"
        ).fetchall()
        assert [(row["order_no"], row["status"]) for row in rows] == [
            (first["order_no"], "cancelled"),
            (replacement_data["order_no"], "pending"),
        ]


def test_live_minimum_amount_callback_delivers_activates_then_refund_confirmation_revokes_access(
    client, app, monkeypatch
):
    csrf, order = _create_verification_order(client, monkeypatch)
    paid = client.post("/payments/ecpay/notify", data=_paid_notice(order))

    assert paid.status_code == 200
    assert paid.get_data(as_text=True) == "1|OK"
    assert len(app.extensions["mail_outbox"]) == 1
    delivery = app.extensions["mail_outbox"][0]["text"]
    activation_path = re.search(r"https?://[^/]+(/activate/\S+)", delivery).group(1)
    activation_code = re.search(r"一次性 12 位開通碼：([^\n]+)", delivery).group(1)

    public_csrf = set_public_csrf(client, "verification-activation")
    activated = client.post(
        activation_path,
        data={"csrf_token": public_csrf, "activation_code": activation_code},
        follow_redirects=True,
    )
    assert activated.status_code == 200
    assert "七日破局劍譜" in activated.get_data(as_text=True)

    rejected_confirmation = client.post(
        f"/admin/api/payment-verification/orders/{order['order_no']}/refund-confirmation",
        json={"external_refund_confirmed": True, "confirmation": "wrong-order"},
        headers={"X-CSRF-Token": csrf},
    )
    assert rejected_confirmation.status_code == 400

    refunded = client.post(
        f"/admin/api/payment-verification/orders/{order['order_no']}/refund-confirmation",
        json={"external_refund_confirmed": True, "confirmation": order["order_no"]},
        headers={"X-CSRF-Token": csrf},
    )
    repeated = client.post(
        f"/admin/api/payment-verification/orders/{order['order_no']}/refund-confirmation",
        json={"external_refund_confirmed": True, "confirmation": order["order_no"]},
        headers={"X-CSRF-Token": csrf},
    )

    assert refunded.status_code == 200
    assert refunded.get_json()["status"] == "refunded"
    assert repeated.status_code == 200
    assert repeated.get_json()["result"] == "already_refunded"

    inaccessible = client.get(f"/library/orders/{order['order_no']}")
    assert inaccessible.status_code in {302, 404}
    if inaccessible.status_code == 302:
        inaccessible = client.get(f"/library/orders/{order['order_no']}", follow_redirects=True)
    assert "七日破局劍譜" not in inaccessible.get_data(as_text=True)

    with app.app_context():
        connection = get_db()
        stored = connection.execute(
            "SELECT status, payment_method, refunded_at FROM orders WHERE order_no = ?",
            (order["order_no"],),
        ).fetchone()
        refund_event = connection.execute(
            "SELECT amount, method, result FROM refund_events WHERE order_id = "
            "(SELECT id FROM orders WHERE order_no = ?)",
            (order["order_no"],),
        ).fetchone()
        device = connection.execute(
            "SELECT revoked_at, revoked_reason FROM customer_devices "
            "WHERE customer_id = (SELECT customer_id FROM orders WHERE order_no = ?)",
            (order["order_no"],),
        ).fetchone()
        assert stored["status"] == "refunded"
        assert stored["payment_method"] == "Credit_CreditCard"
        assert stored["refunded_at"]
        assert device["revoked_at"]
        assert device["revoked_reason"] == "verification_refunded"
        assert dict(refund_event) == {
            "amount": 5,
            "method": "ecpay-dashboard",
            "result": "confirmed",
        }


def test_verification_callback_rejects_wrong_amount_and_simulated_payment(
    client, app, monkeypatch
):
    _, order = _create_verification_order(client, monkeypatch)
    wrong_amount = _paid_notice(order)
    wrong_amount["TradeAmt"] = "199"
    wrong_amount["CheckMacValue"] = ecpay_check_mac_value(
        wrong_amount, "verification-hash-key", "verification-hash-iv"
    )
    rejected = client.post("/payments/ecpay/notify", data=wrong_amount)
    assert rejected.status_code == 200

    simulated = _paid_notice(order)
    simulated["TradeNo"] = "2608249999999999"
    simulated["TradeAmt"] = "5"
    simulated["SimulatePaid"] = "1"
    simulated["CheckMacValue"] = ecpay_check_mac_value(
        simulated, "verification-hash-key", "verification-hash-iv"
    )
    ignored = client.post("/payments/ecpay/notify", data=simulated)
    assert ignored.status_code == 200

    with app.app_context():
        stored = get_db().execute(
            "SELECT status FROM orders WHERE order_no = ?", (order["order_no"],)
        ).fetchone()
        assert stored["status"] == "pending"


def test_dashboard_excludes_verification_order_from_business_metrics(client, monkeypatch):
    _, order = _create_verification_order(client, monkeypatch)
    client.post("/payments/ecpay/notify", data=_paid_notice(order))

    dashboard = client.get("/admin/api/dashboard").get_json()
    assert dashboard["metrics"]["revenue"] == 0
    assert dashboard["metrics"]["paid_orders"] == 0
    assert dashboard["customer_access"]["summary"]["paid_entitlements"] == 0
    assert dashboard["payment_verification"]["latest"]["order_no"] == order["order_no"]
    assert dashboard["payment_verification"]["latest"]["status"] == "paid"
    serialized = str(dashboard["payment_verification"])
    assert "owner@example.com" not in serialized
    assert "verification-hash" not in serialized


def test_admin_dashboard_has_separate_minimum_amount_verification_controls(client):
    login_admin(client)
    body = client.get("/admin").get_data(as_text=True)

    assert 'id="payment-verification-state"' in body
    assert 'id="create-payment-verification"' in body
    assert 'id="replace-payment-verification"' in body
    assert 'id="confirm-payment-verification-refund"' in body
    assert "payment-verification-v4" in body
    assert "NT$5 正式付款驗證" in body


def test_payment_processing_locks_postgres_order_before_deduplication_update():
    source = inspect.getsource(process_payment_event)

    assert "FOR UPDATE" in source
    assert 'backend == "postgresql"' in source
