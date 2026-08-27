import json
from datetime import datetime, timedelta, timezone

from tianwai.db import get_db, utc_now


def _stub_line(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "test-line-access-token")
    monkeypatch.setattr(
        "tianwai.notifications.send_line_push",
        lambda _message: ("sent", ""),
    )


def _insert_notification(connection, key, status, created_at, channel="line"):
    connection.execute(
        """
        INSERT INTO notification_queue
            (dedupe_key, channel, recipient_masked, payload_json, status,
             attempts, last_error, created_at, updated_at)
        VALUES (?, ?, 'masked', '{}', ?, 1, 'test', ?, ?)
        """,
        (key, channel, status, created_at, created_at),
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


def test_daily_summary_keeps_historical_delivery_debt_out_of_current_todo(app):
    from tianwai.notifications import build_daily_summary

    with app.app_context():
        connection = get_db()
        _insert_notification(connection, "line:daily-summary:old", "skipped", "2026-01-01T00:00:00+00:00")
        _insert_notification(connection, "email:risk:old", "failed", "2026-01-01T00:00:00+00:00", "email")
        connection.commit()
        summary = build_daily_summary("morning")["email"]

    assert "重試或修正 2 筆未送達管理通知" not in summary
    assert "歷史未投遞紀錄 2 筆" in summary
    assert "不自動重送" in summary


def test_daily_summary_only_marks_recent_failed_delivery_as_actionable(app):
    from tianwai.notifications import build_daily_summary

    with app.app_context():
        connection = get_db()
        now = utc_now()
        _insert_notification(connection, "email:risk:recent", "failed", now, "email")
        _insert_notification(connection, "line:risk:recent", "skipped", now)
        connection.commit()
        summary = build_daily_summary("morning")["email"]

    assert "今日有 1 筆管理通知送達失敗" in summary
    assert "今日略過 1 筆" in summary
    assert "今日有 2 筆" not in summary


def test_daily_summary_distinguishes_line_channel_from_admin_recipient(app, monkeypatch):
    from tianwai.notifications import build_daily_summary

    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "channel-token")
    monkeypatch.setenv("LINE_CHANNEL_SECRET", "channel-secret")
    monkeypatch.delenv("LINE_ADMIN_USER_ID", raising=False)

    with app.app_context():
        summary = build_daily_summary("morning")["email"]

    assert "LINE 官方帳號已連線，但管理員私訊收件人尚未設定" in summary
    assert "LINE 官方帳號頻道未設定" not in summary


def test_daily_summary_treats_verified_payment_config_with_closed_gate_as_normal(app, monkeypatch):
    from tianwai.notifications import build_daily_summary

    monkeypatch.setenv("PAYMENT_PROVIDER", "ecpay")
    monkeypatch.setenv("ECPAY_MODE", "production")
    monkeypatch.setenv("ECPAY_MERCHANT_ID", "merchant")
    monkeypatch.setenv("ECPAY_HASH_KEY", "hash-key")
    monkeypatch.setenv("ECPAY_HASH_IV", "hash-iv")
    monkeypatch.delenv("ECPAY_LIVE_CONFIRMED", raising=False)

    with app.app_context():
        summary = build_daily_summary("morning")["email"]

    assert "綠界正式金流（公開收款關閉）" in summary
    assert "金流設定未完成" not in summary
    assert "金流目前不可用" not in summary


def test_daily_summary_counts_unique_human_sessions_and_gates_top_idea(app):
    from tianwai.notifications import build_daily_summary

    with app.app_context():
        connection = get_db()
        idea_id = connection.execute(
            "SELECT id FROM ideas WHERE slug = 'brand-world-forge'"
        ).fetchone()["id"]
        now = utc_now()
        rows = [
            ("page_view", None, "direct", "human-1", 0),
            ("view_idea", idea_id, "web", "human-1", 0),
            ("view_idea", idea_id, "web", "human-1", 0),
            ("page_view", None, "direct", "human-2", 0),
            ("view_idea", idea_id, "web", "human-3", 0),
            ("page_view", None, "direct", "bot-1", 1),
            ("view_idea", idea_id, "admin-preview", "admin-1", 0),
        ]
        for index, (event_name, stored_idea_id, source, session_id, automated) in enumerate(rows):
            connection.execute(
                """
                INSERT INTO analytics_events
                    (event_name, idea_id, source, session_id, event_value, event_version,
                     dedupe_key, is_automated, page_path, created_at)
                VALUES (?, ?, ?, ?, '', 1, ?, ?, '/', ?)
                """,
                (event_name, stored_idea_id, source, session_id, f"event-{index}", automated, now),
            )
        connection.commit()
        summary = build_daily_summary("morning")["email"]

    assert "有效訪客 3 位" in summary
    assert "首頁 2 位" in summary
    assert "仙策詳情 2 位" in summary
    assert "暫不排名" in summary
    assert "未達 10 位門檻" in summary


def test_retry_private_alerts_ignores_stale_summaries_and_alerts(app, monkeypatch):
    from tianwai.notifications import retry_private_alerts

    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "test-line-access-token")
    monkeypatch.setattr("tianwai.notifications._deliver", lambda _row: ("sent", ""))
    now = datetime.now(timezone.utc)
    with app.app_context():
        connection = get_db()
        _insert_notification(
            connection,
            "line:daily-summary:stale",
            "failed",
            (now - timedelta(days=2)).isoformat(timespec="seconds"),
        )
        _insert_notification(
            connection,
            "line:daily-summary:recent",
            "failed",
            (now - timedelta(hours=2)).isoformat(timespec="seconds"),
        )
        _insert_notification(
            connection,
            "line:risk:stale",
            "failed",
            (now - timedelta(days=8)).isoformat(timespec="seconds"),
        )
        _insert_notification(
            connection,
            "line:risk:recent",
            "failed",
            (now - timedelta(days=6)).isoformat(timespec="seconds"),
        )
        connection.commit()
        result = retry_private_alerts(limit=20)

    assert result["processed"] == 2
    assert result["sent"] == 2
    assert result["ignored_stale"] == 2


def test_retry_private_alerts_does_not_repeatedly_attempt_unconfigured_line(app, monkeypatch):
    from tianwai.notifications import retry_private_alerts

    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    with app.app_context():
        connection = get_db()
        _insert_notification(connection, "line:risk:waiting", "skipped", utc_now())
        connection.commit()
        before = connection.execute(
            "SELECT attempts FROM notification_queue WHERE dedupe_key = 'line:risk:waiting'"
        ).fetchone()["attempts"]
        result = retry_private_alerts(limit=20)
        after = connection.execute(
            "SELECT attempts FROM notification_queue WHERE dedupe_key = 'line:risk:waiting'"
        ).fetchone()["attempts"]

    assert result["processed"] == 0
    assert result["deferred_unconfigured"] == 1
    assert after == before


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


def test_email_event_captures_insert_id_before_transaction_commit(app, monkeypatch):
    from tianwai.mailer import _record_event

    class CommitSensitiveCursor:
        def __init__(self, connection):
            self.connection = connection

        @property
        def lastrowid(self):
            if self.connection.committed:
                raise RuntimeError("insert id requested after transaction commit")
            return 73

    class CommitSensitiveConnection:
        def __init__(self):
            self.committed = False

        def execute(self, _statement, _parameters=()):
            return CommitSensitiveCursor(self)

        def commit(self):
            self.committed = True

    connection = CommitSensitiveConnection()
    monkeypatch.setattr("tianwai.mailer.get_db", lambda: connection)

    with app.app_context():
        event_id = _record_event(None, "activation", "customer@example.com", "sent")

    assert event_id == 73
    assert connection.committed is True


def test_brevo_https_delivery_records_status_without_persisting_secret(app, monkeypatch):
    from tianwai.mailer import send_email

    captured = {}

    class Response:
        status = 201
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(request_data, timeout):
        captured["request"] = request_data
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("tianwai.mailer.development_delivery_enabled", lambda: False)
    monkeypatch.setattr("tianwai.mailer.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("EMAIL_PROVIDER", "brevo")
    monkeypatch.setenv("BREVO_API_KEY", "test-brevo-api-key")
    monkeypatch.setenv("MAIL_FROM", "studio@example.com")
    monkeypatch.setenv("MAIL_FROM_NAME", "天外一筆工作室")

    with app.test_request_context("/customer/login"):
        result = send_email(
            "customer@example.com",
            "登入資料",
            "one-time secret body",
            "customer_login_code",
        )

    assert result == "sent"
    assert captured["request"].full_url == "https://api.brevo.com/v3/smtp/email"
    assert captured["request"].get_header("Api-key") == "test-brevo-api-key"
    assert captured["timeout"] == 15
    payload = json.loads(captured["request"].data.decode("utf-8"))
    assert payload["sender"] == {
        "name": "天外一筆工作室",
        "email": "studio@example.com",
    }
    assert payload["to"] == [{"email": "customer@example.com"}]
    assert payload["textContent"] == "one-time secret body"

    with app.app_context():
        row = get_db().execute(
            "SELECT recipient_masked, status, error_code FROM email_events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        stored = " ".join(str(value or "") for value in row)

    assert row["recipient_masked"] == "c***@example.com"
    assert row["status"] == "sent"
    assert "one-time secret body" not in stored
    assert "test-brevo-api-key" not in stored


def test_brevo_delivery_uses_verified_sender_id_without_sender_email(app, monkeypatch):
    from tianwai.mailer import email_delivery_ready, send_email

    captured = {}

    class Response:
        status = 201
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(request_data, timeout):
        captured["request"] = request_data
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("tianwai.mailer.development_delivery_enabled", lambda: False)
    monkeypatch.setattr("tianwai.mailer.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("EMAIL_PROVIDER", "brevo")
    monkeypatch.setenv("BREVO_API_KEY", "test-brevo-api-key")
    monkeypatch.setenv("BREVO_SENDER_ID", "42")
    monkeypatch.delenv("MAIL_FROM", raising=False)

    with app.test_request_context("/customer/login"):
        assert email_delivery_ready() is True
        result = send_email(
            "customer@example.com",
            "登入資料",
            "one-time secret body",
            "customer_login_code",
        )

    assert result == "sent"
    assert captured["timeout"] == 15
    payload = json.loads(captured["request"].data.decode("utf-8"))
    assert payload["sender"] == {"id": 42}
    assert "email" not in payload["sender"]


def test_brevo_delivery_rejects_invalid_sender_id(app, monkeypatch):
    from tianwai.mailer import email_delivery_ready

    monkeypatch.setattr("tianwai.mailer.development_delivery_enabled", lambda: False)
    monkeypatch.setenv("EMAIL_PROVIDER", "brevo")
    monkeypatch.setenv("BREVO_API_KEY", "test-brevo-api-key")
    monkeypatch.setenv("BREVO_SENDER_ID", "not-a-number")
    monkeypatch.setenv("MAIL_FROM", "studio@example.com")

    with app.test_request_context("/customer/login"):
        assert email_delivery_ready() is False
