import base64
import hashlib
import hmac
import json

from conftest import set_public_csrf
from test_public_flow import create_order


def payment_signature(raw):
    return hmac.new(b"test-payment-secret", raw, hashlib.sha256).hexdigest()


def line_signature(raw):
    digest = hmac.new(b"test-line-secret", raw, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def test_payment_webhook_is_idempotent(client):
    order = create_order(client)
    payload = {
        "event_id": "evt_001",
        "order_no": order["order_no"],
        "amount": 199,
        "status": "paid",
        "payment_ref": "mock_001",
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    first = client.post(
        "/payments/webhook/mock",
        data=raw,
        content_type="application/json",
        headers={"X-Payment-Signature": payment_signature(raw)},
    )
    second = client.post(
        "/payments/webhook/mock",
        data=raw,
        content_type="application/json",
        headers={"X-Payment-Signature": payment_signature(raw)},
    )

    assert first.status_code == 200
    assert first.get_json()["result"] == "paid"
    assert second.status_code == 200
    assert second.get_json()["result"] == "duplicate"


def test_payment_webhook_rejects_wrong_amount(client):
    order = create_order(client)
    payload = {
        "event_id": "evt_wrong_amount",
        "order_no": order["order_no"],
        "amount": 1,
        "status": "paid",
        "payment_ref": "mock_wrong",
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    response = client.post(
        "/payments/webhook/mock",
        data=raw,
        content_type="application/json",
        headers={"X-Payment-Signature": payment_signature(raw)},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "付款金額不符"


def test_payment_webhook_rejects_invalid_signature(client):
    response = client.post(
        "/payments/webhook/mock",
        data=b"{}",
        content_type="application/json",
        headers={"X-Payment-Signature": "wrong"},
    )

    assert response.status_code == 401


def test_line_webhook_verifies_signature_and_deduplicates(client):
    payload = {
        "events": [
            {
                "type": "message",
                "webhookEventId": "line-event-001",
                "replyToken": "reply-token",
                "source": {"type": "user", "userId": "U123"},
                "message": {"type": "text", "text": "價格"},
            }
        ]
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = {"X-Line-Signature": line_signature(raw)}

    first = client.post("/line/webhook", data=raw, content_type="application/json", headers=headers)
    second = client.post("/line/webhook", data=raw, content_type="application/json", headers=headers)

    assert first.status_code == 200
    assert first.get_json()["processed"] == 1
    assert second.status_code == 200
    assert second.get_json()["processed"] == 0


def test_line_webhook_rejects_invalid_signature(client):
    response = client.post(
        "/line/webhook",
        data=b'{"events":[]}',
        content_type="application/json",
        headers={"X-Line-Signature": "wrong"},
    )

    assert response.status_code == 401


def test_line_simulator_shows_product_navigation(client):
    csrf = set_public_csrf(client)
    response = client.post(
        "/dev/line/reply",
        json={"message": "靈感"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    assert "六脈仙策" in response.get_json()["reply"]


def test_line_simulator_catalog_uses_six_flex_cards(client):
    csrf = set_public_csrf(client)
    response = client.post(
        "/dev/line/reply",
        json={"message": "靈感"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert [message["type"] for message in payload["messages"]] == ["text", "flex"]
    assert payload["messages"][1]["contents"]["type"] == "carousel"
    assert len(payload["messages"][1]["contents"]["contents"]) == 6
    assert len(payload["cards"]) == 6
    assert all(card["url"].endswith("?source=line") for card in payload["cards"])


def test_line_webhook_rejects_invalid_payload_shape(client):
    raw = json.dumps(["not-an-event-envelope"]).encode("utf-8")
    response = client.post(
        "/line/webhook",
        data=raw,
        content_type="application/json",
        headers={"X-Line-Signature": line_signature(raw)},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "LINE 事件格式不正確"
