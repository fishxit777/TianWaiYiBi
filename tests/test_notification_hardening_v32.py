"""Offline, synthetic-only checks for TianWai's private admin outbox."""
import json
import sqlite3
import re
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Lock

import pytest

from tianwai.db import get_db, utc_now
from tianwai import notifications as n


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "synthetic-tianwai-token")
    monkeypatch.setenv("LINE_ADMIN_USER_ID", "U" + "a" * 32)


def _queue(index=1):
    return n.queue_security_alert(
        index, level="high", event_type="sensitive_path_probe", event_id=f"SE-{index}",
        path="/private/synthetic-sensitive-value?key=hidden-value",
        detail="unstructured private concept and credentials", user_agent="private-agent",
        customer_public_id="private-customer", action_taken="rejected",
    )


def test_event_payload_uses_allowlist_not_free_text(app):
    with app.app_context():
        message = n._event_messages(
            level="high", event_type="unknown-private-type", event_id="private-event",
            incident_no="private-incident", customer_public_id="private-customer",
            path="/private/path?secret=unknown", user_agent="private-agent",
            detail="private concept with no keyword", action_taken="private-action",
        )
    for value in ("unknown-private-type", "private-event", "private-incident", "private-customer",
                  "/private/path", "private-agent", "private concept", "private-action"):
        assert value not in message
    assert "高風險" in message
    assert n.mask_ip("private:paid:content") == "masked"


@pytest.mark.parametrize("recipient", ["C" + "a" * 32, "R" + "a" * 32, "Ubad", ""])
def test_line_refuses_non_private_or_invalid_recipient(app, configured, monkeypatch, recipient):
    monkeypatch.setenv("LINE_ADMIN_USER_ID", recipient)
    monkeypatch.setattr(n.urllib.request, "urlopen", lambda *_a, **_k: pytest.fail("must not send"))
    with app.app_context():
        status, _ = n.send_line_push("synthetic", retry_key="00000000-0000-4000-8000-000000000001")
    assert status == "skipped"


def test_ambiguous_retry_has_same_provider_key_and_backoff(app, configured, monkeypatch):
    requests = []
    def fail(request, **_kwargs):
        requests.append(request)
        raise TimeoutError()
    monkeypatch.setattr(n.urllib.request, "urlopen", fail)
    with app.app_context():
        _queue()
        _queue()
        assert len(requests) == 1
        assert n.retry_private_alerts()["processed"] == 0
        get_db().execute("UPDATE notification_queue SET next_attempt_at = ''")
        get_db().commit()
        assert n.retry_private_alerts()["processed"] == 1
        row = get_db().execute("SELECT * FROM notification_queue").fetchone()
    assert len(requests) == 2
    assert requests[0].get_header("X-line-retry-key")
    assert requests[0].get_header("X-line-retry-key") == requests[1].get_header("X-line-retry-key")
    assert requests[0].data == requests[1].data
    assert row["attempts"] == 2
    assert row["next_attempt_at"] > row["updated_at"]


def test_retry_exhaustion_is_terminal(app, configured, monkeypatch):
    monkeypatch.setattr(n, "_deliver", lambda _row: ("failed", "network_error"))
    with app.app_context():
        _queue()
        for _ in range(8):
            get_db().execute("UPDATE notification_queue SET next_attempt_at = ''")
            get_db().commit()
            n.retry_private_alerts()
        row = get_db().execute("SELECT * FROM notification_queue").fetchone()
    assert row["attempts"] == n.MAX_DELIVERY_ATTEMPTS
    assert row["last_error"] == "retry_exhausted"


def test_atomic_claim_prevents_reentrant_delivery(app, configured, monkeypatch):
    delivered = []
    def deliver(row):
        delivered.append(row["id"])
        assert n.retry_private_alerts()["processed"] == 0
        return "sent", ""
    monkeypatch.setattr(n, "_deliver", deliver)
    with app.app_context():
        _queue()
    assert len(delivered) == 1


def test_crash_lease_recovers_but_stale_worker_cannot_finalize(app, configured, monkeypatch):
    monkeypatch.setattr(n, "_deliver", lambda _row: ("failed", "network_error"))
    with app.app_context():
        _queue()
        connection = get_db()
        connection.execute("UPDATE notification_queue SET next_attempt_at = '', claim_token = 'old-worker', claimed_until = '2000-01-01T00:00:00+00:00'")
        connection.commit()
        row = connection.execute("SELECT * FROM notification_queue").fetchone()
        claimed = n._claim_delivery(row)
        assert claimed is not None
        assert claimed["claim_token"] != "old-worker"
        n._persist_delivery(row["id"], "sent", "", "old-worker")
        assert connection.execute("SELECT status FROM notification_queue").fetchone()["status"] != "sent"


def test_alert_storm_bounded_and_summary_has_separate_capacity(app, configured, monkeypatch):
    delivered = []
    monkeypatch.setattr(n, "_deliver", lambda row: (delivered.append(row["id"]) or "sent", ""))
    with app.app_context():
        for index in range(1, 31):
            _queue(index)
        assert len(delivered) <= n.ALERT_WINDOW_LIMIT
        summary = n.queue_daily_summary("noon")
        assert summary["channels"]["line"] == "sent"
        assert get_db().execute("SELECT COUNT(*) AS count FROM notification_queue WHERE next_attempt_at > updated_at").fetchone()["count"] > 0


def test_legacy_payload_is_never_transmitted(app, configured, monkeypatch):
    monkeypatch.setattr(n.urllib.request, "urlopen", lambda *_a, **_k: pytest.fail("legacy payload sent"))
    with app.app_context():
        row = {"channel": "line", "payload_json": json.dumps({"message": "private legacy text"})}
        assert n._deliver(row) == ("skipped", "legacy_payload_disabled")


def test_retry_stops_after_provider_key_window_or_recipient_change(app, configured, monkeypatch):
    monkeypatch.setattr(n, "send_line_push", lambda *_a, **_k: ("failed", "network_error"))
    with app.app_context():
        _queue()
        connection = get_db()
        connection.execute("UPDATE notification_queue SET next_attempt_at = '', first_attempt_at = ?", ((datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(timespec="seconds"),))
        connection.commit()
        row = connection.execute("SELECT * FROM notification_queue").fetchone()
        assert n._deliver(row) == ("skipped", "provider_retry_window_expired")
        connection.execute("UPDATE notification_queue SET first_attempt_at = ?", (utc_now(),))
        connection.commit()
        monkeypatch.setenv("LINE_ADMIN_USER_ID", "U" + "b" * 32)
        row = connection.execute("SELECT * FROM notification_queue").fetchone()
        assert n._deliver(row) == ("skipped", "recipient_configuration_changed")


def test_provider_409_requires_acceptance_header(app, configured, monkeypatch):
    headers = {"x-line-accepted-request-id": "synthetic-accepted"}
    def conflict(*_a, **_k):
        raise urllib.error.HTTPError("https://api.line.me", 409, "Conflict", headers, None)
    monkeypatch.setattr(n.urllib.request, "urlopen", conflict)
    with app.app_context():
        assert n.send_line_push("synthetic", retry_key="00000000-0000-4000-8000-000000000001") == ("sent", "")
        headers.clear()
        assert n.send_line_push("synthetic", retry_key="00000000-0000-4000-8000-000000000001") == ("failed", "http_409")


def test_daily_summary_never_exposes_private_idea_title(app):
    with app.app_context():
        connection = get_db()
        idea_id = connection.execute("SELECT id FROM ideas LIMIT 1").fetchone()["id"]
        connection.execute("UPDATE ideas SET title = 'synthetic-private-paid-title' WHERE id = ?", (idea_id,))
        connection.execute("INSERT INTO analytics_events (event_name, idea_id, source, session_id, created_at) VALUES ('view_idea', ?, 'web', 'synthetic', ?)", (idea_id, utc_now()))
        connection.commit()
        assert "synthetic-private-paid-title" not in n.build_daily_summary("noon")["line"]


def test_low_or_medium_events_stay_local(app, configured, monkeypatch):
    monkeypatch.setattr(n.urllib.request, "urlopen", lambda *_a, **_k: pytest.fail("low-risk push"))
    with app.app_context():
        for level in ("low", "medium", "unknown"):
            assert n.queue_security_alert(1, level=level)["queued"] == 0
            assert n.queue_private_alert(None, "", level, "probe", "")["queued"] == 0
        assert get_db().execute("SELECT COUNT(*) AS n FROM notification_queue").fetchone()["n"] == 0


def test_cross_connection_workers_cannot_double_claim_or_exceed_quota(app, configured, monkeypatch):
    delivered = []
    lock = Lock()
    def deliver(row):
        with lock:
            delivered.append(row["id"])
        return "sent", ""
    monkeypatch.setattr(n, "_deliver", deliver)
    original_ready = n.line_admin_delivery_ready
    monkeypatch.setattr(n, "line_admin_delivery_ready", lambda: False)
    with app.app_context():
        for index in range(1, 21):
            _queue(index)
        first = dict(get_db().execute("SELECT * FROM notification_queue LIMIT 1").fetchone())
    monkeypatch.setattr(n, "line_admin_delivery_ready", original_ready)
    barrier = Barrier(2)
    def competing_claim():
        with app.app_context():
            barrier.wait(timeout=5)
            return n._attempt_delivery(first)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _i: competing_claim(), range(2)))
    assert results.count("sent") == 1
    assert results.count(None) == 1
    def worker():
        with app.app_context():
            return n.retry_private_alerts(limit=50)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _i: worker(), range(4)))
    assert len(delivered) == len(set(delivered)) == n.ALERT_WINDOW_LIMIT
    with app.app_context():
        buckets = get_db().execute("SELECT attempts FROM notification_delivery_windows WHERE bucket_key LIKE 'tianwai:line:alert:300:%'").fetchall()
    assert max(row["attempts"] for row in buckets) <= n.ALERT_WINDOW_LIMIT


def test_permanent_provider_error_does_not_retry(app, configured, monkeypatch):
    calls = []
    monkeypatch.setattr(n, "_deliver", lambda row: (calls.append(row["id"]) or "failed", "http_401"))
    with app.app_context():
        _queue()
        assert n.retry_private_alerts()["processed"] == 0
        row = get_db().execute("SELECT * FROM notification_queue").fetchone()
    assert len(calls) == 1
    assert row["retryable"] == 0
    assert row["last_error"] == "http_401"


def test_additive_migration_is_idempotent_and_keeps_claims(tmp_path):
    from tianwai.db import migrate_notification_outbox
    connection = sqlite3.connect(tmp_path / "legacy-outbox.db")
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE notification_queue (id INTEGER PRIMARY KEY, channel TEXT, status TEXT, attempts INTEGER)")
    connection.execute("INSERT INTO notification_queue VALUES (1, 'line', 'pending', 2)")
    migrate_notification_outbox(connection)
    connection.execute("UPDATE notification_queue SET claim_token = 'synthetic-claim', claimed_until = '2099-01-01', provider_retry_key = 'stable-key', next_attempt_at = '2099-01-02'")
    connection.commit()
    before = dict(connection.execute("SELECT * FROM notification_queue").fetchone())
    migrate_notification_outbox(connection)
    connection.commit()
    after = dict(connection.execute("SELECT * FROM notification_queue").fetchone())
    connection.close()
    assert before == after


def test_existing_summary_job_runs_only_bounded_project_retry(client, monkeypatch):
    retries = []
    monkeypatch.setattr("tianwai.notification_routes.retry_private_alerts", lambda limit: retries.append(limit) or {"processed": 0})
    monkeypatch.setattr("tianwai.notification_routes.queue_daily_summary", lambda slot: {"slot": slot})
    assert client.post("/internal/notifications/daily-summary", json={"slot": "noon"}).status_code == 404
    assert retries == []
    result = client.post("/internal/notifications/daily-summary", json={"slot": "noon"}, headers={"X-Notification-Secret": "test-notification-secret-with-at-least-32-characters"})
    assert result.status_code == 200
    assert retries == [10]


def test_retry_loop_obeys_time_budget(app, configured, monkeypatch):
    clock = [0]
    monkeypatch.setattr(n.time, "monotonic", lambda: clock[0])
    original_ready = n.line_admin_delivery_ready
    monkeypatch.setattr(n, "line_admin_delivery_ready", lambda: False)
    with app.app_context():
        for index in range(1, 4):
            _queue(index)
        monkeypatch.setattr(n, "line_admin_delivery_ready", original_ready)
        def deliver(_row):
            clock[0] += 8
            return "failed", "network_error"
        monkeypatch.setattr(n, "_deliver", deliver)
        assert n.retry_private_alerts(limit=10)["processed"] == 1


def test_postgres_migration_uses_additive_idempotent_sql():
    from tianwai.db import migrate_notification_outbox, _postgres_sql
    class Cursor:
        def __init__(self, columns):
            self.columns = columns
        def fetchall(self):
            return [{"name": name} for name in self.columns]
    class PortableConnection:
        backend = "postgresql"
        def __init__(self):
            self.columns = {"id", "channel", "status"}
            self.sql = []
        def execute(self, sql, _parameters=()):
            self.sql.append(_postgres_sql(sql))
            match = re.search(r"ADD COLUMN IF NOT EXISTS (\w+)", sql)
            if match:
                self.columns.add(match.group(1))
            return Cursor(self.columns)
    connection = PortableConnection()
    migrate_notification_outbox(connection)
    added = sum("ADD COLUMN" in sql for sql in connection.sql)
    assert added == 7
    migrate_notification_outbox(connection)
    assert sum("ADD COLUMN" in sql for sql in connection.sql) == added
    assert not any("PRAGMA" in sql or "UPDATE notification_queue" in sql for sql in connection.sql)


def _claim_fifth_attempt(connection):
    connection.execute("UPDATE notification_queue SET attempts = ?, next_attempt_at = ''", (n.MAX_DELIVERY_ATTEMPTS - 1,))
    connection.commit()
    return n._claim_delivery(connection.execute("SELECT * FROM notification_queue LIMIT 1").fetchone())


def test_last_attempt_crash_is_finalized_after_lease_expiry(app, configured, monkeypatch):
    original_ready = n.line_admin_delivery_ready
    monkeypatch.setattr(n, "line_admin_delivery_ready", lambda: False)
    with app.app_context():
        _queue()
        monkeypatch.setattr(n, "line_admin_delivery_ready", original_ready)
        connection = get_db()
        claimed = _claim_fifth_attempt(connection)
        assert claimed["attempts"] == n.MAX_DELIVERY_ATTEMPTS
        connection.execute("UPDATE notification_queue SET claimed_until = '2000-01-01T00:00:00+00:00'")
        connection.commit()
        monkeypatch.setattr(n, "_deliver", lambda _row: pytest.fail("exhausted request repeated"))
        result = n.retry_private_alerts()
        row = connection.execute("SELECT * FROM notification_queue").fetchone()
        assert result["processed"] == 0
        assert row["status"] == "failed"
        assert row["last_error"] == "retry_exhausted"
        assert row["retryable"] == 0
        assert row["claim_token"] == row["claimed_until"] == row["next_attempt_at"] == ""
        n._persist_delivery(row["id"], "sent", "", claimed["claim_token"])
        assert connection.execute("SELECT status FROM notification_queue").fetchone()["status"] == "failed"


def test_last_attempt_active_lease_is_not_finalized(app, configured, monkeypatch):
    original_ready = n.line_admin_delivery_ready
    monkeypatch.setattr(n, "line_admin_delivery_ready", lambda: False)
    with app.app_context():
        _queue()
        monkeypatch.setattr(n, "line_admin_delivery_ready", original_ready)
        connection = get_db()
        claimed = dict(_claim_fifth_attempt(connection))
        monkeypatch.setattr(n, "_deliver", lambda _row: pytest.fail("active request repeated"))
        assert n.retry_private_alerts()["processed"] == 0
        assert dict(connection.execute("SELECT * FROM notification_queue").fetchone()) == claimed
        n._persist_delivery(claimed["id"], "sent", "", claimed["claim_token"])
        assert connection.execute("SELECT status FROM notification_queue").fetchone()["status"] == "sent"
