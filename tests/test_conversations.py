from datetime import datetime, timedelta, timezone

from conftest import login_admin, set_public_csrf
from tianwai.conversations import _visitor_rate_limited
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


def _conversation_url(visibility="public", slug="mvp-sword-cut"):
    return (
        "/api/conversations/idea-detail"
        f"?visibility={visibility}&idea_slug={slug}"
    )


def _post_message(client, csrf, slug="mvp-sword-cut", **overrides):
    payload = {
        "visibility": "public",
        "body": "這一卷的方法很清楚，我想知道下一步。",
        "idea_slug": slug,
    }
    payload.update(overrides)
    return client.post(
        "/api/conversations/idea-detail/messages",
        json=payload,
        headers={"X-CSRF-Token": csrf},
    )


def _enable_visitor_comments(monkeypatch):
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "test-public-site-key")
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "test-private-secret-key")
    monkeypatch.setattr(
        "tianwai.conversations.verify_turnstile",
        lambda token, ip, expected_action: bool(
            token == "valid-visitor-token" and expected_action == "public-conversation"
        ),
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
            "visitor_token_hash",
            "source_hash",
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


def test_public_read_is_anonymous_and_private_read_still_requires_login(client):
    public = client.get(_conversation_url())
    assert public.status_code == 200
    assert public.get_json()["messages"] == []
    assert public.get_json()["viewer"]["authenticated"] is False

    private = client.get(_conversation_url("private"))
    rejected = _post_message(client, set_public_csrf(client))

    assert private.status_code == 401
    assert rejected.status_code == 503


def test_visitor_public_message_requires_turnstile_and_only_owner_sees_pending(
    app, client, monkeypatch
):
    _enable_visitor_comments(monkeypatch)
    csrf = set_public_csrf(client, "visitor-public-csrf")

    missing_challenge = _post_message(client, csrf)
    private = _post_message(
        client,
        csrf,
        visibility="private",
        turnstile_token="valid-visitor-token",
    )
    created = _post_message(
        client,
        csrf,
        turnstile_token="valid-visitor-token",
    )

    assert missing_challenge.status_code == 403
    assert private.status_code == 401
    assert created.status_code == 201
    message = created.get_json()["message"]
    assert message["status"] == "pending"
    assert message["mine"] is True
    assert message["author"]["alias"].startswith("訪客・")
    assert message["badges"] == ["訪客", "等待公開"]
    assert "visitor_token_hash" not in str(created.get_json())
    assert "source_hash" not in str(created.get_json())

    cookie = created.headers.get("Set-Cookie", "")
    assert "twyb_visitor=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    own = client.get(_conversation_url()).get_json()
    assert [item["id"] for item in own["messages"]] == [message["id"]]
    assert own["viewer"]["alias"] == message["author"]["alias"]

    other = app.test_client()
    assert other.get(_conversation_url()).get_json()["messages"] == []


def test_visitor_validation_honeypot_and_strict_rate_limit(app, client, monkeypatch):
    _enable_visitor_comments(monkeypatch)
    csrf = set_public_csrf(client, "visitor-validation-csrf")

    invalid_challenge = _post_message(client, csrf, turnstile_token="invalid")
    markup = _post_message(
        client,
        csrf,
        body="<b>不應接受</b>",
        turnstile_token="valid-visitor-token",
    )
    public_link = _post_message(
        client,
        csrf,
        body="請看 malicious.example",
        turnstile_token="valid-visitor-token",
    )
    too_long = _post_message(
        client,
        csrf,
        body="字" * 501,
        turnstile_token="valid-visitor-token",
    )
    honeypot = _post_message(
        client,
        csrf,
        website="spam.example",
        turnstile_token="valid-visitor-token",
    )

    assert invalid_challenge.status_code == 403
    assert markup.status_code == 400
    assert public_link.status_code == 400
    assert too_long.status_code == 400
    assert honeypot.status_code == 400

    for index in range(3):
        response = _post_message(
            client,
            csrf,
            body=f"匿名合法測試留言第 {index + 1} 則",
            turnstile_token="valid-visitor-token",
        )
        assert response.status_code == 201
    limited = _post_message(
        client,
        csrf,
        body="匿名第四則應被限制",
        turnstile_token="valid-visitor-token",
    )
    assert limited.status_code == 429

    other = app.test_client()
    source_limited = _post_message(
        other,
        set_public_csrf(other, "visitor-source-limit-csrf"),
        body="清除訪客 Cookie 仍不應繞過來源限速",
        turnstile_token="valid-visitor-token",
    )
    assert source_limited.status_code == 429

    with app.app_context():
        rows = get_db().execute(
            "SELECT visitor_token_hash, source_hash FROM section_messages WHERE author_type = 'visitor'"
        ).fetchall()
        assert len(rows) == 3
        assert all(len(row["visitor_token_hash"]) == 64 for row in rows)
        assert all(len(row["source_hash"]) == 64 for row in rows)


def test_visitor_daily_limit_applies_outside_the_short_window(app):
    visitor_hash = "a" * 64
    source_hash = "b" * 64
    created_at = _iso(datetime.now(timezone.utc) - timedelta(hours=1))
    with app.app_context():
        connection = get_db()
        idea = connection.execute(
            "SELECT id FROM ideas WHERE slug = 'mvp-sword-cut'"
        ).fetchone()
        for index in range(10):
            connection.execute(
                """
                INSERT INTO section_messages
                    (public_id, section_key, idea_id, author_type,
                     visitor_token_hash, source_hash, visibility, status,
                     body, created_at, updated_at)
                VALUES (?, 'idea-detail', ?, 'visitor', ?, ?, 'public',
                        'pending', ?, ?, ?)
                """,
                (
                    f"MSG-DAILY-{index}",
                    idea["id"],
                    visitor_hash,
                    source_hash,
                    f"每日限制測試 {index}",
                    created_at,
                    created_at,
                ),
            )
        connection.commit()
        assert _visitor_rate_limited(visitor_hash, source_hash) is True


def test_public_customer_message_waits_for_moderation_and_does_not_expose_identity(app, client):
    _login_customer(app, client)
    csrf = set_public_csrf(client, "conversation-public-csrf")

    created = _post_message(client, csrf)
    assert created.status_code == 201
    assert created.get_json()["message"]["status"] == "pending"
    assert created.get_json()["message"]["badges"] == ["等待公開"]

    own_view = client.get(_conversation_url()).get_json()
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

    anonymous = app.test_client().get(_conversation_url())
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

    own = client.get(_conversation_url("private"))
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
    other_view = other.get(_conversation_url("private"))
    assert other_view.status_code == 200
    assert other_view.get_json()["messages"] == []


def test_alias_and_color_are_stable_but_color_is_not_the_only_identity(app, client):
    _login_customer(app, client)
    first = client.get(_conversation_url()).get_json()[
        "viewer"
    ]
    second = client.get(
        _conversation_url(slug="brand-world-forge")
    ).get_json()["viewer"]

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
    for legacy_section in (
        "home-hero",
        "home-world",
        "home-ideas",
        "home-how",
        "home-creed",
        "home-transmission",
    ):
        assert (
            client.get(f"/api/conversations/{legacy_section}?visibility=public").status_code
            == 404
        )
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
            "section_key": "idea-detail",
            "idea_slug": "mvp-sword-cut",
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
            "section_key": "idea-detail",
            "idea_slug": "mvp-sword-cut",
            "visibility": "private",
            "customer_public_id": "TYB-COMMENT-A001",
            "reply_to_id": private["id"],
            "body": "這則只回覆給你。",
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert public_reply.status_code == 201
    assert private_reply.status_code == 201

    public_view = app.test_client().get(_conversation_url()).get_json()
    assert len(public_view["messages"]) == 2
    assert public_view["messages"][1]["author"]["label"] == "守閣者"
    assert public_view["messages"][1]["target"]["alias"].startswith("同道・")

    private_view = client.get(_conversation_url("private")).get_json()
    assert any(message["body"] == "這則只回覆給你。" for message in private_view["messages"])

    hidden = client.post(
        f"/admin/api/conversations/{pending['id']}/moderate",
        json={"status": "hidden"},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert hidden.status_code == 200
    assert len(
        app.test_client()
        .get(_conversation_url())
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


def test_admin_can_approve_and_publicly_reply_to_visitor(app, client, monkeypatch):
    _enable_visitor_comments(monkeypatch)
    csrf = set_public_csrf(client, "visitor-admin-csrf")
    pending = _post_message(
        client,
        csrf,
        turnstile_token="valid-visitor-token",
    ).get_json()["message"]

    admin_csrf = login_admin(client)
    approved = client.post(
        f"/admin/api/conversations/{pending['id']}/moderate",
        json={"status": "published"},
        headers={"X-CSRF-Token": admin_csrf},
    )
    replied = client.post(
        "/admin/api/conversations/reply",
        json={
            "section_key": "idea-detail",
            "idea_slug": "mvp-sword-cut",
            "visibility": "public",
            "reply_to_id": pending["id"],
            "body": "守閣者已收到這道訪客傳音。",
        },
        headers={"X-CSRF-Token": admin_csrf},
    )

    assert approved.status_code == 200
    assert replied.status_code == 201
    public = app.test_client().get(_conversation_url()).get_json()["messages"]
    assert public[0]["badges"] == ["訪客"]
    assert public[1]["target"]["alias"] == public[0]["author"]["alias"]

    private_reply = client.post(
        "/admin/api/conversations/reply",
        json={
            "section_key": "idea-detail",
            "idea_slug": "mvp-sword-cut",
            "visibility": "private",
            "reply_to_id": pending["id"],
            "body": "訪客不能收到私密回覆。",
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert private_reply.status_code == 400


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


def test_public_pages_render_reusable_accessible_conversation_widgets(client, monkeypatch):
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "test-public-site-key")
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "test-private-secret-key")
    home_response = client.get("/")
    detail_response = client.get("/ideas/mvp-sword-cut")
    home = home_response.get_data(as_text=True)
    detail = detail_response.get_data(as_text=True)

    assert home.count('data-conversation-widget') == 0
    assert home.count('data-idea-activity') == 6
    assert 'data-ideas-activity-summary' in home
    assert 'data-ideas-nav-activity' in home
    assert 'data-section-key="home-hero"' not in home
    assert 'data-section-key="home-transmission"' not in home
    assert home.count("conversations.js") == 1

    assert detail.count('data-conversation-widget') == 1
    assert 'data-section-key="idea-detail"' in detail
    assert 'data-idea-slug="mvp-sword-cut"' in detail
    assert 'id="conversation-idea-detail-mvp-sword-cut"' in detail
    assert 'data-conversation-turnstile' in detail
    assert 'data-sitekey="test-public-site-key"' in detail
    assert 'api.js?render=explicit' in detail
    assert 'data-action="public-conversation"' in detail
    assert "訪客可免登入公開留言" in detail
    assert "https://challenges.cloudflare.com" not in home_response.headers[
        "Content-Security-Policy"
    ]
    assert "https://challenges.cloudflare.com" in detail_response.headers[
        "Content-Security-Policy"
    ]
    assert "frame-src https://challenges.cloudflare.com" in detail_response.headers[
        "Content-Security-Policy"
    ]


def test_idea_activity_exposes_only_safe_public_and_customer_reply_markers(app, client):
    _login_customer(app, client)
    csrf = set_public_csrf(client, "conversation-activity-csrf")
    pending = _post_message(client, csrf).get_json()["message"]
    private = _post_message(
        client,
        csrf,
        visibility="private",
        body="只給守閣者的活動測試。",
    ).get_json()["message"]

    before_approval = client.get("/api/conversations/idea-activity")
    before_item = next(
        item
        for item in before_approval.get_json()["ideas"]
        if item["slug"] == "mvp-sword-cut"
    )
    assert before_item["public_count"] == 0
    assert before_item["latest_public_id"] == 0
    assert before_item["private_reply_count"] == 0
    assert before_item["latest_private_reply_id"] == 0
    assert len(before_approval.get_json()["viewer"]["activity_scope"]) == 20
    assert "TYB-COMMENT-A001" not in str(before_approval.get_json())
    assert before_approval.headers["Cache-Control"].startswith("no-store")

    admin_csrf = login_admin(client)
    assert client.post(
        f"/admin/api/conversations/{pending['id']}/moderate",
        json={"status": "published"},
        headers={"X-CSRF-Token": admin_csrf},
    ).status_code == 200
    reply = client.post(
        "/admin/api/conversations/reply",
        json={
            "section_key": "idea-detail",
            "idea_slug": "mvp-sword-cut",
            "visibility": "private",
            "customer_public_id": "TYB-COMMENT-A001",
            "reply_to_id": private["id"],
            "body": "守閣者的私密活動回覆。",
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert reply.status_code == 201

    activity = client.get("/api/conversations/idea-activity").get_json()
    item = next(
        candidate
        for candidate in activity["ideas"]
        if candidate["slug"] == "mvp-sword-cut"
    )
    assert item["public_count"] == 1
    assert item["latest_public_id"] == pending["id"]
    assert item["private_reply_count"] == 1
    assert item["latest_private_reply_id"] == reply.get_json()["message"]["id"]
    assert "body" not in str(activity)
    assert "customer" not in str(activity)
    assert client.get(_conversation_url()).get_json()["latest_activity_id"] == pending["id"]
    assert (
        client.get(_conversation_url("private")).get_json()["latest_activity_id"]
        == reply.get_json()["message"]["id"]
    )

    anonymous = app.test_client().get("/api/conversations/idea-activity").get_json()
    anonymous_item = next(
        candidate
        for candidate in anonymous["ideas"]
        if candidate["slug"] == "mvp-sword-cut"
    )
    assert "private_reply_count" not in anonymous_item
    assert "latest_private_reply_id" not in anonymous_item
