import sqlite3
import re

from conftest import login_admin, set_public_csrf
from test_customer_access import _pay_and_get_activation
from tianwai.security import (
    ADMIN_PASSWORD_ENTROPY_BITS,
    generate_admin_password,
    hash_admin_password,
    verify_admin_password,
)


def test_generated_admin_password_has_256_bits_and_password_manager_safe_format():
    passwords = {generate_admin_password() for _ in range(20)}

    assert ADMIN_PASSWORD_ENTROPY_BITS == 256
    assert len(passwords) == 20
    assert all(len(password) == 43 for password in passwords)
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{43}", password) for password in passwords)


def test_admin_password_hash_uses_argon2id_without_plaintext():
    password = generate_admin_password()
    encoded = hash_admin_password(password)

    assert encoded.startswith("$argon2id$")
    assert "m=19456,t=2,p=1" in encoded
    assert password not in encoded
    assert verify_admin_password(password, encoded) is True
    assert verify_admin_password(password + "x", encoded) is False


def test_argon2_admin_hash_takes_priority_and_prevents_plaintext_downgrade(client, monkeypatch):
    password = generate_admin_password()
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", hash_admin_password(password))
    monkeypatch.setenv("ADMIN_PASSWORD", "correct-horse-battery-staple")
    csrf = set_public_csrf(client)

    legacy = client.post(
        "/admin/login",
        data={"username": "keeper", "password": "correct-horse-battery-staple", "csrf_token": csrf},
    )
    accepted = client.post(
        "/admin/login",
        data={"username": "keeper", "password": password, "csrf_token": csrf},
    )

    assert legacy.status_code == 403
    assert accepted.status_code == 302


def test_admin_dashboard_reports_argon2_status_without_exposing_hash(client, monkeypatch):
    login_admin(client)
    legacy = client.get("/admin/api/dashboard").get_json()["security_config"]
    encoded = hash_admin_password(generate_admin_password())
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", encoded)
    upgraded_response = client.get("/admin/api/dashboard")
    upgraded = upgraded_response.get_json()["security_config"]

    assert legacy["admin_password_argon2"] is False
    assert upgraded["admin_password_argon2"] is True
    assert encoded not in upgraded_response.get_data(as_text=True)


def test_admin_login_failure_is_generic(client):
    csrf = set_public_csrf(client)
    response = client.post(
        "/admin/login",
        data={"username": "unknown", "password": "wrong", "csrf_token": csrf},
    )

    assert response.status_code == 403
    assert "帳號或密碼錯誤" in response.get_data(as_text=True)
    assert "unknown" not in response.get_data(as_text=True)


def test_admin_login_uses_professional_v16_design_layer(client):
    body = client.get("/admin/login").get_data(as_text=True)

    assert "static/v16.css" in body
    assert "授權身分驗證" in body


def test_admin_session_is_hashed_in_database(app, client):
    login_admin(client)
    cookie = client.get_cookie("twyb_admin", path="/admin")
    assert cookie is not None

    connection = sqlite3.connect(app.config["DATABASE"])
    row = connection.execute("SELECT session_hash FROM admin_sessions").fetchone()
    connection.close()

    assert row is not None
    assert cookie.value not in row[0]
    assert len(row[0]) == 64


def test_admin_api_requires_authentication(client):
    response = client.get("/admin/api/dashboard")

    assert response.status_code == 401


def test_admin_dashboard_uses_six_separate_operational_workspaces(client):
    login_admin(client)
    body = client.get("/admin").get_data(as_text=True)

    for workspace in ("overview", "orders", "ideas", "customers", "integrations", "security"):
        assert f'data-admin-view="{workspace}"' in body
        assert f'data-admin-panel="{workspace}"' in body
    assert "今日需要處理" in body
    assert "開通碼、登入碼與私密連結不會在後台曝光" in body
    assert 'data-admin-panel="orders" hidden' in body
    assert "static/v16.css" in body
    assert 'class="admin-environment"' in body
    assert 'id="last-sync"' in body
    assert 'aria-pressed="true">全部' in body
    assert "metric-skeleton" in body


def test_admin_customer_access_summary_tracks_paid_then_activated(client):
    login_admin(client)
    _, activation_link, activation_code = _pay_and_get_activation(client)

    paid = client.get("/admin/api/dashboard").get_json()["customer_access"]
    assert paid["summary"]["paid_customers"] == 1
    assert paid["summary"]["paid_entitlements"] == 1
    assert paid["summary"]["pending_activation"] == 1
    assert paid["orders"][0]["activated"] is False

    csrf = set_public_csrf(client, "admin-access-test-csrf")
    response = client.post(
        activation_link,
        data={"csrf_token": csrf, "activation_code": activation_code},
        follow_redirects=True,
    )
    assert response.status_code == 200

    activated = client.get("/admin/api/dashboard").get_json()["customer_access"]
    assert activated["summary"]["activated_entitlements"] == 1
    assert activated["summary"]["pending_activation"] == 0
    assert activated["summary"]["active_sessions"] == 1
    assert activated["orders"][0]["activated"] is True
    assert "traveler@example.com" not in str(activated["orders"])


def test_admin_price_change_requires_csrf_and_writes_audit(app, client):
    csrf = login_admin(client)
    rejected = client.post("/admin/api/settings/price", json={"price": 299})
    accepted = client.post(
        "/admin/api/settings/price",
        json={"price": 299},
        headers={"X-CSRF-Token": csrf},
    )

    assert rejected.status_code == 403
    assert accepted.status_code == 200
    assert accepted.get_json()["price"] == 299

    connection = sqlite3.connect(app.config["DATABASE"])
    audit = connection.execute(
        "SELECT action, target FROM audit_logs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    connection.close()
    assert audit == ("update_global_price", "299")


def test_sensitive_path_is_blocked_and_logged(app, client):
    response = client.get("/.env")

    assert response.status_code == 404
    connection = sqlite3.connect(app.config["DATABASE"])
    event = connection.execute(
        "SELECT event_type FROM security_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    connection.close()
    assert event[0] == "sensitive_path_probe"


def test_security_test_endpoint_creates_event(client):
    csrf = login_admin(client)
    response = client.post(
        "/admin/api/security/test",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 201
    dashboard = client.get("/admin/api/dashboard").get_json()
    assert any(item["event_type"] == "manual_security_test" for item in dashboard["security_events"])


def test_admin_can_inspect_and_revoke_trusted_device(app, client):
    csrf = login_admin(client)
    _, activation_link, activation_code = _pay_and_get_activation(client)
    public_csrf = set_public_csrf(client, "device-admin-csrf")
    client.post(
        activation_link,
        data={"csrf_token": public_csrf, "activation_code": activation_code},
        follow_redirects=True,
    )

    dashboard = client.get("/admin/api/dashboard").get_json()
    device = dashboard["customer_devices"][0]
    assert dashboard["evidence_chain"]["valid"] is True
    assert device["customer_public_id"].startswith("TYB-")
    assert device["last_ip"].endswith("*.*")

    revoked = client.post(
        f"/admin/api/customers/devices/{device['id']}/revoke",
        headers={"X-CSRF-Token": csrf},
    )
    assert revoked.status_code == 200
    assert client.get("/customer/library").status_code == 302


def test_admin_can_update_incident_and_retry_private_alerts(app, client):
    from tianwai.risk import record_access_event

    csrf = login_admin(client)
    with app.test_request_context("/test-risk", environ_base={"REMOTE_ADDR": "203.0.113.44"}):
        record_access_event("automated_security_test", 70, "rejected")

    dashboard = client.get("/admin/api/dashboard").get_json()
    incident = dashboard["risk_incidents"][0]
    updated = client.post(
        f"/admin/api/security/incidents/{incident['id']}",
        json={"status": "resolved"},
        headers={"X-CSRF-Token": csrf},
    )
    retried = client.post(
        "/admin/api/security/notifications/retry",
        headers={"X-CSRF-Token": csrf},
    )
    assert updated.status_code == 200
    assert updated.get_json()["status"] == "resolved"
    assert retried.status_code == 200
    assert retried.get_json()["processed"] >= 1


def test_repeated_bad_logins_trigger_temporary_block(client):
    csrf = set_public_csrf(client)
    statuses = []
    for _ in range(6):
        response = client.post(
            "/admin/login",
            data={"username": "keeper", "password": "wrong", "csrf_token": csrf},
        )
        statuses.append(response.status_code)

    assert 429 in statuses


def _editable_idea_payload(idea):
    return {
        "title": idea["title"],
        "role": idea["role"],
        "seal": idea["seal"],
        "discipline": idea["discipline"],
        "summary": idea["summary"],
        "teaser": idea["teaser"],
        "paid_content": idea["paid_content"],
        "deliverables": idea["deliverables"],
        "tags": idea["tags"],
        "accent": idea["accent"],
        "sort_order": idea["sort_order"],
        "price_override": idea["price_override"],
    }


def test_admin_can_update_idea_content_and_price_override(app, client):
    csrf = login_admin(client)
    dashboard = client.get("/admin/api/dashboard").get_json()
    idea = dashboard["ideas"][0]
    payload = _editable_idea_payload(idea)
    payload.update({"title": "一頁破局進階試煉", "price_override": 299, "accent": "violet"})

    response = client.post(
        f"/admin/api/ideas/{idea['id']}",
        json=payload,
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    connection = sqlite3.connect(app.config["DATABASE"])
    row = connection.execute(
        "SELECT title, price_override, accent FROM ideas WHERE id = ?", (idea["id"],)
    ).fetchone()
    audit = connection.execute(
        "SELECT action, target FROM audit_logs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    connection.close()
    assert row == ("一頁破局進階試煉", 299, "violet")
    assert audit == ("update_idea_content", str(idea["id"]))


def test_admin_idea_update_requires_csrf_and_valid_accent(client):
    csrf = login_admin(client)
    idea = client.get("/admin/api/dashboard").get_json()["ideas"][0]
    payload = _editable_idea_payload(idea)

    no_csrf = client.post(f"/admin/api/ideas/{idea['id']}", json=payload)
    payload["accent"] = "javascript"
    invalid_accent = client.post(
        f"/admin/api/ideas/{idea['id']}", json=payload, headers={"X-CSRF-Token": csrf}
    )

    assert no_csrf.status_code == 403
    assert invalid_accent.status_code == 400
    assert invalid_accent.get_json()["error"] == "accent 不在允許清單"
