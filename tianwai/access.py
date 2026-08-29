import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from .db import get_db, utc_now
from .mailer import send_email
from .security import (
    derive_activation_token,
    get_client_ip,
    hash_scoped_token,
    hash_token,
    log_security_event,
    require_public_csrf,
    safe_user_agent,
)


access_bp = Blueprint("access", __name__)
CUSTOMER_COOKIE = "twyb_customer"
DEVICE_COOKIE = "twyb_device"
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
ACTIVATION_CODE_MINUTES = 10
LOGIN_CODE_MINUTES = 10
CUSTOMER_SESSION_DAYS = 7
CUSTOMER_IDLE_HOURS = 24
DEVICE_TRUST_DAYS = 30
MAX_TRUSTED_DEVICES = 2
CODE_ATTEMPT_LIMIT = 5
DELIVERY_LIMIT = 3
DELIVERY_WINDOW_MINUTES = 15


def _now():
    return datetime.now(timezone.utc)


def _iso(moment):
    return moment.isoformat(timespec="seconds")


def _base_url():
    configured = os.environ.get("BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    return request.url_root.rstrip("/")


def _generate_code(length=12):
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def _normalize_code(value):
    return "".join(character for character in str(value).upper() if character.isalnum())


def _format_code(code):
    return "-".join(code[index:index + 4] for index in range(0, len(code), 4))


def _normalize_email(value):
    return str(value or "").strip().lower()[:254]


def _ensure_customer(email):
    connection = get_db()
    normalized = _normalize_email(email)
    customer = connection.execute(
        "SELECT * FROM customers WHERE normalized_email = ?", (normalized,)
    ).fetchone()
    if customer is None:
        connection.execute(
            """
            INSERT OR IGNORE INTO customers
                (public_id, normalized_email, status, risk_level, created_at, updated_at)
            VALUES (?, ?, 'active', 'low', ?, ?)
            """,
            (f"TYB-{secrets.token_hex(6).upper()}", normalized, utc_now(), utc_now()),
        )
        connection.commit()
        customer = connection.execute(
            "SELECT * FROM customers WHERE normalized_email = ?", (normalized,)
        ).fetchone()
        if customer is None:
            raise RuntimeError("Unable to create customer identity")
    return customer


def _device_label(user_agent):
    agent = (user_agent or "").lower()
    if "iphone" in agent:
        return "iPhone"
    if "ipad" in agent:
        return "iPad"
    if "android" in agent and "mobile" in agent:
        return "Android 手機"
    if "android" in agent:
        return "Android 平板"
    if "windows" in agent:
        return "Windows 電腦"
    if "macintosh" in agent or "mac os" in agent:
        return "Mac 電腦"
    return "瀏覽器裝置"


def _order_for_activation_token(activation_token):
    return get_db().execute(
        """
        SELECT orders.*, ideas.title, ideas.public_title, ideas.role, ideas.discipline, ideas.primary_vein,
               ideas.secondary_vein, ideas.maturity, ideas.paid_content,
               ideas.deliverables, ideas.tags, ideas.accent, ideas.hero_image,
               ideas.diagram_image, ideas.scene_image
        FROM orders JOIN ideas ON ideas.id = orders.idea_id
        WHERE orders.activation_token_hash = ?
        """,
        (hash_token(activation_token),),
    ).fetchone()


def _delivery_rate_limited(order_id, kind):
    window_start = _iso(_now() - timedelta(minutes=DELIVERY_WINDOW_MINUTES))
    row = get_db().execute(
        """
        SELECT COUNT(*) AS count FROM email_events
        WHERE order_id = ? AND email_kind = ? AND created_at >= ?
        """,
        (order_id, kind, window_start),
    ).fetchone()
    return int(row["count"] or 0) >= DELIVERY_LIMIT


def issue_activation_delivery(order_id):
    connection = get_db()
    order = connection.execute(
        """
        SELECT orders.*, ideas.public_title AS title FROM orders
        JOIN ideas ON ideas.id = orders.idea_id
        WHERE orders.id = ?
        """,
        (order_id,),
    ).fetchone()
    if order is None or order["status"] != "paid":
        return {"status": "not_paid"}

    customer = _ensure_customer(order["customer_email"])
    connection.execute(
        "UPDATE orders SET customer_id = ? WHERE id = ? AND customer_id IS NULL",
        (customer["id"], order_id),
    )
    connection.commit()

    code = _generate_code()
    now = _now()
    cursor = connection.execute(
        """
        INSERT INTO activation_codes
            (order_id, code_hash, created_at, expires_at, delivery_status)
        VALUES (?, ?, ?, ?, 'pending')
        """,
        (
            order_id,
            hash_scoped_token("activation-code", code),
            _iso(now),
            _iso(now + timedelta(minutes=ACTIVATION_CODE_MINUTES)),
        ),
    )
    activation_code_id = cursor.lastrowid
    connection.commit()

    activation_token = derive_activation_token(order["order_no"])
    activation_url = f"{_base_url()}/activate/{activation_token}"
    formatted_code = _format_code(code)
    text_body = (
        f"{order['customer_name']} 您好：\n\n"
        f"訂單 {order['order_no']} 已確認付款。\n"
        f"購買內容：{order['title']}\n\n"
        f"專屬開通頁：{activation_url}\n"
        f"一次性 12 位開通碼：{formatted_code}\n\n"
        "開通碼有效 10 分鐘，成功使用後會立即失效，請勿轉傳。\n"
        "開通後，您的購買權限會保留；日後重新登入時，系統會另寄一組 10 分鐘有效的登入碼。\n"
        "每個帳號最多保留 2 台可信裝置，且同一時間僅允許 1 台裝置存取已購內容。\n"
        "若非本人購買，請不要使用此開通碼，並聯絡天外一筆客服。\n"
    )
    status = send_email(
        order["customer_email"],
        f"天外一筆｜訂單 {order['order_no']} 開通資料",
        text_body,
        "activation",
        order_id,
    )
    if status in {"sent", "development"}:
        connection.execute(
            """
            UPDATE activation_codes SET revoked_at = ?
            WHERE order_id = ? AND id <> ? AND used_at IS NULL AND revoked_at IS NULL
            """,
            (utc_now(), order_id, activation_code_id),
        )
        connection.execute(
            "UPDATE activation_codes SET delivery_status = ? WHERE id = ?",
            (status, activation_code_id),
        )
    else:
        connection.execute(
            """
            UPDATE activation_codes SET delivery_status = 'failed', revoked_at = ? WHERE id = ?
            """,
            (utc_now(), activation_code_id),
        )
    connection.commit()
    return {
        "status": status,
        "activation_token": activation_token,
        "development_code": formatted_code if status == "development" else "",
    }


def _issue_login_delivery(email):
    connection = get_db()
    order = connection.execute(
        """
        SELECT orders.id, orders.order_no FROM orders
        WHERE customer_email = ? AND status = 'paid'
        ORDER BY paid_at DESC LIMIT 1
        """,
        (email,),
    ).fetchone()
    if order is None:
        return {"status": "not_found"}
    _ensure_customer(email)

    recent_start = _iso(_now() - timedelta(minutes=DELIVERY_WINDOW_MINUTES))
    recent = connection.execute(
        """
        SELECT COUNT(*) AS count FROM customer_login_codes
        WHERE customer_email = ? AND created_at >= ?
        """,
        (email, recent_start),
    ).fetchone()
    if int(recent["count"] or 0) >= DELIVERY_LIMIT:
        return {"status": "rate_limited"}

    code = _generate_code()
    now = _now()
    cursor = connection.execute(
        """
        INSERT INTO customer_login_codes
            (customer_email, code_hash, created_at, expires_at, requested_ip)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            email,
            hash_scoped_token("customer-login-code", code),
            _iso(now),
            _iso(now + timedelta(minutes=LOGIN_CODE_MINUTES)),
            get_client_ip(),
        ),
    )
    login_code_id = cursor.lastrowid
    connection.commit()
    formatted_code = _format_code(code)
    status = send_email(
        email,
        "天外一筆｜10 分鐘登入驗證碼",
        (
            f"您的登入驗證碼是：{formatted_code}\n\n"
            "此驗證碼僅能使用一次，並會在 10 分鐘後自動失效。\n"
            "驗證碼失效不會影響已購買的內容，可回到登入頁重新申請。\n"
            "完成登入後，其他裝置上的舊工作階段會失效；帳號最多保留 2 台可信裝置。\n"
            "若非本人操作，請忽略此信並不要提供驗證碼給任何人。\n"
        ),
        "customer_login",
        order["id"],
    )
    if status in {"sent", "development"}:
        connection.execute(
            """
            UPDATE customer_login_codes SET revoked_at = ?
            WHERE customer_email = ? AND id <> ? AND used_at IS NULL AND revoked_at IS NULL
            """,
            (utc_now(), email, login_code_id),
        )
    else:
        connection.execute(
            "UPDATE customer_login_codes SET revoked_at = ? WHERE id = ?",
            (utc_now(), login_code_id),
        )
    connection.commit()
    return {
        "status": status,
        "development_code": formatted_code if status == "development" else "",
    }


def _create_customer_session(email):
    """Create one active session and register/reuse one of two trusted devices."""
    from .risk import record_access_event

    customer = _ensure_customer(email)
    connection = get_db()
    if getattr(connection, "backend", "sqlite") == "postgresql":
        if not connection.in_transaction:
            connection.execute("BEGIN")
        connection.execute(
            "SELECT id FROM customers WHERE id = ? FOR UPDATE", (customer["id"],)
        )
    else:
        connection.execute("BEGIN IMMEDIATE")
    now = _now()
    now_iso = _iso(now)
    raw_device = request.cookies.get(DEVICE_COOKIE, "")
    device = None
    if raw_device:
        device = connection.execute(
            """
            SELECT * FROM customer_devices
            WHERE customer_id = ? AND device_token_hash = ? AND revoked_at IS NULL
              AND trusted_until > ?
            """,
            (customer["id"], hash_scoped_token("customer-device", raw_device), now_iso),
        ).fetchone()

    new_device_token = ""
    replaced_device_id = None
    if device is None:
        active_devices = connection.execute(
            """
            SELECT * FROM customer_devices
            WHERE customer_id = ? AND revoked_at IS NULL AND trusted_until > ?
            ORDER BY last_seen_at ASC, id ASC
            """,
            (customer["id"], now_iso),
        ).fetchall()
        if len(active_devices) >= MAX_TRUSTED_DEVICES:
            replaced_device_id = active_devices[0]["id"]
            connection.execute(
                """
                UPDATE customer_devices
                SET revoked_at = ?, revoked_reason = 'device_limit_replacement'
                WHERE id = ? AND revoked_at IS NULL
                """,
                (now_iso, replaced_device_id),
            )
            connection.execute(
                """
                UPDATE customer_sessions
                SET revoked_at = ?, revoked_reason = 'device_replaced'
                WHERE device_id = ? AND revoked_at IS NULL
                """,
                (now_iso, replaced_device_id),
            )
        new_device_token = secrets.token_urlsafe(32)
        device_cursor = connection.execute(
            """
            INSERT INTO customer_devices
                (customer_id, public_id, device_token_hash, label, user_agent,
                 first_ip, last_ip, first_seen_at, last_seen_at, trusted_until)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer["id"], f"DEV-{secrets.token_hex(5).upper()}",
                hash_scoped_token("customer-device", new_device_token),
                _device_label(safe_user_agent()), safe_user_agent(), get_client_ip(),
                get_client_ip(), now_iso, now_iso,
                _iso(now + timedelta(days=DEVICE_TRUST_DAYS)),
            ),
        )
        device = connection.execute(
            "SELECT * FROM customer_devices WHERE id = ?", (device_cursor.lastrowid,)
        ).fetchone()
    else:
        connection.execute(
            "UPDATE customer_devices SET last_seen_at = ?, last_ip = ? WHERE id = ?",
            (now_iso, get_client_ip(), device["id"]),
        )

    previous_sessions = connection.execute(
        """
        SELECT id, device_id FROM customer_sessions
        WHERE customer_id = ? AND revoked_at IS NULL AND expires_at > ?
        """,
        (customer["id"], now_iso),
    ).fetchall()
    connection.execute(
        """
        UPDATE customer_sessions
        SET revoked_at = ?, revoked_reason = 'single_session_transfer'
        WHERE customer_id = ? AND revoked_at IS NULL
        """,
        (now_iso, customer["id"]),
    )

    raw_token = secrets.token_urlsafe(32)
    session_cursor = connection.execute(
        """
        INSERT INTO customer_sessions
            (session_hash, customer_email, created_at, last_seen_at, expires_at,
             user_agent, customer_id, device_id, ip, idle_expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hash_token(raw_token), customer["normalized_email"], now_iso, now_iso,
            _iso(now + timedelta(days=CUSTOMER_SESSION_DAYS)), safe_user_agent(),
            customer["id"], device["id"], get_client_ip(),
            _iso(now + timedelta(hours=CUSTOMER_IDLE_HOURS)),
        ),
    )
    session_id = session_cursor.lastrowid
    connection.commit()

    if replaced_device_id:
        record_access_event(
            "trusted_device_replaced", 40, "oldest_device_revoked",
            customer_id=customer["id"], device_id=device["id"],
            metadata={"replaced_device_id": replaced_device_id},
        )
    elif new_device_token:
        record_access_event(
            "trusted_device_registered", 10, "device_trusted",
            customer_id=customer["id"], device_id=device["id"],
        )
    if previous_sessions:
        different_device = any(row["device_id"] != device["id"] for row in previous_sessions)
        record_access_event(
            "single_session_transferred", 30 if different_device else 15,
            "previous_session_revoked", customer_id=customer["id"], device_id=device["id"],
            metadata={"previous_session_count": len(previous_sessions)},
        )
    else:
        record_access_event(
            "customer_session_created", 5, "session_issued",
            customer_id=customer["id"], device_id=device["id"],
        )
    return raw_token, new_device_token, session_id


def _set_customer_cookies(response, raw_token, raw_device=""):
    secure = bool(current_app.config.get("SESSION_COOKIE_SECURE")) or request.is_secure
    response.set_cookie(
        CUSTOMER_COOKIE,
        raw_token,
        max_age=CUSTOMER_SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=secure,
        samesite="Lax",
        path="/",
    )
    if raw_device:
        response.set_cookie(
            DEVICE_COOKIE,
            raw_device,
            max_age=DEVICE_TRUST_DAYS * 24 * 60 * 60,
            httponly=True,
            secure=secure,
            samesite="Lax",
            path="/",
        )
    return response


def current_customer_session():
    raw_token = request.cookies.get(CUSTOMER_COOKIE, "")
    if not raw_token:
        return None
    connection = get_db()
    row = connection.execute(
        """
        SELECT customer_sessions.*, customers.public_id AS customer_public_id,
               customers.status AS customer_status,
               customer_devices.public_id AS device_public_id
        FROM customer_sessions
        JOIN customers ON customers.id = customer_sessions.customer_id
        LEFT JOIN customer_devices ON customer_devices.id = customer_sessions.device_id
        WHERE customer_sessions.session_hash = ?
          AND customer_sessions.revoked_at IS NULL
          AND customer_sessions.expires_at > ?
          AND customer_sessions.idle_expires_at > ?
          AND customers.status = 'active'
        """,
        (hash_token(raw_token), utc_now(), utc_now()),
    ).fetchone()
    if row is None:
        revoked = connection.execute(
            """
            SELECT * FROM customer_sessions
            WHERE session_hash = ? AND revoked_at IS NOT NULL
              AND revoked_reason IN ('single_session_transfer', 'device_replaced')
            LIMIT 1
            """,
            (hash_token(raw_token),),
        ).fetchone()
        if revoked is not None:
            from .risk import record_access_event

            attempts = int(revoked["replay_attempts"] or 0) + 1
            connection.execute(
                "UPDATE customer_sessions SET replay_attempts = ?, last_replay_at = ? WHERE id = ?",
                (attempts, utc_now(), revoked["id"]),
            )
            connection.commit()
            record_access_event(
                "revoked_session_replay", 35 if attempts == 1 else 70,
                "access_rejected", customer_id=revoked["customer_id"],
                device_id=revoked["device_id"],
                metadata={"attempts": attempts, "reason": revoked["revoked_reason"]},
            )
        return None
    connection.execute(
        "UPDATE customer_sessions SET last_seen_at = ?, idle_expires_at = ? WHERE id = ?",
        (utc_now(), _iso(_now() + timedelta(hours=CUSTOMER_IDLE_HOURS)), row["id"]),
    )
    if row["device_id"]:
        connection.execute(
            "UPDATE customer_devices SET last_seen_at = ?, last_ip = ? WHERE id = ?",
            (utc_now(), get_client_ip(), row["device_id"]),
        )
    connection.commit()
    return row


def current_customer_email():
    row = current_customer_session()
    return row["customer_email"] if row else None


def customer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_customer_email() is None:
            return redirect(url_for("access.customer_login_page"))
        return view(*args, **kwargs)

    return wrapped


@access_bp.get("/activate/<activation_token>")
def activate_page(activation_token):
    order = _order_for_activation_token(activation_token)
    if order is None:
        return render_template(
            "message.html",
            title="開通連結無效",
            message="請確認 Email 中的專屬開通連結是否完整。",
        ), 404
    activated = get_db().execute(
        "SELECT 1 FROM activation_codes WHERE order_id = ? AND used_at IS NOT NULL LIMIT 1",
        (order["id"],),
    ).fetchone() is not None
    delivery_row = get_db().execute(
        """
        SELECT delivery_status FROM activation_codes
        WHERE order_id = ? ORDER BY id DESC LIMIT 1
        """,
        (order["id"],),
    ).fetchone()
    delivery_status = delivery_row["delivery_status"] if delivery_row is not None else "pending"
    resent_requested = request.args.get("resent") == "1"
    delivery_error = request.args.get("delivery_error", "")
    if resent_requested and delivery_status not in {"sent", "development"}:
        delivery_error = "failed"
    return render_template(
        "activate.html",
        order=order,
        activation_token=activation_token,
        activated=activated,
        resent=resent_requested and delivery_status in {"sent", "development"},
        delivery_error=delivery_error,
        error="",
    )


@access_bp.post("/activate/<activation_token>")
def activate_order(activation_token):
    csrf_error = require_public_csrf()
    if csrf_error:
        return csrf_error
    order = _order_for_activation_token(activation_token)
    if order is None or order["status"] != "paid":
        return render_template(
            "message.html", title="目前無法開通", message="付款尚未確認，或開通連結無效。"
        ), 400

    from .risk import record_access_event

    code = _normalize_code(request.form.get("activation_code", ""))
    connection = get_db()
    customer = _ensure_customer(order["customer_email"])
    connection.execute(
        "UPDATE orders SET customer_id = ? WHERE id = ? AND customer_id IS NULL",
        (customer["id"], order["id"]),
    )
    connection.commit()
    code_row = connection.execute(
        """
        SELECT * FROM activation_codes
        WHERE order_id = ? AND used_at IS NULL AND revoked_at IS NULL
        ORDER BY id DESC LIMIT 1
        """,
        (order["id"],),
    ).fetchone()
    valid_shape = len(code) == 12 and all(character in CODE_ALPHABET for character in code)
    valid = bool(
        code_row
        and code_row["expires_at"] > utc_now()
        and int(code_row["failed_attempts"]) < CODE_ATTEMPT_LIMIT
        and valid_shape
        and hmac.compare_digest(
            code_row["code_hash"], hash_scoped_token("activation-code", code)
        )
    )
    if not valid:
        if code_row is not None:
            attempts = int(code_row["failed_attempts"]) + 1
            connection.execute(
                """
                UPDATE activation_codes
                SET failed_attempts = ?, revoked_at = CASE WHEN ? >= ? THEN ? ELSE revoked_at END
                WHERE id = ?
                """,
                (attempts, attempts, CODE_ATTEMPT_LIMIT, utc_now(), code_row["id"]),
            )
            connection.commit()
        score = 65 if code_row is not None and attempts >= CODE_ATTEMPT_LIMIT else 20 + min(attempts if code_row else 1, 4) * 5
        record_access_event(
            "activation_code_rejected", score, "rejected",
            customer_id=customer["id"], order_id=order["id"],
            metadata={"attempts": attempts if code_row is not None else 1},
        )
        return render_template(
            "activate.html",
            order=order,
            activation_token=activation_token,
            activated=False,
            resent=False,
            error="開通碼錯誤、已失效或嘗試次數過多。請重新寄送開通資料。",
        ), 400

    cursor = connection.execute(
        """
        UPDATE activation_codes SET used_at = ?
        WHERE id = ? AND used_at IS NULL AND revoked_at IS NULL
        """,
        (utc_now(), code_row["id"]),
    )
    connection.commit()
    if cursor.rowcount != 1:
        return render_template(
            "message.html", title="開通碼已使用", message="請使用 Email 重新登入已購買內容。"
        ), 409

    record_access_event(
        "activation_code_accepted", 5, "order_activated",
        customer_id=customer["id"], order_id=order["id"],
    )
    raw_session, raw_device, _session_id = _create_customer_session(order["customer_email"])
    response = redirect(url_for("access.order_content", order_no=order["order_no"]))
    return _set_customer_cookies(response, raw_session, raw_device)


@access_bp.post("/activate/<activation_token>/resend")
def resend_activation(activation_token):
    csrf_error = require_public_csrf()
    if csrf_error:
        return csrf_error
    order = _order_for_activation_token(activation_token)
    if order is None or order["status"] != "paid":
        return redirect(
            url_for("access.activate_page", activation_token=activation_token, delivery_error="unavailable")
        )
    if _delivery_rate_limited(order["id"], "activation"):
        return redirect(
            url_for("access.activate_page", activation_token=activation_token, delivery_error="rate_limited")
        )
    delivery = issue_activation_delivery(order["id"])
    if delivery.get("status") in {"sent", "development"}:
        return redirect(url_for("access.activate_page", activation_token=activation_token, resent="1"))
    return redirect(
        url_for("access.activate_page", activation_token=activation_token, delivery_error="failed")
    )


@access_bp.get("/customer/login")
def customer_login_page():
    return render_template("customer_login.html", step="request", error="", sent=False)


@access_bp.post("/customer/login/request")
def customer_login_request():
    csrf_error = require_public_csrf()
    if csrf_error:
        return csrf_error
    email = _normalize_email(request.form.get("customer_email", ""))
    session["customer_login_email"] = email
    result = _issue_login_delivery(email)
    if result.get("development_code"):
        session["dev_login_code"] = result["development_code"]
    return redirect(url_for("access.customer_login_verify"))


@access_bp.get("/customer/login/verify")
def customer_login_verify():
    if not session.get("customer_login_email"):
        return redirect(url_for("access.customer_login_page"))
    return render_template(
        "customer_login.html",
        step="verify",
        error="",
        sent=True,
        development_code=session.pop("dev_login_code", ""),
    )


@access_bp.post("/customer/login/verify")
def customer_login_complete():
    csrf_error = require_public_csrf()
    if csrf_error:
        return csrf_error
    from .risk import record_access_event

    email = _normalize_email(session.get("customer_login_email", ""))
    code = _normalize_code(request.form.get("login_code", ""))
    connection = get_db()
    code_row = connection.execute(
        """
        SELECT * FROM customer_login_codes
        WHERE customer_email = ? AND used_at IS NULL AND revoked_at IS NULL
        ORDER BY id DESC LIMIT 1
        """,
        (email,),
    ).fetchone()
    valid_shape = len(code) == 12 and all(character in CODE_ALPHABET for character in code)
    valid = bool(
        code_row
        and code_row["expires_at"] > utc_now()
        and int(code_row["failed_attempts"]) < CODE_ATTEMPT_LIMIT
        and valid_shape
        and hmac.compare_digest(
            code_row["code_hash"], hash_scoped_token("customer-login-code", code)
        )
    )
    if not valid:
        if code_row is not None:
            attempts = int(code_row["failed_attempts"]) + 1
            connection.execute(
                """
                UPDATE customer_login_codes
                SET failed_attempts = ?, revoked_at = CASE WHEN ? >= ? THEN ? ELSE revoked_at END
                WHERE id = ?
                """,
                (attempts, attempts, CODE_ATTEMPT_LIMIT, utc_now(), code_row["id"]),
            )
            connection.commit()
        customer = connection.execute(
            "SELECT id FROM customers WHERE normalized_email = ?", (email,)
        ).fetchone()
        score = 65 if code_row is not None and attempts >= CODE_ATTEMPT_LIMIT else 20 + min(attempts if code_row else 1, 4) * 5
        record_access_event(
            "customer_login_code_rejected", score, "rejected",
            customer_id=customer["id"] if customer else None,
            metadata={"attempts": attempts if code_row is not None else 1},
        )
        return render_template(
            "customer_login.html",
            step="verify",
            error="登入碼錯誤或已超過 10 分鐘。請重新申請。",
            sent=True,
            development_code="",
        ), 400

    connection.execute(
        "UPDATE customer_login_codes SET used_at = ? WHERE id = ?",
        (utc_now(), code_row["id"]),
    )
    connection.commit()
    customer = _ensure_customer(email)
    record_access_event(
        "customer_login_code_accepted", 5, "login_verified", customer_id=customer["id"]
    )
    raw_session, raw_device, _session_id = _create_customer_session(email)
    session.pop("customer_login_email", None)
    response = redirect(url_for("access.customer_library"))
    return _set_customer_cookies(response, raw_session, raw_device)


@access_bp.get("/customer/library")
@customer_required
def customer_library():
    email = current_customer_email()
    orders = get_db().execute(
        """
        SELECT orders.order_no, orders.paid_at, ideas.title, ideas.role, ideas.discipline
        FROM orders JOIN ideas ON ideas.id = orders.idea_id
        WHERE orders.customer_email = ? AND orders.status = 'paid'
        ORDER BY orders.paid_at DESC, orders.id DESC
        """,
        (email,),
    ).fetchall()
    return render_template("customer_library.html", orders=orders)


@access_bp.get("/library/orders/<order_no>")
@customer_required
def order_content(order_no):
    customer_session = current_customer_session()
    email = customer_session["customer_email"] if customer_session else ""
    order = get_db().execute(
        """
        SELECT orders.*, ideas.title, ideas.role, ideas.discipline, ideas.primary_vein,
               ideas.secondary_vein, ideas.maturity, ideas.paid_content,
               ideas.deliverables, ideas.accent, ideas.hero_image,
               ideas.diagram_image, ideas.scene_image
        FROM orders JOIN ideas ON ideas.id = orders.idea_id
        WHERE orders.order_no = ? AND orders.customer_email = ? AND orders.status = 'paid'
        """,
        (order_no, email),
    ).fetchone()
    if order is None:
        return render_template(
            "message.html", title="找不到已購買內容", message="請確認登入的 Email 是否為購買時使用的 Email。"
        ), 404
    return render_template(
        "order_access.html",
        order=order,
        access_context={
            "customer": customer_session["customer_public_id"],
            "device": customer_session["device_public_id"] or "DEV-UNKNOWN",
            "order": f"ORD-***{order['order_no'][-6:]}",
            "time": f"{utc_now()[:16].replace('T', ' ')}Z",
        },
    )


@access_bp.post("/customer/logout")
def customer_logout():
    csrf_error = require_public_csrf()
    if csrf_error:
        return csrf_error
    raw_token = request.cookies.get(CUSTOMER_COOKIE, "")
    if raw_token:
        connection = get_db()
        connection.execute(
            """
            UPDATE customer_sessions SET revoked_at = ?, revoked_reason = 'logout'
            WHERE session_hash = ? AND revoked_at IS NULL
            """,
            (utc_now(), hash_token(raw_token)),
        )
        connection.commit()
    response = redirect(url_for("public.home"))
    response.delete_cookie(CUSTOMER_COOKIE, path="/")
    return response
