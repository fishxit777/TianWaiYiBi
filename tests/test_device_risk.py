import json
import re
from datetime import datetime

from conftest import set_public_csrf
from test_customer_access import _pay_and_get_activation
from tianwai.db import get_db
from tianwai.risk import verify_access_event_chain


def _login(client, email="traveler@example.com", suffix="device"):
    csrf = set_public_csrf(client, f"{suffix}-csrf")
    page = client.post(
        "/customer/login/request",
        data={"csrf_token": csrf, "customer_email": email},
        follow_redirects=True,
    )
    code = re.search(
        r"本機測試登入碼.*?<strong>([^<]+)</strong>", page.get_data(as_text=True), re.S
    ).group(1)
    return client.post(
        "/customer/login/verify",
        data={"csrf_token": csrf, "login_code": code},
        follow_redirects=True,
    )


def test_activation_and_login_codes_are_ten_minutes(client, app):
    _order, _link, _activation_code = _pay_and_get_activation(client)
    with app.app_context():
        activation = get_db().execute(
            "SELECT created_at, expires_at FROM activation_codes ORDER BY id DESC LIMIT 1"
        ).fetchone()
        activation_seconds = (
            datetime.fromisoformat(activation["expires_at"])
            - datetime.fromisoformat(activation["created_at"])
        ).total_seconds()
        assert activation_seconds == 600

    csrf = set_public_csrf(client, "ten-minute-login-csrf")
    client.post(
        "/customer/login/request",
        data={"csrf_token": csrf, "customer_email": "traveler@example.com"},
    )
    with app.app_context():
        login = get_db().execute(
            "SELECT created_at, expires_at FROM customer_login_codes ORDER BY id DESC LIMIT 1"
        ).fetchone()
        login_seconds = (
            datetime.fromisoformat(login["expires_at"])
            - datetime.fromisoformat(login["created_at"])
        ).total_seconds()
        assert login_seconds == 600


def test_two_trusted_devices_one_active_session_and_third_replaces_oldest(client, app):
    order, link, activation_code = _pay_and_get_activation(client)
    csrf = set_public_csrf(client, "first-device-csrf")
    first = client.post(
        link,
        data={"csrf_token": csrf, "activation_code": activation_code},
        follow_redirects=True,
    )
    assert first.status_code == 200

    second_client = app.test_client()
    second = _login(second_client, suffix="second-device")
    assert second.status_code == 200
    assert client.get("/customer/library").status_code == 302

    third_client = app.test_client()
    third = _login(third_client, suffix="third-device")
    assert third.status_code == 200
    assert second_client.get("/customer/library").status_code == 302
    assert second_client.get("/customer/library").status_code == 302
    content = third_client.get(f"/library/orders/{order['order_no']}")
    assert content.status_code == 200
    assert "access-watermark" in content.get_data(as_text=True)
    assert "ORD-***" in content.get_data(as_text=True)

    with app.app_context():
        connection = get_db()
        customer = connection.execute(
            "SELECT * FROM customers WHERE normalized_email = 'traveler@example.com'"
        ).fetchone()
        device_count = connection.execute(
            "SELECT COUNT(*) AS count FROM customer_devices WHERE customer_id = ? AND revoked_at IS NULL",
            (customer["id"],),
        ).fetchone()["count"]
        active_sessions = connection.execute(
            "SELECT COUNT(*) AS count FROM customer_sessions WHERE customer_id = ? AND revoked_at IS NULL",
            (customer["id"],),
        ).fetchone()["count"]
        replaced = connection.execute(
            "SELECT 1 FROM access_events WHERE event_type = 'trusted_device_replaced'"
        ).fetchone()
        replay_alert = connection.execute(
            "SELECT 1 FROM risk_incidents WHERE level = 'high' AND reason_codes LIKE '%revoked_session_replay%'"
        ).fetchone()
        assert device_count == 2
        assert active_sessions == 1
        assert replaced is not None
        assert replay_alert is not None
        assert verify_access_event_chain()["valid"] is True


def test_high_risk_code_failures_queue_privacy_minimized_alert(client, app):
    _order, link, activation_code = _pay_and_get_activation(client)
    csrf = set_public_csrf(client, "high-risk-csrf")
    for _ in range(5):
        response = client.post(
            link,
            data={"csrf_token": csrf, "activation_code": "AAAAAAAAAAAA"},
        )
        assert response.status_code == 400

    with app.app_context():
        connection = get_db()
        incident = connection.execute(
            "SELECT * FROM risk_incidents WHERE level = 'high' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        notification = connection.execute(
            "SELECT * FROM notification_queue WHERE channel = 'line' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        channels = connection.execute(
            "SELECT channel FROM notification_queue WHERE incident_id = ? ORDER BY channel",
            (incident["id"],),
        ).fetchall()
        payload = json.loads(notification["payload_json"])["message"]
        assert incident is not None
        assert [row["channel"] for row in channels] == ["line"]
        assert notification["status"] in {"sent", "failed", "skipped"}
        assert "traveler@example.com" not in payload
        assert activation_code.replace("-", "") not in payload
        assert "TYB-" in payload
