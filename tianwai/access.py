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
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
ACTIVATION_CODE_HOURS = 24
LOGIN_CODE_MINUTES = 7
CUSTOMER_SESSION_DAYS = 30
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


def _order_for_activation_token(activation_token):
    return get_db().execute(
        """
        SELECT orders.*, ideas.title, ideas.role, ideas.discipline, ideas.paid_content,
               ideas.deliverables, ideas.accent
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
        SELECT orders.*, ideas.title FROM orders
        JOIN ideas ON ideas.id = orders.idea_id
        WHERE orders.id = ?
        """,
        (order_id,),
    ).fetchone()
    if order is None or order["status"] != "paid":
        return {"status": "not_paid"}

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
            _iso(now + timedelta(hours=ACTIVATION_CODE_HOURS)),
        ),
    )
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
        "開通碼有效 24 小時，成功使用後會立即失效，請勿轉傳。\n"
        "開通後，您的購買權限會保留；日後重新登入時，系統會另寄一組 7 分鐘有效的登入碼。\n"
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
            (utc_now(), order_id, cursor.lastrowid),
        )
        connection.execute(
            "UPDATE activation_codes SET delivery_status = ? WHERE id = ?",
            (status, cursor.lastrowid),
        )
    else:
        connection.execute(
            """
            UPDATE activation_codes SET delivery_status = 'failed', revoked_at = ? WHERE id = ?
            """,
            (utc_now(), cursor.lastrowid),
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
    connection.commit()
    formatted_code = _format_code(code)
    status = send_email(
        email,
        "天外一筆｜7 分鐘登入驗證碼",
        (
            f"您的登入驗證碼是：{formatted_code}\n\n"
            "此驗證碼僅能使用一次，並會在 7 分鐘後自動失效。\n"
            "驗證碼失效不會影響已購買的內容，可回到登入頁重新申請。\n"
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
            (utc_now(), email, cursor.lastrowid),
        )
    else:
        connection.execute(
            "UPDATE customer_login_codes SET revoked_at = ? WHERE id = ?",
            (utc_now(), cursor.lastrowid),
        )
    connection.commit()
    return {
        "status": status,
        "development_code": formatted_code if status == "development" else "",
    }


def _create_customer_session(email):
    raw_token = secrets.token_urlsafe(32)
    now = _now()
    connection = get_db()
    connection.execute(
        """
        INSERT INTO customer_sessions
            (session_hash, customer_email, created_at, last_seen_at, expires_at, user_agent)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            hash_token(raw_token),
            email,
            _iso(now),
            _iso(now),
            _iso(now + timedelta(days=CUSTOMER_SESSION_DAYS)),
            safe_user_agent(),
        ),
    )
    connection.commit()
    return raw_token


def _set_customer_cookie(response, raw_token):
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
    return response


def current_customer_email():
    raw_token = request.cookies.get(CUSTOMER_COOKIE, "")
    if not raw_token:
        return None
    connection = get_db()
    row = connection.execute(
        """
        SELECT * FROM customer_sessions
        WHERE session_hash = ? AND revoked_at IS NULL AND expires_at > ?
        """,
        (hash_token(raw_token), utc_now()),
    ).fetchone()
    if row is None:
        return None
    connection.execute(
        "UPDATE customer_sessions SET last_seen_at = ? WHERE id = ?",
        (utc_now(), row["id"]),
    )
    connection.commit()
    return row["customer_email"]


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
    return render_template(
        "activate.html",
        order=order,
        activation_token=activation_token,
        activated=activated,
        resent=request.args.get("resent") == "1",
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

    code = _normalize_code(request.form.get("activation_code", ""))
    connection = get_db()
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
        log_security_event("activation_code_rejected", "medium", "rejected", f"order={order['order_no']}")
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

    raw_session = _create_customer_session(order["customer_email"])
    response = redirect(url_for("access.order_content", order_no=order["order_no"]))
    return _set_customer_cookie(response, raw_session)


@access_bp.post("/activate/<activation_token>/resend")
def resend_activation(activation_token):
    csrf_error = require_public_csrf()
    if csrf_error:
        return csrf_error
    order = _order_for_activation_token(activation_token)
    if order is not None and order["status"] == "paid" and not _delivery_rate_limited(order["id"], "activation"):
        issue_activation_delivery(order["id"])
    return redirect(url_for("access.activate_page", activation_token=activation_token, resent="1"))


@access_bp.get("/customer/login")
def customer_login_page():
    return render_template("customer_login.html", step="request", error="", sent=False)


@access_bp.post("/customer/login/request")
def customer_login_request():
    csrf_error = require_public_csrf()
    if csrf_error:
        return csrf_error
    email = str(request.form.get("customer_email", "")).strip().lower()[:254]
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
    email = str(session.get("customer_login_email", "")).strip().lower()
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
        log_security_event("customer_login_code_rejected", "medium", "rejected", "invalid_or_expired")
        return render_template(
            "customer_login.html",
            step="verify",
            error="登入碼錯誤或已超過 7 分鐘。請重新申請。",
            sent=True,
            development_code="",
        ), 400

    connection.execute(
        "UPDATE customer_login_codes SET used_at = ? WHERE id = ?",
        (utc_now(), code_row["id"]),
    )
    connection.commit()
    raw_session = _create_customer_session(email)
    session.pop("customer_login_email", None)
    response = redirect(url_for("access.customer_library"))
    return _set_customer_cookie(response, raw_session)


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
    email = current_customer_email()
    order = get_db().execute(
        """
        SELECT orders.*, ideas.title, ideas.role, ideas.discipline, ideas.paid_content,
               ideas.deliverables, ideas.accent
        FROM orders JOIN ideas ON ideas.id = orders.idea_id
        WHERE orders.order_no = ? AND orders.customer_email = ? AND orders.status = 'paid'
        """,
        (order_no, email),
    ).fetchone()
    if order is None:
        return render_template(
            "message.html", title="找不到已購買內容", message="請確認登入的 Email 是否為購買時使用的 Email。"
        ), 404
    return render_template("order_access.html", order=order)


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
