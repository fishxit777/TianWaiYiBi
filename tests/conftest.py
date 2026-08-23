import os
import re
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "keeper")
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("ADMIN_PASSWORD", "correct-horse-battery-staple")
    monkeypatch.setenv("PAYMENT_WEBHOOK_SECRET", "test-payment-secret")
    monkeypatch.setenv("LINE_CHANNEL_SECRET", "test-line-secret")
    monkeypatch.setenv("APP_SECRET_KEY", "test-app-secret")
    monkeypatch.setenv("ENABLE_DEV_TOOLS", "true")
    monkeypatch.setenv("BASE_URL", "http://localhost")
    monkeypatch.setenv("ADMIN_ALERT_EMAIL", "admin-alerts@example.com")
    monkeypatch.setenv("LINE_ADMIN_USER_ID", "UADMIN1234567890")
    monkeypatch.setenv(
        "NOTIFICATION_CRON_SECRET",
        "test-notification-secret-with-at-least-32-characters",
    )

    from tianwai import create_app

    application = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test.db"),
            "SESSION_COOKIE_SECURE": False,
        }
    )
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def set_public_csrf(client, token="public-test-csrf"):
    with client.session_transaction() as session:
        session["csrf_token"] = token
    return token


def login_admin(client):
    token = set_public_csrf(client, "login-test-csrf")
    response = client.post(
        "/admin/login",
        data={
            "username": "keeper",
            "password": "correct-horse-battery-staple",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    dashboard = client.get("/admin")
    assert dashboard.status_code == 200
    match = re.search(rb'<meta name="admin-csrf" content="([^"]+)"', dashboard.data)
    assert match
    return match.group(1).decode("utf-8")
