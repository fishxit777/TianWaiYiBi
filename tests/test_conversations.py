from datetime import datetime, timedelta, timezone

from conftest import login_admin, set_public_csrf
from tianwai.db import get_db
from tianwai.security import hash_token


def _iso(moment):
    return moment.isoformat(timespec="seconds")


def _login_customer(app, client, public_id="TYB-COMMENT-A001", email="comment-a@example.com"):
    raw_token = f"customer-session-{public_id}"
    now = datetime.now(timezone.utc)
    with app.app_context():
        connection = get_db()
        connection.execute(
            """
            INSERT INTO customers
                (public_id, normalized_email, status, risk_level, created_at, updated_at)
            VALUES (?, ?, 'active', 'low', ?, ?)
            """,
            (public_id, email, _iso(now), _iso(now)),
        )
        customer = connection.execute(
            "SELECT id FROM customers WHERE public_id = ?", (public_id,)
        ).fetchone()
        connection.execute(
            """
            INSERT INTO customer_sessions
                (session_hash, customer_email, created_at, last_seen_at, expires_at,
                 user_agent, customer_id, ip, idle_expires_at)
            VALUES (?, ?, ?, ?, ?, 'pytest', ?, '127.0.0.1', ?)
            """,
            (
                hash_token(raw_token),
                email,
                _iso(now),
                _iso(now),
                _iso(now + timedelta(days=1)),
                customer["id"],
                _iso(now + timedelta(hours=8)),
            ),
        )
        connection.commit()
    client.set_cookie("twyb_customer", raw_token)
    return customer["id"]


def _post_message(client, csrf, **overrides):
    payload = {
        "visibility": "public",
        "body": "這一卷的方法很清楚，我想知道下一步。",
    }
    payload.update(overrides)
    return client.post(
        "/api/conversations/home-world/messages",
        json=payload,
        headers={"X-CSRF-Token": csrf},
    )


def test_conversation_schema_exists_in_both_database_dialects(app):
    with app.app_context():
        columns = get_db().execute("PRAGMA table_info(section_messages)").fetchall()
        assert {row["name"] for row in columns} >= {
            "public_id",
            "section_key",
            "idea_id",
            "author_type",
            "customer_id",
            "reply_to_id",
            "visibility",
            "status",
            "body",
            "created_at",
        }

    from pathlib import Path

    postgres_schema = (
        Path(__file__).resolve().parents[1] / "tianwai" / "schema_postgres.sql"
    ).read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS section_messages" in postgres_schema


def test_public_read_is_anonymous_but_writing_and_private_read_require_login(client):
    public = client.get("/api/conversations/home-world?visibility=public")
    assert public.status_code == 200
    assert public.get_json()["messages"] == []
    assert public.get_json()["viewer"]["authenticated"] is False

    private = client.get("/api/conversations/home-world?visibility=private")
    rejected = _post_message(client, set_public_csrf(client))

    assert private.status_code == 401
    assert rejected.status_code == 401


def test_public_customer_message_waits_for_moderation_and_does_not_expose_identity(app, client):
    _login_customer(app, client)
    csrf = set_public_csrf(client, "conversation-public-csrf")

    created = _post_message(client, csrf)
    assert created.status_code == 201
    assert created.get_json()["message"]["status"] == "pending"
    assert created.get_json()["message"]["badges"] == ["等待公開"]

    own_view = client.get("/api/conversations/home-world?visibility=public").get_json()
    assert len(own_view["messages"]) == 1
    assert own_view["messages"][0]["mine"] is True
    assert "comment-a@example.com" not in str(own_view)
    assert "TYB-COMMENT-A001" not in str(own_view)

    with app.app_context():
        notifications = get_db().execute(
            "SELECT payload_json FROM notification_queue ORDER BY id"
        ).fetchall()
        serialized_notifications = " ".join(row["payload_json"] for row in notifications)
        assert "這一卷的方法很清楚" not in serialized_notifications
        assert "comment-a@example.com" not in serialized_notifications

    anonymous = app.test_client().get(
        "/api/conversations/home-world?visibility=public"
    )
    assert anonymous.status_code == 200
    assert anonymous.get_json()["messages"] == []


def test_private_messages_are_isolated_by_customer(app, client):
    _login_customer(app, client)
    csrf = set_public_csrf(client, "conversation-private-a")
    created = _post_message(
        client,
        csrf,
        visibility="private",
        body="這是只給守閣者看的內容。",
    )
    assert created.status_code == 201

    own = client.get("/api/conversations/home-world?visibility=private")
    assert [message["body"] for message in own.get_json()["messages"]] == [
        "這是只給守閣者看的內容。"
    ]
    assert own.headers["Cache-Control"].startswith("no-store")

    other = app.test_client()
    _login_customer(
        app,
        other,
        public_id="TYB-COMMENT-B002",
        email="comment-b@example.com",
    )
    other_view = other.get("/api/conversations/home-world?visibility=private")
    assert other_view.status_code == 200
    assert other_view.get_json()["messages"] == []


def test_alias_and_color_are_stable_but_color_is_not_the_only_identity(app, client):
    _login_customer(app, client)
    first = client.get("/api/conversations/home-world?visibility=public").get_json()[
        "viewer"
    ]
    second = client.get("/api/conversations/home-how?visibility=public").get_json()[
        "viewer"
    ]

    assert first["alias"] == second["alias"]
    assert first["color"] == second["color"]
    assert first["alias"].startswith("同道・")
    assert first["badge"] == "你的識別"
    assert first["color"] in {"jade", "gold", "azure", "violet", "coral", "silver"}


def test_customer_message_validation_rejects_markup_links_and_rate_limit(app, client):
    _login_customer(app, client)
    csrf = set_public_csrf(client, "conversation-validation-csrf")

    markup = _post_message(client, csrf, body="<script>alert(1)</script>")
    public_link = _post_message(client, csrf, body="請看 https://malicious.invalid")
    too_long = _post_message(client, csrf, body="字" * 801)

    assert markup.status_code == 400
    assert public_link.status_code == 400
    assert too_long.status_code == 400

    for index in range(5):
        response = _post_message(client, csrf, body=f"合法的測試留言第 {index + 1} 則")
        assert response.status_code == 201
    limited = _post_message(client, csrf, body="第六則應該被短期限制")
    assert limited.status_code == 429


def test_invalid_section_and_unpublished_idea_context_are_rejected(app, client):
    assert client.get("/api/conversations/not-a-section?visibility=public").status_code == 404
    assert (
        client.get(
            "/api/conversations/idea-detail?visibility=public&idea_slug=missing"
        ).status_code
        == 404
    )

    with app.app_context():
        get_db().execute("UPDATE ideas SET published = 0 WHERE slug = 'mvp-sword-cut'")
        get_db().commit()
    hidden = client.get(
        "/api/conversations/idea-detail?visibility=public&idea_slug=mvp-sword-cut"
    )
    assert hidden.status_code == 404


def test_admin_can_approve_hide_and_reply_without_public_customer_data(app, client):
    _login_customer(app, client)
    public_csrf = set_public_csrf(client, "conversation-admin-fixture")
    pending = _post_message(client, public_csrf).get_json()["message"]
    private = _post_message(
        client,
        public_csrf,
        visibility="private",
        body="私密問題只應由守閣者看見。",
    ).get_json()["message"]

    admin_csrf = login_admin(client)
    dashboard = client.get("/admin/api/dashboard")
    dashboard_text = dashboard.get_data(as_text=True)
    data = dashboard.get_json()

    assert data["conversation_summary"]["pending"] == 1
    assert len(data["conversation_messages"]) == 2
    assert "comment-a@example.com" not in dashboard_text
    assert "TYB-COMMENT-A001" in dashboard_text

    approved = client.post(
        f"/admin/api/conversations/{pending['id']}/moderate",
        json={"status": "published"},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert approved.status_code == 200

    public_reply = client.post(
        "/admin/api/conversations/reply",
        json={
            "section_key": "home-world",
            "visibility": "public",
            "customer_public_id": "TYB-COMMENT-A001",
            "reply_to_id": pending["id"],
            "body": "守閣者已收到，建議先從限制最大的步驟開始。",
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    private_reply = client.post(
        "/admin/api/conversations/reply",
        json={
            "section_key": "home-world",
            "visibility": "private",
            "customer_public_id": "TYB-COMMENT-A001",
            "reply_to_id": private["id"],
            "body": "這則只回覆給你。",
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert public_reply.status_code == 201
    assert private_reply.status_code == 201

    public_view = app.test_client().get(
        "/api/conversations/home-world?visibility=public"
    ).get_json()
    assert len(public_view["messages"]) == 2
    assert public_view["messages"][1]["author"]["label"] == "守閣者"
    assert public_view["messages"][1]["target"]["alias"].startswith("同道・")

    private_view = client.get(
        "/api/conversations/home-world?visibility=private"
    ).get_json()
    assert any(message["body"] == "這則只回覆給你。" for message in private_view["messages"])

    hidden = client.post(
        f"/admin/api/conversations/{pending['id']}/moderate",
        json={"status": "hidden"},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert hidden.status_code == 200
    assert len(
        app.test_client()
        .get("/api/conversations/home-world?visibility=public")
        .get_json()["messages"]
    ) == 1

    with app.app_context():
        actions = {
            row["action"]
            for row in get_db().execute(
                "SELECT action FROM audit_logs WHERE action LIKE 'conversation_%'"
            ).fetchall()
        }
        assert {"conversation_moderated", "conversation_replied"} <= actions


def test_admin_conversation_mutations_require_admin_csrf(app, client):
    _login_customer(app, client)
    public_csrf = set_public_csrf(client, "conversation-admin-csrf-check")
    message = _post_message(client, public_csrf).get_json()["message"]
    login_admin(client)

    rejected = client.post(
        f"/admin/api/conversations/{message['id']}/moderate",
        json={"status": "published"},
    )
    assert rejected.status_code == 403


def test_public_pages_render_reusable_accessible_conversation_widgets(client):
    home = client.get("/").get_data(as_text=True)
    detail = client.get("/ideas/mvp-sword-cut").get_data(as_text=True)

    assert home.count('data-conversation-widget') == 6
    assert 'data-section-key="home-hero"' in home
    assert 'data-section-key="home-transmission"' in home
    assert "公開傳音" in home
    assert "私密傳音" in home
    assert "顏色僅供輔助辨識" in home
    assert home.count("conversations.js") == 1

    assert detail.count('data-conversation-widget') == 1
    assert 'data-section-key="idea-detail"' in detail
    assert 'data-idea-slug="mvp-sword-cut"' in detail
