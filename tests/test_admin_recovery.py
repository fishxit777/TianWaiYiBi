import json
import re
from types import SimpleNamespace

from conftest import login_admin, set_public_csrf
from tianwai.db import get_db
from tianwai.passkeys import store_registration_result
from tianwai.recovery import available_recovery_code_count, consume_recovery_code
from tianwai.security import hash_admin_password
from tianwai.turnstile import verify_turnstile


def _enable_recovery(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", hash_admin_password("correct-horse-battery-staple"))
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("ADMIN_RECOVERY_ENABLED", "true")
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "public-site-key")
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "private-secret-key")


def _register_credential(app, identifier, label):
    verified = SimpleNamespace(
        credential_id=identifier,
        credential_public_key=b"public-" + identifier,
        sign_count=0,
        aaguid="aaguid",
        credential_device_type=SimpleNamespace(value="multi_device"),
        credential_backed_up=True,
        user_verified=True,
    )
    with app.test_request_context("/admin/passkeys/setup"):
        return store_registration_result(verified, label=label, transports=["hybrid"])


def test_recovery_code_rotation_returns_plaintext_once_and_stores_only_argon2(app, client, monkeypatch):
    _enable_recovery(monkeypatch)
    csrf = login_admin(client)
    response = client.post(
        "/admin/api/passkeys/recovery-codes",
        headers={"X-CSRF-Token": csrf},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["count"] == 10
    assert len(set(payload["codes"])) == 10
    assert all(re.fullmatch(r"[A-Z2-7]{4}(?:-[A-Z2-7]{4}){5}-[A-Z2-7]{2}", code) for code in payload["codes"])
    with app.app_context():
        rows = get_db().execute("SELECT * FROM admin_recovery_codes").fetchall()
        serialized = json.dumps([dict(row) for row in rows], ensure_ascii=False)
        assert len(rows) == 10
        assert all(row["code_hash"].startswith("$argon2id$") for row in rows)
        assert all(code not in serialized for code in payload["codes"])
        assert available_recovery_code_count() == 10

    rotated = client.post(
        "/admin/api/passkeys/recovery-codes",
        headers={"X-CSRF-Token": csrf},
    ).get_json()
    with app.app_context():
        assert available_recovery_code_count() == 10
        old_active = get_db().execute(
            "SELECT COUNT(*) AS count FROM admin_recovery_codes WHERE revoked_at IS NULL AND id <= 10"
        ).fetchone()["count"]
        assert old_active == 0
    assert set(payload["codes"]).isdisjoint(rotated["codes"])


def test_wrong_password_does_not_consume_recovery_code(app, client, monkeypatch):
    _enable_recovery(monkeypatch)
    csrf = login_admin(client)
    code = client.post(
        "/admin/api/passkeys/recovery-codes",
        headers={"X-CSRF-Token": csrf},
    ).get_json()["codes"][0]
    client.post("/admin/logout", data={"csrf_token": csrf})
    public_csrf = set_public_csrf(client, "recovery-csrf")
    monkeypatch.setattr("tianwai.admin.verify_turnstile", lambda token, ip: True)
    response = client.post(
        "/admin/recovery",
        data={
            "csrf_token": public_csrf,
            "username": "keeper",
            "password": "wrong-password",
            "recovery_code": code,
            "cf-turnstile-response": "valid-token",
        },
    )
    assert response.status_code == 403
    with app.test_request_context("/admin/recovery"):
        assert consume_recovery_code(code) is True


def test_successful_recovery_revokes_sessions_and_passkeys_and_restricts_access(app, client, monkeypatch):
    _enable_recovery(monkeypatch)
    csrf = login_admin(client)
    code = client.post(
        "/admin/api/passkeys/recovery-codes",
        headers={"X-CSRF-Token": csrf},
    ).get_json()["codes"][0]
    _register_credential(app, b"old-windows", "Old Windows Hello")
    _register_credential(app, b"old-phone", "Old Phone")
    client.post(
        "/admin/api/passkeys/activate",
        headers={"X-CSRF-Token": csrf},
    )
    client.post("/admin/logout", data={"csrf_token": csrf})

    public_csrf = set_public_csrf(client, "recovery-success-csrf")
    monkeypatch.setattr("tianwai.admin.verify_turnstile", lambda token, ip: True)
    response = client.post(
        "/admin/recovery",
        data={
            "csrf_token": public_csrf,
            "username": "keeper",
            "password": "correct-horse-battery-staple",
            "recovery_code": code,
            "cf-turnstile-response": "valid-token",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/passkeys/setup")
    assert client.get("/admin", follow_redirects=False).headers["Location"].endswith("/admin/passkeys/setup")

    with app.app_context():
        active_sessions = get_db().execute(
            "SELECT * FROM admin_sessions WHERE revoked_at IS NULL"
        ).fetchall()
        active_keys = get_db().execute(
            "SELECT COUNT(*) AS count FROM admin_webauthn_credentials WHERE revoked_at IS NULL"
        ).fetchone()["count"]
        event = get_db().execute(
            "SELECT * FROM security_events WHERE event_type = 'admin_emergency_recovery'"
        ).fetchone()
        assert len(active_sessions) == 1
        assert active_sessions[0]["auth_method"] == "recovery"
        assert active_sessions[0]["restricted"] == 1
        assert active_keys == 0
        assert event["severity"] == "critical"
        assert code not in " ".join(str(value) for value in dict(event).values())


def test_restricted_recovery_session_needs_two_new_passkeys_before_completion(app, client, monkeypatch):
    _enable_recovery(monkeypatch)
    csrf = login_admin(client)
    code = client.post(
        "/admin/api/passkeys/recovery-codes",
        headers={"X-CSRF-Token": csrf},
    ).get_json()["codes"][0]
    client.post("/admin/logout", data={"csrf_token": csrf})
    public_csrf = set_public_csrf(client, "recovery-reenroll-csrf")
    monkeypatch.setattr("tianwai.admin.verify_turnstile", lambda token, ip: True)
    client.post(
        "/admin/recovery",
        data={
            "csrf_token": public_csrf,
            "username": "keeper",
            "password": "correct-horse-battery-staple",
            "recovery_code": code,
            "cf-turnstile-response": "valid-token",
        },
    )
    setup = client.get("/admin/passkeys/setup")
    admin_csrf = re.search(rb'<meta name="admin-csrf" content="([^"]+)"', setup.data).group(1).decode()
    assert b"\xe7\xb7\x8a\xe6\x80\xa5\xe5\xbe\xa9\xe5\x8e\x9f" in setup.data

    _register_credential(app, b"new-windows", "New Windows Hello")
    one_key = client.post(
        "/admin/api/passkeys/activate",
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert one_key.status_code == 409

    _register_credential(app, b"new-phone", "New Phone")
    completed = client.post(
        "/admin/api/passkeys/activate",
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert completed.status_code == 200
    assert client.get("/admin").status_code == 200
    with app.app_context():
        active = get_db().execute(
            "SELECT * FROM admin_sessions WHERE revoked_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert active["restricted"] == 0
        assert active["auth_method"] == "passkey"


def test_recovery_page_is_fail_closed_and_has_scoped_turnstile_csp(app, client, monkeypatch):
    assert client.get("/admin/recovery").status_code == 404
    _enable_recovery(monkeypatch)
    csrf = login_admin(client)
    client.post("/admin/api/passkeys/recovery-codes", headers={"X-CSRF-Token": csrf})
    client.post("/admin/logout", data={"csrf_token": csrf})
    response = client.get("/admin/recovery")
    policy = response.headers["Content-Security-Policy"]
    assert response.status_code == 200
    assert "https://challenges.cloudflare.com" in policy
    assert "frame-src https://challenges.cloudflare.com" in policy
    assert "private-secret-key" not in response.get_data(as_text=True)


def test_turnstile_requires_success_exact_action_and_hostname(app, monkeypatch):
    _enable_recovery(monkeypatch)

    class FakeResponse:
        status = 200

        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    with app.app_context():
        monkeypatch.setattr(
            "tianwai.turnstile.urllib.request.urlopen",
            lambda request, timeout: FakeResponse(
                {"success": True, "action": "admin-recovery", "hostname": "localhost"}
            ),
        )
        assert verify_turnstile("single-use-token", "127.0.0.1") is True
        assert (
            verify_turnstile(
                "single-use-token", "127.0.0.1", expected_action="public-conversation"
            )
            is False
        )

        monkeypatch.setattr(
            "tianwai.turnstile.urllib.request.urlopen",
            lambda request, timeout: FakeResponse(
                {"success": True, "action": "different-action", "hostname": "localhost"}
            ),
        )
        assert verify_turnstile("single-use-token", "127.0.0.1") is False

        monkeypatch.setattr(
            "tianwai.turnstile.urllib.request.urlopen",
            lambda request, timeout: FakeResponse(
                {"success": True, "action": "admin-recovery", "hostname": "attacker.invalid"}
            ),
        )
        assert verify_turnstile("single-use-token", "127.0.0.1") is False
