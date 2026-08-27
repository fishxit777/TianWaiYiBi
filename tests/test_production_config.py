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


def test_ecpay_production_mode_requires_explicit_live_confirmation(client, monkeypatch):
    monkeypatch.setenv("PAYMENT_PROVIDER", "ecpay")
    monkeypatch.setenv("ECPAY_MODE", "production")
    monkeypatch.setenv("ECPAY_MERCHANT_ID", "merchant")
    monkeypatch.setenv("ECPAY_HASH_KEY", "hash-key")
    monkeypatch.setenv("ECPAY_HASH_IV", "hash-iv")
    monkeypatch.delenv("ECPAY_LIVE_CONFIRMED", raising=False)

    response = client.get("/checkout/brand-world-forge")

    assert response.status_code == 200
    assert "正式付款尚未開放" in response.get_data(as_text=True)


def test_ecpay_complete_production_config_reports_intentional_public_closure(app, monkeypatch):
    from tianwai.payments import payment_checkout_status

    monkeypatch.setenv("PAYMENT_PROVIDER", "ecpay")
    monkeypatch.setenv("ECPAY_MODE", "production")
    monkeypatch.setenv("ECPAY_MERCHANT_ID", "merchant")
    monkeypatch.setenv("ECPAY_HASH_KEY", "hash-key")
    monkeypatch.setenv("ECPAY_HASH_IV", "hash-iv")
    monkeypatch.delenv("ECPAY_LIVE_CONFIRMED", raising=False)

    with app.app_context():
        status = payment_checkout_status()

    assert status["provider"] == "unavailable"
    assert status["ready"] is False
    assert status["configuration_ready"] is True
    assert status["state"] == "closed"
    assert status["public_sales_open"] is False
    assert "公開收款關閉" in status["label"]


def _csrf_token(client, base_url):
    response = client.get("/dev/line", base_url=base_url)
    match = re.search(rb'<meta name="csrf-token" content="([^"]+)"', response.data)
    assert match
    return match.group(1).decode("utf-8")
