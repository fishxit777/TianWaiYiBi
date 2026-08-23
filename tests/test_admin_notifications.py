import json

from tianwai.db import get_db


def _stub_line(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "test-line-access-token")
    monkeypatch.setattr(
        "tianwai.notifications.send_line_push",
        lambda _message: ("sent", ""),
    )


def test_daily_summary_endpoint_requires_secret(client):
    missing = client.post(
        "/internal/notifications/daily-summary",
        json={"slot": "morning"},
    )
    wrong = client.post(
        "/internal/notifications/daily-summary",
        json={"slot": "morning"},
        headers={"X-Notification-Secret": "wrong-secret"},
    )

    assert missing.status_code == 404
    assert wrong.status_code == 404


def test_daily_summary_queues_detailed_private_line_and_email(client, app, monkeypatch):
    _stub_line(monkeypatch)

    response = client.post(
        "/internal/notifications/daily-summary",
        json={"slot": "morning"},
        headers={
            "X-Notification-Secret": "test-notification-secret-with-at-least-32-characters"
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["slot"] == "morning"
    assert body["queued"] == 2
    assert body["channels"] == {"email": "sent", "line": "sent"}

    with app.app_context():
        rows = get_db().execute(
            "SELECT channel, recipient_masked, payload_json FROM notification_queue ORDER BY channel"
        ).fetchall()
        assert [row["channel"] for row in rows] == ["email", "line"]
        payloads = [json.loads(row["payload_json"]) for row in rows]
        combined = "\n".join(
            payload.get("message", payload.get("text", "")) for payload in payloads
        )

    for heading in ("訂單與營收", "開通與存取", "安全與風險", "系統與通知", "需要處理", "正常但值得知道"):
        assert heading in combined
    assert "admin-alerts@example.com" not in combined
    assert "test-notification-secret" not in combined
    assert "目前無需立即處理" in combined


def test_daily_summary_is_idempotent_per_taipei_date_slot_and_channel(client, app, monkeypatch):
    _stub_line(monkeypatch)
    headers = {
        "X-Notification-Secret": "test-notification-secret-with-at-least-32-characters"
    }

    first = client.post(
        "/internal/notifications/daily-summary",
        json={"slot": "noon"},
        headers=headers,
    )
    second = client.post(
        "/internal/notifications/daily-summary",
        json={"slot": "noon"},
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.get_json()["deduplicated"] == 2
    with app.app_context():
        count = get_db().execute(
            "SELECT COUNT(*) AS count FROM notification_queue"
        ).fetchone()["count"]
    assert count == 2


def test_high_risk_access_event_creates_two_privacy_safe_alerts(app, monkeypatch):
    from tianwai.risk import record_access_event

    _stub_line(monkeypatch)
    with app.test_request_context(
        "/customer/library",
        environ_base={"REMOTE_ADDR": "203.0.113.44"},
        headers={"User-Agent": "Sensitive Browser 1.0"},
    ):
        event_id = record_access_event(
            "revoked_session_replay",
            85,
            "session_revoked",
            metadata={
                "email": "customer@example.com",
                "token": "SECRET-TOKEN",
                "reason": "revoked_cookie_reused",
            },
        )

    with app.app_context():
        rows = get_db().execute(
            "SELECT channel, payload_json FROM notification_queue ORDER BY channel"
        ).fetchall()
        payload_text = "\n".join(row["payload_json"] for row in rows)

    assert [row["channel"] for row in rows] == ["email", "line"]
    assert event_id in payload_text
    assert "重大" in payload_text
    assert "203.0.113.*" in payload_text
    assert "customer@example.com" not in payload_text
    assert "SECRET-TOKEN" not in payload_text
    assert "203.0.113.44" not in payload_text


def test_high_security_event_queues_immediate_dual_channel_alert(app, monkeypatch):
    from tianwai.security import log_security_event

    _stub_line(monkeypatch)
    with app.test_request_context(
        "/payments/webhook",
        environ_base={"REMOTE_ADDR": "198.51.100.80"},
    ):
        log_security_event(
            "payment_signature_rejected",
            "high",
            "rejected",
            "bad_signature token=must-not-leak",
        )

    with app.app_context():
        rows = get_db().execute(
            "SELECT channel, payload_json FROM notification_queue ORDER BY channel"
        ).fetchall()
        combined = "\n".join(row["payload_json"] for row in rows)

    assert [row["channel"] for row in rows] == ["email", "line"]
    assert "payment_signature_rejected" in combined
    assert "198.51.100.*" in combined
    assert "must-not-leak" not in combined


def test_transactional_email_failure_alerts_line_without_recursive_queue(app, monkeypatch):
    from tianwai.mailer import send_email

    _stub_line(monkeypatch)
    monkeypatch.setattr("tianwai.mailer.development_delivery_enabled", lambda: False)
    monkeypatch.setattr("tianwai.mailer.email_delivery_ready", lambda: False)

    with app.test_request_context("/customer/login"):
        result = send_email(
            "customer@example.com",
            "登入碼",
            "secret code must stay private",
            "customer_login_code",
        )

    assert result == "failed"
    with app.app_context():
        connection = get_db()
        rows = connection.execute(
            "SELECT channel, payload_json FROM notification_queue ORDER BY channel"
        ).fetchall()
        email_event_count = connection.execute(
            "SELECT COUNT(*) AS count FROM email_events"
        ).fetchone()["count"]
        combined = "\n".join(row["payload_json"] for row in rows)

    assert [row["channel"] for row in rows] == ["email", "line"]
    assert email_event_count == 2
    assert "secret code" not in combined
    assert "customer@example.com" not in combined
