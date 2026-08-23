import re
from datetime import datetime, timedelta, timezone

from conftest import set_public_csrf
from test_public_flow import create_order
from tianwai.db import get_db


def _pay_and_get_activation(client):
    order = create_order(client)
    payment_page = client.get(order["checkout_url"])
    body = payment_page.get_data(as_text=True)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', body).group(1)
    token = re.search(r'name="payment_token" value="([^"]+)"', body).group(1)
    response = client.post(
        "/pay/mock/complete",
        data={"csrf_token": csrf, "payment_token": token},
        follow_redirects=True,
    )
    result = response.get_data(as_text=True)
    code = re.search(r"本機測試開通碼.*?<strong>([^<]+)</strong>", result, re.S).group(1)
    link = re.search(r'href="(/activate/[^\"]+)"', result).group(1)
    return order, link, code


def test_activation_code_expires_and_can_be_resent(client, app):
    order, link, code = _pay_and_get_activation(client)
    with app.app_context():
        expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds")
        get_db().execute(
            """
            UPDATE activation_codes SET expires_at = ?
            WHERE order_id = (SELECT id FROM orders WHERE order_no = ?)
            """,
            (expired, order["order_no"]),
        )
        get_db().commit()

    csrf = set_public_csrf(client, "expired-activation-csrf")
    rejected = client.post(
        link,
        data={"csrf_token": csrf, "activation_code": code},
    )
    assert rejected.status_code == 400
    assert "已失效" in rejected.get_data(as_text=True)

    resent = client.post(
        f"{link}/resend",
        data={"csrf_token": csrf},
        follow_redirects=True,
    )
    assert resent.status_code == 200
    assert "新的開通資料已寄出" in resent.get_data(as_text=True)
    assert len(app.extensions["mail_outbox"]) == 2


def test_customer_login_code_expires_after_ten_minutes_without_losing_entitlement(client, app):
    order, link, activation_code = _pay_and_get_activation(client)
    csrf = set_public_csrf(client, "activate-for-login-csrf")
    activated = client.post(
        link,
        data={"csrf_token": csrf, "activation_code": activation_code},
        follow_redirects=True,
    )
    assert "七日品牌世界觀鍛造表" in activated.get_data(as_text=True)

    client.post("/customer/logout", data={"csrf_token": csrf})
    login_csrf = set_public_csrf(client, "login-request-csrf")
    requested = client.post(
        "/customer/login/request",
        data={"csrf_token": login_csrf, "customer_email": "traveler@example.com"},
        follow_redirects=True,
    )
    assert requested.status_code == 200
    login_code = re.search(
        r"本機測試登入碼.*?<strong>([^<]+)</strong>",
        requested.get_data(as_text=True),
        re.S,
    ).group(1)

    with app.app_context():
        expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds")
        get_db().execute(
            "UPDATE customer_login_codes SET expires_at = ? WHERE customer_email = ?",
            (expired, "traveler@example.com"),
        )
        get_db().commit()

    rejected = client.post(
        "/customer/login/verify",
        data={"csrf_token": login_csrf, "login_code": login_code},
    )
    assert rejected.status_code == 400
    assert "超過 10 分鐘" in rejected.get_data(as_text=True)

    with app.app_context():
        paid = get_db().execute(
            "SELECT status FROM orders WHERE order_no = ?", (order["order_no"],)
        ).fetchone()
        assert paid["status"] == "paid"


def test_valid_relogin_code_restores_library_and_is_single_use(client):
    _, link, activation_code = _pay_and_get_activation(client)
    csrf = set_public_csrf(client, "activate-relogin-csrf")
    client.post(
        link,
        data={"csrf_token": csrf, "activation_code": activation_code},
        follow_redirects=True,
    )
    client.post("/customer/logout", data={"csrf_token": csrf})

    login_csrf = set_public_csrf(client, "valid-login-csrf")
    page = client.post(
        "/customer/login/request",
        data={"csrf_token": login_csrf, "customer_email": "traveler@example.com"},
        follow_redirects=True,
    )
    code = re.search(
        r"本機測試登入碼.*?<strong>([^<]+)</strong>", page.get_data(as_text=True), re.S
    ).group(1)
    logged_in = client.post(
        "/customer/login/verify",
        data={"csrf_token": login_csrf, "login_code": code},
        follow_redirects=True,
    )
    assert logged_in.status_code == 200
    assert "已購內容" in logged_in.get_data(as_text=True)
    assert "品牌世界觀鍛造" in logged_in.get_data(as_text=True)

    reused = client.post(
        "/customer/login/verify",
        data={"csrf_token": login_csrf, "login_code": code},
    )
    assert reused.status_code in {302, 400}


def test_customer_access_pages_disable_caching_and_framing(client):
    response = client.get("/customer/login")

    assert response.status_code == 200
    assert response.headers["Cache-Control"].startswith("no-store")
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
