"""Isolated customer-session and one-use code regression checks."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest

from conftest import set_public_csrf
from tianwai import access
from tianwai.db import get_db, utc_now
from tianwai.security import hash_scoped_token


@pytest.fixture(autouse=True)
def isolate_external_services(monkeypatch):
    # The shared app fixture uses a temporary SQLite file. Explicitly prevent an
    # inherited deployment URL or LINE token from overriding that isolation.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(
        "tianwai.notifications.send_line_push", lambda _message: ("sent", "")
    )


def _session_cookies(app, client, email="session-owner@example.test"):
    with app.test_request_context("/"):
        raw_session, raw_device, session_id = access._create_customer_session(email)
    client.set_cookie(access.CUSTOMER_COOKIE, raw_session)
    client.set_cookie(access.DEVICE_COOKIE, raw_device)
    return raw_session, raw_device, session_id


def _session_row(app, session_id):
    with app.app_context():
        return dict(get_db().execute(
            "SELECT * FROM customer_sessions WHERE id = ?", (session_id,)
        ).fetchone())


def test_valid_paired_cookies_allow_access_without_ip_or_agent_binding(app, client):
    _session_cookies(app, client)

    response = client.get(
        "/customer/library",
        headers={"User-Agent": "updated-browser"},
        environ_overrides={"REMOTE_ADDR": "192.0.2.12"},
    )

    assert response.status_code == 200


@pytest.mark.parametrize("device_cookie", [None, "unrelated-device-cookie"])
def test_copied_session_cookie_without_its_device_is_rejected(app, client, device_cookie):
    raw_session, _raw_device, session_id = _session_cookies(app, client)
    copied = app.test_client()
    copied.set_cookie(access.CUSTOMER_COOKIE, raw_session)
    if device_cookie is not None:
        copied.set_cookie(access.DEVICE_COOKIE, device_cookie)
    before = _session_row(app, session_id)

    assert copied.get("/customer/library").status_code == 302
    after = _session_row(app, session_id)
    assert after["last_seen_at"] == before["last_seen_at"]
    assert after["idle_expires_at"] == before["idle_expires_at"]
    # Reject the copied cookie without allowing an unauthenticated client to
    # revoke the legitimate user's session.
    assert client.get("/customer/library").status_code == 200


@pytest.mark.parametrize("change", [
    "device_revoked", "device_expired", "missing_device", "foreign_device",
    "customer_blocked", "session_revoked", "session_expired", "session_idle_expired",
])
def test_session_rechecks_device_customer_and_lifetime_on_every_request(app, client, change):
    _raw_session, _raw_device, session_id = _session_cookies(app, client)
    assert client.get("/customer/library").status_code == 200
    previous = _session_row(app, session_id)
    with app.app_context():
        connection = get_db()
        expired = access._iso(access._now() - timedelta(seconds=1))
        if change == "device_revoked":
            connection.execute(
                "UPDATE customer_devices SET revoked_at = ? WHERE id = ?",
                (utc_now(), previous["device_id"]),
            )
        elif change == "device_expired":
            connection.execute(
                "UPDATE customer_devices SET trusted_until = ? WHERE id = ?",
                (expired, previous["device_id"]),
            )
        elif change == "missing_device":
            connection.execute(
                "UPDATE customer_sessions SET device_id = NULL WHERE id = ?", (session_id,)
            )
        elif change == "foreign_device":
            other = access._ensure_customer("other-owner@example.test")
            connection.execute(
                "UPDATE customer_devices SET customer_id = ? WHERE id = ?",
                (other["id"], previous["device_id"]),
            )
        elif change == "customer_blocked":
            connection.execute(
                "UPDATE customers SET status = 'suspended' WHERE id = ?",
                (previous["customer_id"],),
            )
        elif change == "session_revoked":
            connection.execute(
                "UPDATE customer_sessions SET revoked_at = ? WHERE id = ?",
                (utc_now(), session_id),
            )
        elif change == "session_expired":
            connection.execute(
                "UPDATE customer_sessions SET expires_at = ? WHERE id = ?", (expired, session_id)
            )
        else:
            connection.execute(
                "UPDATE customer_sessions SET idle_expires_at = ? WHERE id = ?",
                (expired, session_id),
            )
        connection.commit()

    assert client.get("/customer/library").status_code == 302


def _prepare_login(app, client):
    email = "login-owner@example.test"
    code = "23456789ABCD"
    with app.app_context():
        access._ensure_customer(email)
        connection = get_db()
        cursor = connection.execute(
            """
            INSERT INTO customer_login_codes
                (customer_email, code_hash, created_at, expires_at, requested_ip)
            VALUES (?, ?, ?, ?, ?)
            """,
            (email, hash_scoped_token("customer-login-code", code), utc_now(),
             access._iso(access._now() + timedelta(minutes=10)), "192.0.2.1"),
        )
        code_id = cursor.lastrowid
        connection.commit()
    csrf = set_public_csrf(client)
    with client.session_transaction() as state:
        state["customer_login_email"] = email
    return email, code, code_id, csrf


class _ConnectionProxy:
    def __init__(self, connection, before_consume=None, after_read=None):
        self.connection = connection
        self.before_consume = before_consume
        self.after_read = after_read

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, parameters=()):
        normalized = " ".join(statement.split())
        if normalized.startswith("UPDATE customer_login_codes SET used_at") and self.before_consume:
            self.before_consume(self.connection)
        cursor = self.connection.execute(statement, parameters)
        if normalized.startswith("SELECT * FROM customer_login_codes") and self.after_read:
            row = cursor.fetchone()
            self.after_read()

            class ReadResult:
                def fetchone(self):
                    return row

            return ReadResult()
        return cursor


@pytest.mark.parametrize("state", ["used", "revoked", "expired", "attempt_limit"])
def test_login_claim_rechecks_code_state_after_initial_read(app, client, monkeypatch, state):
    _email, code, code_id, csrf = _prepare_login(app, client)

    def invalidate_before_claim(connection):
        if state == "used":
            connection.execute(
                "UPDATE customer_login_codes SET used_at = ? WHERE id = ?", (utc_now(), code_id)
            )
        elif state == "revoked":
            connection.execute(
                "UPDATE customer_login_codes SET revoked_at = ? WHERE id = ?", (utc_now(), code_id)
            )
        elif state == "expired":
            connection.execute(
                "UPDATE customer_login_codes SET expires_at = ? WHERE id = ?",
                (access._iso(access._now() - timedelta(seconds=1)), code_id),
            )
        else:
            connection.execute(
                "UPDATE customer_login_codes SET failed_attempts = ? WHERE id = ?",
                (access.CODE_ATTEMPT_LIMIT, code_id),
            )
        connection.commit()

    monkeypatch.setattr(
        access, "get_db", lambda: _ConnectionProxy(get_db(), before_consume=invalidate_before_claim)
    )
    response = client.post(
        "/customer/login/verify", data={"csrf_token": csrf, "login_code": code}
    )

    assert response.status_code == 400
    assert client.get_cookie(access.CUSTOMER_COOKIE) is None
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM customer_sessions").fetchone()[0] == 0


def test_concurrent_login_code_claim_issues_exactly_one_session(app, monkeypatch):
    first, second = app.test_client(), app.test_client()
    email, code, code_id, first_csrf = _prepare_login(app, first)
    second_csrf = set_public_csrf(second)
    with second.session_transaction() as state:
        state["customer_login_email"] = email
    barrier = Barrier(2, timeout=10)
    # Force both independent SQLite connections to observe the same valid code
    # before either UPDATE. This reproduces the old double-consumption race.
    monkeypatch.setattr(
        access, "get_db", lambda: _ConnectionProxy(get_db(), after_read=barrier.wait)
    )

    def verify(client, csrf):
        return client.post(
            "/customer/login/verify", data={"csrf_token": csrf, "login_code": code}
        )

    with ThreadPoolExecutor(max_workers=2) as workers:
        attempts = [workers.submit(verify, first, first_csrf), workers.submit(verify, second, second_csrf)]
        responses = [attempt.result(timeout=15) for attempt in attempts]

    assert sorted(response.status_code for response in responses) == [302, 400]
    assert sum(client.get_cookie(access.CUSTOMER_COOKIE) is not None for client in (first, second)) == 1
    with app.app_context():
        connection = get_db()
        assert connection.execute("SELECT COUNT(*) FROM customer_sessions").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM customer_devices").fetchone()[0] == 1
        assert connection.execute(
            "SELECT used_at FROM customer_login_codes WHERE id = ?", (code_id,)
        ).fetchone()["used_at"] is not None
