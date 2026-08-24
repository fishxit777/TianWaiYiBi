import os

import pytest


pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").strip(),
    reason="TEST_DATABASE_URL is only provided by the PostgreSQL integration workflow",
)


def test_real_postgres_schema_seed_insert_and_row_mapping(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.setenv("APP_SECRET_KEY", "postgres-integration-secret-at-least-32-characters")
    monkeypatch.setenv("ADMIN_USERNAME", "integration-admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "integration-password-not-for-production")
    monkeypatch.setenv("BASE_URL", "http://localhost")

    from tianwai import create_app
    from tianwai.db import get_db, utc_now
    from tianwai.passkeys import authentication_challenge_allowed, create_challenge

    app = create_app({"TESTING": True})
    with app.app_context():
        connection = get_db()
        assert connection.backend == "postgresql"
        assert connection.execute("SELECT COUNT(*) AS count FROM ideas").fetchone()["count"] == 6
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

    response = app.test_client().get("/healthz")
    assert response.status_code == 200
    assert "postgresql" not in response.get_data(as_text=True).lower()
    assert os.environ["TEST_DATABASE_URL"] not in response.get_data(as_text=True)
