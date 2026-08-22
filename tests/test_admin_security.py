import sqlite3

from conftest import login_admin, set_public_csrf


def test_admin_login_failure_is_generic(client):
    csrf = set_public_csrf(client)
    response = client.post(
        "/admin/login",
        data={"username": "unknown", "password": "wrong", "csrf_token": csrf},
    )

    assert response.status_code == 403
    assert "帳號或密碼錯誤" in response.get_data(as_text=True)
    assert "unknown" not in response.get_data(as_text=True)


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
