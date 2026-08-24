import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for

from .access import issue_activation_delivery
from .db import get_db, utc_now
from .mailer import email_delivery_ready
from .security import derive_activation_token, hash_token, log_security_event, require_public_csrf


payments_bp = Blueprint("payments", __name__)
ECPAY_STAGE_URL = "https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5"
ECPAY_PRODUCTION_URL = "https://payment.ecpay.com.tw/Cashier/AioCheckOut/V5"
TAIPEI_TIMEZONE = timezone(timedelta(hours=8))
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _enabled(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _ecpay_config():
    mode = os.environ.get("ECPAY_MODE", "stage").strip().lower()
    if mode not in {"stage", "production"}:
        mode = "stage"
    raw_store_id = os.environ.get("ECPAY_STORE_ID", "TWYB").strip()
    store_id = raw_store_id if raw_store_id.isalnum() and len(raw_store_id) <= 10 else ""
    return {
        "mode": mode,
        "merchant_id": os.environ.get("ECPAY_MERCHANT_ID", "").strip(),
        "hash_key": os.environ.get("ECPAY_HASH_KEY", "").strip(),
        "hash_iv": os.environ.get("ECPAY_HASH_IV", "").strip(),
        "store_id": store_id,
        "endpoint": ECPAY_PRODUCTION_URL if mode == "production" else ECPAY_STAGE_URL,
    }


def payment_checkout_status(verification=False):
    requested = os.environ.get("PAYMENT_PROVIDER", "mock").strip().lower()
    if requested == "ecpay":
        config = _ecpay_config()
        credentials_ready = all(
            (
                config["merchant_id"],
                config["hash_key"],
                config["hash_iv"],
                config["store_id"],
            )
        )
        base_url = os.environ.get("BASE_URL", "").strip().lower()
        callback_ready = base_url.startswith("https://") or bool(current_app.config.get("TESTING"))
        live_confirmed = config["mode"] != "production" or _enabled("ECPAY_LIVE_CONFIRMED", False)
        verification_email = os.environ.get("PAYMENT_VERIFICATION_EMAIL", "").strip().lower()
        verification_ready = bool(
            config["mode"] == "production"
            and _enabled("ECPAY_VERIFICATION_ENABLED", False)
            and EMAIL_PATTERN.fullmatch(verification_email)
        )
        ready = bool(
            credentials_ready
            and email_delivery_ready()
            and callback_ready
            and (verification_ready if verification else live_confirmed)
        )
        return {
            "provider": "ecpay" if ready else "unavailable",
            "label": (
                "綠界 NT$6 驗證模式"
                if verification and config["mode"] == "production"
                else ("綠界測試金流" if config["mode"] == "stage" else "綠界正式金流")
            ),
            "ready": ready,
            "credentials_ready": credentials_ready,
            "email_ready": email_delivery_ready(),
            "callback_ready": callback_ready,
            "live_confirmed": live_confirmed,
            "verification_enabled": verification_ready,
            "mode": config["mode"],
        }
    development_ready = bool(current_app.config.get("TESTING")) or _enabled("ENABLE_DEV_TOOLS", False)
    return {
        "provider": "mock" if development_ready else "unavailable",
        "label": "本機模擬付款" if development_ready else "正式付款尚未開放",
        "ready": development_ready,
        "credentials_ready": False,
        "email_ready": email_delivery_ready(),
        "mode": "development" if development_ready else "unavailable",
    }


def checkout_url_for(payment_token, verification=False):
    status = payment_checkout_status(verification=verification)
    if not status["ready"]:
        return None
    if status["provider"] == "ecpay":
        return url_for("payments.ecpay_payment_page", payment_token=payment_token)
    return url_for("payments.mock_payment_page", payment_token=payment_token)


def verification_payment_token(order_no):
    """Return a stable high-entropy checkout capability for one admin test order."""
    return derive_activation_token(f"payment-verification:{order_no}")


def ecpay_check_mac_value(parameters, hash_key, hash_iv):
    filtered = {
        str(key): str(value)
        for key, value in parameters.items()
        if str(key).lower() != "checkmacvalue"
    }
    ordered = "&".join(
        f"{key}={filtered[key]}" for key in sorted(filtered, key=lambda item: item.lower())
    )
    source = f"HashKey={hash_key}&{ordered}&HashIV={hash_iv}"
    encoded = quote_plus(source, safe="-_.!*()").lower()
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest().upper()


def _ecpay_callback_valid(parameters):
    config = _ecpay_config()
    supplied = str(parameters.get("CheckMacValue", ""))
    if (
        not supplied
        or str(parameters.get("MerchantID", "")) != config["merchant_id"]
        or str(parameters.get("StoreID", "")) != config["store_id"]
    ):
        return False
    expected = ecpay_check_mac_value(parameters, config["hash_key"], config["hash_iv"])
    return hmac.compare_digest(expected, supplied.upper())


def _ecpay_payload(parameters):
    trade_no = str(parameters.get("TradeNo", ""))[:20]
    order_no = str(parameters.get("MerchantTradeNo", ""))[:20]
    rtn_code = str(parameters.get("RtnCode", ""))
    simulated = str(parameters.get("SimulatePaid", "0")) == "1"
    status = "paid" if rtn_code == "1" and not simulated else "failed"
    return {
        "event_id": f"ecpay:{trade_no or order_no}:{rtn_code}:sim{int(simulated)}"[:120],
        "order_no": order_no,
        "amount": parameters.get("TradeAmt"),
        "status": status,
        "payment_ref": trade_no or order_no,
        "payment_method": str(parameters.get("PaymentType", ""))[:80],
    }


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
    payment_method = str(payload.get("payment_method", ""))[:80]
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

    if order["purpose"] == "verification" and not payment_method.lower().startswith("credit_"):
        connection.execute(
            """
            INSERT INTO payment_events (event_id, order_id, provider, payload_hash, result, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                order["id"],
                provider,
                payload_hash,
                "verification_payment_method_rejected",
                utc_now(),
            ),
        )
        connection.commit()
        log_security_event(
            "payment_method_mismatch", "high", "rejected", f"order={order_no}"
        )
        return {"error": "驗證訂單只接受信用卡一次付清"}, 400

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
        backend = getattr(connection, "backend", "sqlite")
        if backend != "postgresql":
            connection.execute("BEGIN IMMEDIATE")
        fresh_order_query = "SELECT status FROM orders WHERE id = ?"
        if backend == "postgresql":
            fresh_order_query += " FOR UPDATE"
        fresh_order = connection.execute(
            fresh_order_query, (order["id"],)
        ).fetchone()
        duplicate = connection.execute(
            "SELECT result FROM payment_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if duplicate is not None:
            connection.rollback()
            return {"result": "duplicate"}, 200
        result = "paid"
        if fresh_order["status"] == "paid":
            result = "already_paid"
        else:
            connection.execute(
                """
                UPDATE orders
                SET status = 'paid', payment_provider = ?, payment_method = ?,
                    payment_ref = ?, paid_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (provider, payment_method, payment_ref, utc_now(), order["id"]),
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
        response = {"result": result}
        if result == "paid":
            delivery = issue_activation_delivery(order["id"])
            response["delivery"] = delivery.get("status", "failed")
            if delivery.get("development_code"):
                response["development_code"] = delivery["development_code"]
        return response, 200
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
        return redirect(
            url_for(
                "payments.payment_status_page",
                activation_token=derive_activation_token(order["order_no"]),
            )
        )
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
        return redirect(
            url_for(
                "payments.payment_status_page",
                activation_token=derive_activation_token(order["order_no"]),
            )
        )

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
    if result.get("development_code"):
        session["dev_activation_preview"] = {
            "order_id": order["id"],
            "code": result["development_code"],
        }
    return redirect(
        url_for(
            "payments.payment_status_page",
            activation_token=derive_activation_token(order["order_no"]),
        )
    )


@payments_bp.get("/pay/ecpay/<payment_token>")
def ecpay_payment_page(payment_token):
    order = get_db().execute(
        """
        SELECT orders.*, ideas.title FROM orders JOIN ideas ON ideas.id = orders.idea_id
        WHERE orders.payment_token_hash = ?
        """,
        (hash_token(payment_token),),
    ).fetchone()
    if order is None:
        return render_template("message.html", title="付款連結無效", message="請返回重新建立訂單。"), 404
    status = payment_checkout_status(verification=order["purpose"] == "verification")
    if not status["ready"] or status["provider"] != "ecpay":
        return render_template(
            "message.html",
            title="綠界付款尚未啟用",
            message="目前缺少正式商店或寄信設定，尚未建立任何扣款。",
        ), 503
    if order["status"] == "paid":
        return redirect(
            url_for(
                "payments.payment_status_page",
                activation_token=derive_activation_token(order["order_no"]),
            )
        )

    config = _ecpay_config()
    base_url = os.environ.get("BASE_URL", "").strip().rstrip("/") or request.url_root.rstrip("/")
    parameters = {
        "MerchantID": config["merchant_id"],
        "MerchantTradeNo": order["order_no"],
        "MerchantTradeDate": datetime.now(TAIPEI_TIMEZONE).strftime("%Y/%m/%d %H:%M:%S"),
        "PaymentType": "aio",
        "TotalAmount": str(int(order["amount"])),
        "TradeDesc": (
            "Tianwai Yibi payment verification"
            if order["purpose"] == "verification"
            else "Tianwai Yibi digital content"
        ),
        "ItemName": (
            "Tianwai Yibi payment verification"
            if order["purpose"] == "verification"
            else str(order["title"])[:100]
        ),
        "ReturnURL": f"{base_url}/payments/ecpay/notify",
        "ChoosePayment": "Credit" if order["purpose"] == "verification" else "ALL",
        "EncryptType": "1",
        "OrderResultURL": f"{base_url}/payments/ecpay/result",
        "ClientBackURL": f"{base_url}/",
        "NeedExtraPaidInfo": "N",
        "StoreID": config["store_id"],
    }
    if order["purpose"] == "verification":
        parameters["UnionPay"] = "2"
        parameters["BindingCard"] = "0"
    parameters["CheckMacValue"] = ecpay_check_mac_value(
        parameters, config["hash_key"], config["hash_iv"]
    )
    return render_template(
        "ecpay_redirect.html",
        order=order,
        endpoint=config["endpoint"],
        parameters=parameters,
        ecpay_mode=config["mode"],
    )


@payments_bp.post("/payments/ecpay/notify")
def ecpay_payment_notify():
    parameters = request.form.to_dict(flat=True)
    if not _ecpay_callback_valid(parameters):
        log_security_event("ecpay_signature_mismatch", "critical", "rejected", "invalid_check_mac")
        return "0|Error", 400, {"Content-Type": "text/plain; charset=utf-8"}
    if str(parameters.get("SimulatePaid", "0")) == "1":
        log_security_event("ecpay_simulated_paid", "high", "ignored", "not_entitled")
    payload = _ecpay_payload(parameters)
    raw_body = json.dumps(parameters, ensure_ascii=False, sort_keys=True).encode("utf-8")
    result, status_code = process_payment_event(
        payload, raw_body, provider=f"ecpay-{_ecpay_config()['mode']}"
    )
    if status_code >= 500:
        return "0|Error", 500, {"Content-Type": "text/plain; charset=utf-8"}
    return "1|OK", 200, {"Content-Type": "text/plain; charset=utf-8"}


@payments_bp.post("/payments/ecpay/result")
def ecpay_payment_result():
    parameters = request.form.to_dict(flat=True)
    if not _ecpay_callback_valid(parameters):
        log_security_event("ecpay_result_signature_mismatch", "critical", "rejected", "invalid_check_mac")
        return render_template(
            "message.html", title="無法確認付款結果", message="付款結果驗證失敗，請勿重複付款並聯絡客服。"
        ), 400
    payload = _ecpay_payload(parameters)
    raw_body = json.dumps(parameters, ensure_ascii=False, sort_keys=True).encode("utf-8")
    process_payment_event(payload, raw_body, provider=f"ecpay-{_ecpay_config()['mode']}")
    order = get_db().execute(
        "SELECT order_no FROM orders WHERE order_no = ?", (payload["order_no"],)
    ).fetchone()
    if order is None:
        return render_template("message.html", title="找不到訂單", message="請聯絡客服並提供付款紀錄。"), 404
    return redirect(
        url_for(
            "payments.payment_status_page",
            activation_token=derive_activation_token(order["order_no"]),
        )
    )


@payments_bp.get("/payment/status/<activation_token>")
def payment_status_page(activation_token):
    order = get_db().execute(
        """
        SELECT orders.*, ideas.title, ideas.role FROM orders
        JOIN ideas ON ideas.id = orders.idea_id
        WHERE orders.activation_token_hash = ?
        """,
        (hash_token(activation_token),),
    ).fetchone()
    if order is None:
        return render_template("message.html", title="找不到訂單", message="付款狀態連結無效。"), 404
    preview = session.pop("dev_activation_preview", None)
    development_code = ""
    if isinstance(preview, dict) and preview.get("order_id") == order["id"]:
        development_code = str(preview.get("code", ""))
    return render_template(
        "payment_status.html",
        order=order,
        activation_token=activation_token,
        development_code=development_code,
    )


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
