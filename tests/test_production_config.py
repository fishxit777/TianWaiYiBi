import re
from pathlib import Path

from tianwai import create_app


def test_database_path_can_be_configured_from_environment(monkeypatch, tmp_path):
    database_path = tmp_path / "runtime" / "production.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("APP_SECRET_KEY", "a" * 32)

    application = create_app({"TESTING": True})

    assert Path(application.config["DATABASE"]) == database_path.resolve()
    assert database_path.exists()


def test_line_links_fall_back_to_request_origin(client, monkeypatch):
    monkeypatch.delenv("BASE_URL", raising=False)
    origin = "https://tianwai.example"

    response = client.post(
        "/dev/line/reply",
        json={"message": "靈感"},
        headers={"X-CSRF-Token": _csrf_token(client, origin)},
        base_url=origin,
    )

    assert response.status_code == 200
    assert all(card["url"].startswith("https://tianwai.example/") for card in response.get_json()["cards"])


def _csrf_token(client, base_url):
    response = client.get("/dev/line", base_url=base_url)
    match = re.search(rb'<meta name="csrf-token" content="([^"]+)"', response.data)
    assert match
    return match.group(1).decode("utf-8")
