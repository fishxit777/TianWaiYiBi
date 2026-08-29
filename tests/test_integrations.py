import base64
import hashlib
import hmac
import json

from conftest import set_public_csrf
from test_public_flow import create_order
from tianwai.db import get_db
from tianwai.payments import ecpay_check_mac_value


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
    assert len(client.application.extensions["mail_outbox"]) == 1


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


def test_ecpay_checksum_matches_official_aio_example():
    parameters = {
        "TradeDesc": "促銷方案",
        "PaymentType": "aio",
        "MerchantTradeDate": "2023/03/12 15:30:23",
        "MerchantTradeNo": "ecpay20230312153023",
        "MerchantID": "3002607",
        "ReturnURL": "https://www.ecpay.com.tw/receive.php",
        "ItemName": "Apple iphone 15",
        "TotalAmount": "30000",
        "ChoosePayment": "ALL",
        "EncryptType": "1",
    }

    result = ecpay_check_mac_value(
        parameters,
        "pwFHCqoQZGmho4w6",
        "EkRm7iFT261dpevs",
    )

    assert result == "6C51C9E6888DE861FD62FB1DD17029FC742634498FD813DC43D4243B5685B840"


def test_ecpay_server_callback_unlocks_only_after_valid_signed_paid_notice(client, monkeypatch):
    monkeypatch.setenv("PAYMENT_PROVIDER", "ecpay")
    monkeypatch.setenv("ECPAY_MODE", "stage")
    monkeypatch.setenv("ECPAY_MERCHANT_ID", "3002607")
    monkeypatch.setenv("ECPAY_HASH_KEY", "pwFHCqoQZGmho4w6")
    monkeypatch.setenv("ECPAY_HASH_IV", "EkRm7iFT261dpevs")
    order = create_order(client)
    assert order["payment_provider"] == "ecpay"
    assert order["checkout_url"].startswith("/pay/ecpay/")
    redirect_page = client.get(order["checkout_url"])
    assert redirect_page.status_code == 200
    assert b'name="StoreID" value="TWYB"' in redirect_page.data

    parameters = {
        "MerchantID": "3002607",
        "MerchantTradeNo": order["order_no"],
        "StoreID": "TWYB",
        "RtnCode": "1",
        "RtnMsg": "交易成功",
        "TradeNo": "2608231234567890",
        "TradeAmt": "199",
        "PaymentDate": "2026/08/23 12:34:56",
        "PaymentType": "Credit_CreditCard",
        "PaymentTypeChargeFee": "5",
        "TradeDate": "2026/08/23 12:33:00",
        "SimulatePaid": "0",
    }
    parameters["CheckMacValue"] = ecpay_check_mac_value(
        parameters,
        "pwFHCqoQZGmho4w6",
        "EkRm7iFT261dpevs",
    )
    response = client.post("/payments/ecpay/notify", data=parameters)

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "1|OK"
    assert len(client.application.extensions["mail_outbox"]) == 1


def test_ecpay_rejects_callback_from_another_store(client, monkeypatch, app):
    monkeypatch.setenv("PAYMENT_PROVIDER", "ecpay")
    monkeypatch.setenv("ECPAY_MODE", "stage")
    monkeypatch.setenv("ECPAY_MERCHANT_ID", "3002607")
    monkeypatch.setenv("ECPAY_HASH_KEY", "pwFHCqoQZGmho4w6")
    monkeypatch.setenv("ECPAY_HASH_IV", "EkRm7iFT261dpevs")
    order = create_order(client)
    parameters = {
        "MerchantID": "3002607",
        "MerchantTradeNo": order["order_no"],
        "StoreID": "NESTFM",
        "RtnCode": "1",
        "TradeNo": "2608235555555555",
        "TradeAmt": "199",
        "SimulatePaid": "0",
    }
    parameters["CheckMacValue"] = ecpay_check_mac_value(
        parameters,
        "pwFHCqoQZGmho4w6",
        "EkRm7iFT261dpevs",
    )

    response = client.post("/payments/ecpay/notify", data=parameters)

    assert response.status_code == 400
    with app.app_context():
        row = get_db().execute(
            "SELECT status FROM orders WHERE order_no = ?", (order["order_no"],)
        ).fetchone()
        assert row["status"] == "pending"


def test_ecpay_rejects_bad_check_mac_without_granting_access(client, monkeypatch, app):
    monkeypatch.setenv("PAYMENT_PROVIDER", "ecpay")
    monkeypatch.setenv("ECPAY_MODE", "stage")
    monkeypatch.setenv("ECPAY_MERCHANT_ID", "3002607")
    monkeypatch.setenv("ECPAY_HASH_KEY", "pwFHCqoQZGmho4w6")
    monkeypatch.setenv("ECPAY_HASH_IV", "EkRm7iFT261dpevs")
    order = create_order(client)
    response = client.post(
        "/payments/ecpay/notify",
        data={
            "MerchantID": "3002607",
            "MerchantTradeNo": order["order_no"],
            "RtnCode": "1",
            "TradeNo": "2608239999999999",
            "TradeAmt": "199",
            "SimulatePaid": "0",
            "CheckMacValue": "BAD",
        },
    )

    assert response.status_code == 400
    with app.app_context():
        row = get_db().execute(
            "SELECT status FROM orders WHERE order_no = ?", (order["order_no"],)
        ).fetchone()
        assert row["status"] == "pending"


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
    assert "天外盲策封印目錄" in response.get_json()["reply"]
    assert "雙生續行輪" not in response.get_json()["reply"]


def test_line_simulator_catalog_uses_only_published_sealed_cards(client):
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
    assert len(payload["messages"][1]["contents"]["contents"]) == 1
    assert len(payload["cards"]) == 1
    assert payload["cards"][0]["title"] == "封印盲策・第壹卷"
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
