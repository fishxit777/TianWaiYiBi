import hashlib
import hmac
import json
import os
import secrets

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for

from .db import get_db, utc_now
from .security import derive_access_token, hash_token, log_security_event, require_public_csrf


payments_bp = Blueprint("payments", __name__)


def _payment_secret():
    return os.environ.get("PAYMENT_WEBHOOK_SECRET", "")


def payment_signature_valid(raw_body, supplied):
    secret = _payment_secret()
    if not secret or not supplied:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied)


def process_payment_event(payload, raw_body, provider="mock"):
    event_id = str(payload.get("event_id", ""))[:120]
    order_no = str(payload.get("order_no", ""))[:80]
    payment_ref = str(payload.get("payment_ref", ""))[:160]
    status = str(payload.get("status", "")).lower()
    try:
        amount = int(payload.get("amount"))
    except (TypeError, ValueError):
        return {"error": "付款資料格式錯誤"}, 400

    if not event_id or not order_no or not payment_ref:
        return {"error": "付款資料不完整"}, 400

    connection = get_db()
    duplicate = connection.execute(
        "SELECT result FROM payment_events WHERE event_id = ?", (event_id,)
    ).fetchone()
    if duplicate is not None:
        return {"result": "duplicate"}, 200

    order = connection.execute("SELECT * FROM orders WHERE order_no = ?", (order_no,)).fetchone()
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    if order is None:
        connection.execute(
            """
            INSERT INTO payment_events (event_id, order_id, provider, payload_hash, result, created_at)
            VALUES (?, NULL, ?, ?, ?, ?)
            """,
            (event_id, provider, payload_hash, "order_not_found", utc_now()),
        )
        connection.commit()
        log_security_event("payment_order_not_found", "high", "rejected", f"event={event_id}")
        return {"error": "找不到訂單"}, 404

    if amount != int(order["amount"]):
        connection.execute(
            """
            INSERT INTO payment_events (event_id, order_id, provider, payload_hash, result, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, order["id"], provider, payload_hash, "amount_mismatch", utc_now()),
        )
        connection.commit()
        log_security_event(
            "payment_amount_mismatch", "critical", "rejected", f"order={order_no}"
        )
        return {"error": "付款金額不符"}, 400

    if status != "paid":
        connection.execute(
            """
            INSERT INTO payment_events (event_id, order_id, provider, payload_hash, result, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, order["id"], provider, payload_hash, "ignored_status", utc_now()),
        )
        connection.commit()
        return {"result": "ignored"}, 200

    try:
        connection.execute("BEGIN IMMEDIATE")
        duplicate = connection.execute(
            "SELECT result FROM payment_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if duplicate is not None:
            connection.rollback()
            return {"result": "duplicate"}, 200
        fresh_order = connection.execute(
            "SELECT status FROM orders WHERE id = ?", (order["id"],)
        ).fetchone()
        result = "paid"
        if fresh_order["status"] == "paid":
            result = "already_paid"
        else:
            connection.execute(
                """
                UPDATE orders
                SET status = 'paid', payment_provider = ?, payment_ref = ?, paid_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (provider, payment_ref, utc_now(), order["id"]),
            )
            connection.execute(
                """
                INSERT INTO analytics_events (event_name, idea_id, source, session_id, created_at)
                VALUES ('purchase_completed', ?, ?, NULL, ?)
                """,
                (order["idea_id"], provider, utc_now()),
            )
        connection.execute(
            """
            INSERT INTO payment_events (event_id, order_id, provider, payload_hash, result, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, order["id"], provider, payload_hash, result, utc_now()),
        )
        connection.commit()
        return {"result": result}, 200
    except Exception:
        connection.rollback()
        current_app.logger.exception("Payment transaction failed")
        return {"error": "付款處理暫時失敗"}, 500


@payments_bp.get("/pay/mock/<payment_token>")
def mock_payment_page(payment_token):
    order = get_db().execute(
        """
        SELECT orders.*, ideas.title, ideas.role
        FROM orders JOIN ideas ON ideas.id = orders.idea_id
        WHERE orders.payment_token_hash = ?
        """,
        (hash_token(payment_token),),
    ).fetchone()
    if order is None:
        return render_template("message.html", title="付款連結無效", message="此付款連結不存在或已失效。"), 404
    if order["status"] == "paid":
        return redirect(url_for("public.order_access", access_token=derive_access_token(payment_token)))
    return render_template("mock_payment.html", order=order, payment_token=payment_token)


@payments_bp.post("/pay/mock/complete")
def mock_payment_complete():
    csrf_error = require_public_csrf()
    if csrf_error:
        return csrf_error
    if not current_app.config.get("TESTING") and not os.environ.get("ENABLE_DEV_TOOLS", "").lower() in {
        "1", "true", "yes", "on"
    }:
        return jsonify({"error": "本機模擬付款未啟用"}), 404
    payment_token = request.form.get("payment_token", "")
    order = get_db().execute(
        "SELECT * FROM orders WHERE payment_token_hash = ?", (hash_token(payment_token),)
    ).fetchone()
    if order is None:
        return render_template("message.html", title="付款連結無效", message="請返回重新建立訂單。"), 404
    if order["status"] == "paid":
        return redirect(url_for("public.order_access", access_token=derive_access_token(payment_token)))

    payload = {
        "event_id": "mock_evt_" + secrets.token_hex(12),
        "order_no": order["order_no"],
        "amount": int(order["amount"]),
        "status": "paid",
        "payment_ref": "mock_pay_" + secrets.token_hex(10),
    }
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    result, status_code = process_payment_event(payload, raw_body, provider="mock")
    if status_code != 200:
        return render_template("message.html", title="付款失敗", message=result.get("error", "請稍後再試。")), status_code
    return redirect(url_for("public.order_access", access_token=derive_access_token(payment_token)))


@payments_bp.post("/payments/webhook/mock")
def mock_payment_webhook():
    raw_body = request.get_data(cache=True)
    supplied = request.headers.get("X-Payment-Signature", "")
    if not payment_signature_valid(raw_body, supplied):
        log_security_event("payment_signature_mismatch", "critical", "rejected", "invalid_signature")
        return jsonify({"error": "簽章驗證失敗"}), 401
    payload = request.get_json(silent=True) or {}
    result, status_code = process_payment_event(payload, raw_body, provider="mock")
    return jsonify(result), status_code
