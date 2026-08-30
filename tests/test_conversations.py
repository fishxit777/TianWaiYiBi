from conftest import login_admin


def test_public_conversation_endpoints_are_retired(client):
    assert client.get("/api/conversations/idea-activity").status_code == 404
    assert client.get("/api/conversations/idea-detail").status_code == 404
    assert client.post("/api/conversations/idea-detail/messages", json={}).status_code == 404


def test_admin_conversation_endpoints_are_retired(client):
    login_admin(client)
    assert client.post("/admin/api/conversations/reply", json={}).status_code == 404
    assert client.post("/admin/api/conversations/1/moderate", json={}).status_code == 404


def test_public_and_admin_pages_expose_no_conversation_interface(client):
    home = client.get("/").get_data(as_text=True)
    detail = client.get("/ideas/sealed-twin-tire-safety").get_data(as_text=True)
    login_admin(client)
    admin = client.get("/admin").get_data(as_text=True)

    for body in (home, detail, admin):
        assert "conversations.js" not in body
        assert "data-conversation-widget" not in body
        assert "conversation-reply-form" not in body


def test_retired_customer_message_tables_are_not_created_for_new_databases(app):
    from tianwai.db import get_db

    with app.app_context():
        connection = get_db()
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert "section_messages" not in tables
    assert "line_events" not in tables
