import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from urllib.parse import urlparse, urlsplit, urlunsplit

import pytest


pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").strip(),
    reason="TEST_DATABASE_URL is only provided by the PostgreSQL integration workflow",
)


@pytest.fixture
def pg_app(monkeypatch):
    # These integration checks may create synthetic data: refuse remote targets.
    test_url = os.environ["TEST_DATABASE_URL"]
    assert urlparse(test_url).hostname in {"127.0.0.1", "localhost", "::1"}
    monkeypatch.setenv("DATABASE_URL", test_url)
    monkeypatch.setenv("APP_SECRET_KEY", "postgres-integration-secret-at-least-32-characters")
    monkeypatch.setenv("ADMIN_USERNAME", "integration-admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "integration-password-not-for-production")
    monkeypatch.setenv("BASE_URL", "http://localhost")

    from tianwai import create_app

    return create_app({"TESTING": True})


def test_real_postgres_schema_seed_insert_and_row_mapping(pg_app):
    from tianwai.db import get_db, utc_now
    from tianwai.passkeys import authentication_challenge_allowed, create_challenge

    app = pg_app
    with app.app_context():
        connection = get_db()
        assert connection.backend == "postgresql"
        published = connection.execute(
            "SELECT public_title, sort_order FROM ideas WHERE published = 1 ORDER BY sort_order"
        ).fetchall()
        assert len(published) == 13
        assert [row["sort_order"] for row in published] == list(range(1, 14))
        assert all(row["public_title"].startswith("封印盲策・第") for row in published)
        cursor = connection.execute(
            "INSERT INTO audit_logs (action, target, detail, ip, created_at) VALUES (?, ?, ?, ?, ?)",
            ("postgres_ci", "database", "adapter_verified", "127.0.0.1", utc_now()),
        )
        connection.commit()
        assert cursor.lastrowid > 0
        row = connection.execute(
            "SELECT action, detail FROM audit_logs WHERE action = ?", ("postgres_ci",)
        ).fetchone()
        assert dict(row) == {"action": "postgres_ci", "detail": "adapter_verified"}
        index = connection.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = ? AND indexname = ?
            """,
            ("admin_webauthn_challenges", "idx_admin_webauthn_challenge_ip_time"),
        ).fetchone()
        assert index is not None

    with app.test_request_context("/admin/identity/options"):
        assert authentication_challenge_allowed() is True
        for _ in range(10):
            create_challenge("authentication")
        assert authentication_challenge_allowed() is False

    with app.test_request_context("/activate/postgres-session-check"):
        from tianwai.access import _create_customer_session

        raw_session, raw_device, session_id = _create_customer_session(
            "postgres-session-check@example.com"
        )
        assert raw_session
        assert session_id > 0
        assert isinstance(raw_device, str)

    response = app.test_client().get("/healthz")
    assert response.status_code == 200
    assert "postgresql" not in response.get_data(as_text=True).lower()
    assert os.environ["TEST_DATABASE_URL"] not in response.get_data(as_text=True)


def test_real_postgres_legacy_outbox_migration_preserves_claim(pg_app):
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
    from tianwai.db import PostgresConnection, migrate_notification_outbox

    # An isolated schema leaves the app's real synthetic queue untouched.
    schema = "v32_legacy_" + uuid.uuid4().hex
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], row_factory=dict_row) as native:
        native.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        native.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        native.execute("CREATE TABLE notification_queue (id INTEGER PRIMARY KEY, channel TEXT, status TEXT, attempts INTEGER)")
        native.execute("INSERT INTO notification_queue VALUES (1, 'line', 'pending', 2)")
        adapter = PostgresConnection(native)
        migrate_notification_outbox(adapter)
        adapter.execute(
            "UPDATE notification_queue SET claim_token = 'synthetic-claim', claimed_until = '2099-01-01', "
            "provider_retry_key = 'synthetic-stable-key', next_attempt_at = '2099-01-02' WHERE id = 1"
        )
        adapter.commit()
        before = dict(adapter.execute("SELECT * FROM notification_queue WHERE id = 1").fetchone())
        migrate_notification_outbox(adapter)
        adapter.commit()
        assert dict(adapter.execute("SELECT * FROM notification_queue WHERE id = 1").fetchone()) == before
        assert before["attempts"] == 2
        assert before["retryable"] == 1


def test_real_postgres_two_workers_claim_once_without_network(pg_app, monkeypatch):
    from tianwai import notifications as n
    from tianwai.db import get_db

    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "synthetic-pg-line-token")
    monkeypatch.setenv("LINE_ADMIN_USER_ID", "U" + "a" * 32)
    monkeypatch.setattr(n.urllib.request, "urlopen", lambda *_a, **_k: pytest.fail("external send forbidden"))
    ready = n.line_admin_delivery_ready
    monkeypatch.setattr(n, "line_admin_delivery_ready", lambda: False)
    key = "v32-pg-cas-" + uuid.uuid4().hex
    with pg_app.app_context():
        n.queue_admin_messages(key, line_message="synthetic test only")
        row = dict(get_db().execute("SELECT * FROM notification_queue WHERE dedupe_key = ?", ("line:" + key,)).fetchone())
    monkeypatch.setattr(n, "line_admin_delivery_ready", ready)
    delivered = []
    lock = Lock()
    def deliver(claimed):
        with lock:
            delivered.append(claimed["id"])
        return "sent", ""
    monkeypatch.setattr(n, "_deliver", deliver)
    barrier = Barrier(2, timeout=10)
    def claim():
        with pg_app.app_context():
            barrier.wait()
            return n._attempt_delivery(row)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _i: claim(), range(2)))
    assert results.count("sent") == 1
    assert results.count(None) == 1
    assert delivered == [row["id"]]
    with pg_app.app_context():
        stored = get_db().execute("SELECT attempts, status, claim_token FROM notification_queue WHERE id = ?", (row["id"],)).fetchone()
    assert dict(stored) == {"attempts": 1, "status": "sent", "claim_token": ""}


def test_real_postgres_concurrent_login_code_is_single_use(pg_app, monkeypatch):
    from conftest import set_public_csrf
    from test_session_hardening_v32 import _ConnectionProxy, _prepare_login
    from tianwai import access
    from tianwai.db import get_db

    first, second = pg_app.test_client(), pg_app.test_client()
    email, code, code_id, first_csrf = _prepare_login(pg_app, first)
    second_csrf = set_public_csrf(second)
    with second.session_transaction() as state:
        state["customer_login_email"] = email
    barrier = Barrier(2, timeout=10)
    monkeypatch.setattr(access, "get_db", lambda: _ConnectionProxy(get_db(), after_read=barrier.wait))
    def verify(client, csrf):
        return client.post("/customer/login/verify", data={"csrf_token": csrf, "login_code": code})
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(verify, first, first_csrf), workers.submit(verify, second, second_csrf)]
        responses = [future.result(timeout=20) for future in futures]
    assert sorted(response.status_code for response in responses) == [302, 400]
    assert sum(client.get_cookie(access.CUSTOMER_COOKIE) is not None for client in (first, second)) == 1
    with pg_app.app_context():
        assert get_db().execute("SELECT used_at FROM customer_login_codes WHERE id = ?", (code_id,)).fetchone()["used_at"]


def test_real_postgres_two_workers_initialize_empty_database(pg_app, monkeypatch):
    import psycopg
    from psycopg import sql
    from tianwai import create_app, db

    # Each run gets a brand-new synthetic database, never an existing app schema.
    database_name = "v32_boot_" + uuid.uuid4().hex
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as native:
        native.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    parsed = urlsplit(os.environ["TEST_DATABASE_URL"])
    isolated_url = urlunsplit((parsed.scheme, parsed.netloc, "/" + database_name, parsed.query, parsed.fragment))
    monkeypatch.setenv("DATABASE_URL", isolated_url)
    connect = db._connect_postgres
    barrier = Barrier(2, timeout=10)
    counter_lock = Lock()
    opened = []
    def synchronized_connect(value):
        connection = connect(value)
        with counter_lock:
            opened.append(True)
            position = len(opened)
        if position <= 2:
            # Both real connections exist before either worker starts DDL.
            barrier.wait()
        return connection
    monkeypatch.setattr(db, "_connect_postgres", synchronized_connect)
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(create_app, {"TESTING": True}) for _ in range(2)]
        applications = [future.result(timeout=30) for future in futures]
    for application in applications:
        with application.app_context():
            connection = db.get_db()
            assert connection.execute("SELECT COUNT(*) AS n FROM ideas WHERE published = 1").fetchone()["n"] == 13
            assert connection.execute("SELECT COUNT(*) AS n FROM notification_delivery_windows").fetchone()["n"] == 0
        assert application.test_client().get("/healthz").status_code == 200


def test_real_postgres_full_daily_summary_route_is_deduplicated(pg_app, monkeypatch):
    import traceback
    from pathlib import Path
    from tianwai import notifications as n

    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "synthetic-pg-summary-token")
    monkeypatch.setenv("LINE_ADMIN_USER_ID", "U" + "b" * 32)
    secret = "synthetic-summary-secret-at-least-32-characters"
    monkeypatch.setenv("NOTIFICATION_CRON_SECRET", secret)
    monkeypatch.setattr(n.urllib.request, "urlopen", lambda *_a, **_k: pytest.fail("external send forbidden"))
    sent = []
    monkeypatch.setattr(n, "send_line_push", lambda message, **_kwargs: (sent.append(message) or "sent", ""))
    client = pg_app.test_client()
    for _ in range(2):
        try:
            response = client.post(
                "/internal/notifications/daily-summary", json={"slot": "noon"},
                headers={"X-Notification-Secret": secret},
            )
        except Exception as error:
            locations = [f"{Path(frame.filename).name}:{frame.lineno}" for frame in traceback.extract_tb(error.__traceback__)
                         if Path(frame.filename).name in {"notifications.py", "notification_routes.py", "db.py"}]
            pytest.fail(f"summary_route_error={type(error).__name__}; locations={' > '.join(locations)}", pytrace=False)
        assert response.status_code == 200
        assert response.get_json()["channels"]["line"] == "sent"
    assert len(sent) == 1
