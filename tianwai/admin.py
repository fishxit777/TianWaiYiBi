import base64
import ipaddress
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, make_response, redirect, render_template, request, session, url_for
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse

from .analytics import ALLOWED_WINDOWS, build_demand_radar
from .db import get_db, get_setting_int, utc_now
from .mailer import email_delivery_ready
from .risk import verify_access_event_chain
from .security import (
    ADMIN_COOKIE,
    ADMIN_SESSION_HOURS,
    admin_cookie_secure,
    admin_credentials_valid,
    admin_password_hash_configured,
    admin_mutation_guard,
    admin_required,
    create_admin_session,
    current_admin_session,
    get_client_ip,
    is_admin_ip_allowed,
    log_audit,
    log_security_event,
    public_csrf_valid,
    register_login_attempt,
    revoke_admin_session,
)
from .passkeys import (
    activate_passkey_only,
    active_credential_count,
    active_credentials,
    authentication_challenge_allowed,
    begin_authentication,
    begin_registration,
    consume_challenge,
    passkey_only_enabled,
    revoke_credential,
    verify_and_store_registration,
    verify_and_update_authentication,
)
from .recovery import (
    available_recovery_code_count,
    consume_recovery_code,
    generate_recovery_codes,
    revoke_all_passkeys,
)
from .turnstile import turnstile_configured, turnstile_site_key, verify_turnstile
from .conversations import (
    IDEA_SECTION,
    customer_identity,
    message_query,
    normalize_message_body,
    resolve_section_context,
    serialize_message,
)


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
PAYMENT_VERIFICATION_AMOUNT = 6

IDEA_ACCENTS = {"cinnabar", "jade", "gold", "azure", "violet", "silver"}
IDEA_TEXT_RULES = {
    "title": (2, 80),
    "role": (2, 60),
    "seal": (1, 4),
    "discipline": (2, 100),
    "summary": (10, 240),
    "teaser": (10, 600),
    "paid_content": (20, 6000),
    "deliverables": (2, 500),
    "tags": (1, 200),
}


def _mask_email(value):
    local, _, domain = str(value).partition("@")
    if not domain:
        return "***"
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}***@{domain}"


def _mask_ip(value):
    try:
        address = ipaddress.ip_address(str(value))
    except ValueError:
        return "unknown"
    if address.version == 4:
        parts = str(address).split(".")
        return f"{parts[0]}.{parts[1]}.*.*"
    parts = address.exploded.split(":")
    return f"{parts[0]}:{parts[1]}::*"


def _notify_customer_conversation_reply(connection, customer, visibility):
    """Send only a neutral login notice; never copy the conversation body to email."""
    if customer is None:
        return "not_targeted"
    order = connection.execute(
        """
        SELECT id FROM orders
        WHERE customer_id = ? AND status = 'paid' AND purpose = 'sale'
        ORDER BY paid_at DESC, id DESC LIMIT 1
        """,
        (customer["id"],),
    ).fetchone()
    if order is None:
        return "no_entitlement"
    from .mailer import send_email

    base_url = os.environ.get("BASE_URL", "").strip().rstrip("/")
    login_url = f"{base_url}/customer/login" if base_url else "天外一筆客戶登入頁"
    scope = "私密傳音" if visibility == "private" else "公開傳音"
    return send_email(
        customer["normalized_email"],
        f"天外一筆｜你的{scope}有新回覆",
        (
            f"守閣者已回覆你的{scope}。\n\n"
            f"請由官網登入後查看：{login_url}\n\n"
            "為保護隱私，本通知不包含對話正文。天外一筆不會在信件中索取密碼、驗證碼或付款資料。\n"
        ),
        "conversation_reply",
        order["id"],
    )


@admin_bp.get("/login")
def login_page():
    if current_admin_session() is not None:
        return redirect(url_for("admin.dashboard"))
    return render_template(
        "admin_login.html",
        error=None,
        password_login_available=not passkey_only_enabled(),
    )


def _set_admin_cookie(response, raw_token):
    response.set_cookie(
        ADMIN_COOKIE,
        raw_token,
        max_age=ADMIN_SESSION_HOURS * 3600,
        httponly=True,
        secure=admin_cookie_secure(),
        samesite="Strict",
        path="/admin",
    )
    return response


def _encode_challenge(challenge):
    return base64.urlsafe_b64encode(bytes(challenge)).decode("ascii").rstrip("=")


def _decode_challenge(value):
    raw = str(value or "")
    return base64.urlsafe_b64decode(raw + "=" * ((4 - len(raw) % 4) % 4))


def _recovery_enabled():
    return os.environ.get("ADMIN_RECOVERY_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _recovery_available():
    return bool(
        _recovery_enabled()
        and admin_password_hash_configured()
        and turnstile_configured()
        and available_recovery_code_count() > 0
    )


@admin_bp.post("/login")
def login_submit():
    if passkey_only_enabled():
        log_security_event("admin_password_login_disabled", "medium", "rejected", "passkey_only")
        return "", 404
    if not is_admin_ip_allowed():
        log_security_event("admin_ip_denied", "high", "rejected", "allowlist_mismatch")
        return "", 404
    if not public_csrf_valid():
        log_security_event("admin_login_csrf_rejected", "high", "rejected", "csrf_mismatch")
        return render_template(
            "admin_login.html",
            error="安全驗證已過期，請重新整理後再試。",
            password_login_available=True,
        ), 403
    username = request.form.get("username", "")[:120]
    password = request.form.get("password", "")[:512]
    if not admin_credentials_valid(username, password):
        failures = register_login_attempt(False)
        status = 429 if failures >= 5 else 403
        return render_template(
            "admin_login.html",
            error="帳號或密碼錯誤，請稍後再試。",
            password_login_available=True,
        ), status

    register_login_attempt(True)
    raw_token = create_admin_session(auth_method="password")
    log_audit("admin_login", "admin", "server_side_session_created")
    response = make_response(redirect(url_for("admin.dashboard")))
    return _set_admin_cookie(response, raw_token)


@admin_bp.post("/identity/options")
def identity_authentication_options():
    if not is_admin_ip_allowed():
        return "", 404
    if not public_csrf_valid():
        return jsonify({"error": "安全驗證已過期，請重新整理後再試。"}), 403
    if active_credential_count() < 1:
        return jsonify({"error": "無法完成身分驗證。"}), 403
    if not authentication_challenge_allowed():
        log_security_event(
            "admin_identity_challenge_rate_limited",
            "high",
            "rejected",
            "challenge_issuance_limit",
        )
        return jsonify({"error": "請求過於頻繁，請稍後再試。"}), 429
    options, challenge = begin_authentication()
    session["admin_webauthn_auth_challenge"] = _encode_challenge(challenge)
    return jsonify({"publicKey": json.loads(options)})


@admin_bp.post("/identity/verify")
def identity_authentication_verify():
    if not is_admin_ip_allowed():
        return "", 404
    if not public_csrf_valid():
        return jsonify({"error": "安全驗證已過期，請重新整理後再試。"}), 403
    encoded_challenge = session.pop("admin_webauthn_auth_challenge", "")
    payload = request.get_json(silent=True) or {}
    credential = payload.get("credential")
    if not encoded_challenge or not isinstance(credential, dict):
        return jsonify({"error": "驗證已過期，請重新操作。"}), 400
    try:
        challenge = _decode_challenge(encoded_challenge)
        if not consume_challenge("authentication", challenge):
            raise ValueError("challenge_rejected")
        verify_and_update_authentication(credential, challenge)
    except (InvalidAuthenticationResponse, ValueError, TypeError):
        failures = register_login_attempt(False)
        status = 429 if failures >= 5 else 403
        return jsonify({"error": "無法完成身分驗證，請稍後再試。"}), status

    register_login_attempt(True)
    raw_token = create_admin_session(auth_method="passkey")
    log_audit("admin_passkey_login", "admin", "server_side_session_created")
    response = jsonify({"ok": True, "redirect": url_for("admin.dashboard")})
    return _set_admin_cookie(response, raw_token)


@admin_bp.get("/passkeys/setup")
@admin_required
def passkey_setup():
    credentials = [
        {
            "id": row["id"],
            "label": row["label"],
            "device_type": row["device_type"],
            "backed_up": bool(row["backed_up"]),
            "created_at": row["created_at"],
            "last_used_at": row["last_used_at"],
        }
        for row in active_credentials()
    ]
    admin_session = current_admin_session()
    return render_template(
        "admin_passkeys.html",
        admin_csrf=admin_session["csrf_token"],
        credentials=credentials,
        passkey_only=passkey_only_enabled(),
        recovery_mode=bool(admin_session["restricted"]),
        recovery_code_count=available_recovery_code_count(),
    )


@admin_bp.post("/api/passkeys/registration/options")
@admin_required
def passkey_registration_options():
    guard = admin_mutation_guard()
    if guard:
        return guard
    options, challenge = begin_registration()
    session["admin_webauthn_registration_challenge"] = _encode_challenge(challenge)
    return jsonify({"publicKey": json.loads(options)})


@admin_bp.post("/api/passkeys/registration/verify")
@admin_required
def passkey_registration_verify():
    guard = admin_mutation_guard()
    if guard:
        return guard
    encoded_challenge = session.pop("admin_webauthn_registration_challenge", "")
    payload = request.get_json(silent=True) or {}
    credential = payload.get("credential")
    label = str(payload.get("label", "Passkey"))[:80]
    transports = payload.get("transports") or []
    if not encoded_challenge or not isinstance(credential, dict) or not isinstance(transports, list):
        return jsonify({"error": "Passkey 登記已過期，請重新操作。"}), 400
    try:
        challenge = _decode_challenge(encoded_challenge)
        if not consume_challenge("registration", challenge):
            raise ValueError("challenge_rejected")
        credential_id = verify_and_store_registration(
            credential,
            expected_challenge=challenge,
            label=label,
            transports=transports,
        )
    except (InvalidRegistrationResponse, ValueError, TypeError):
        log_security_event("admin_passkey_registration_failed", "high", "rejected", "invalid_response")
        return jsonify({"error": "Passkey 登記失敗，請重新操作。"}), 400
    log_audit("admin_passkey_registered", f"credential:{credential_id}", "public_key_only")
    return jsonify({"ok": True, "credential_id": credential_id})


@admin_bp.post("/api/passkeys/activate")
@admin_required
def passkey_activate():
    guard = admin_mutation_guard()
    if guard:
        return guard
    if not activate_passkey_only():
        return jsonify({"error": "至少需要兩個已驗證 Passkey 才能停用一般密碼登入。"}), 409
    admin_session = current_admin_session()
    if bool(admin_session["restricted"]):
        connection = get_db()
        connection.execute(
            "UPDATE admin_sessions SET restricted = 0, auth_method = 'passkey' WHERE id = ?",
            (admin_session["id"],),
        )
        connection.commit()
        log_security_event(
            "admin_recovery_completed", "critical", "two_passkeys_reenrolled", "recovery_session_upgraded"
        )
    log_audit("admin_passkey_only_enabled", "admin", "two_or_more_credentials")
    return jsonify({"ok": True})


@admin_bp.post("/api/passkeys/<int:credential_id>/revoke")
@admin_required
def passkey_revoke(credential_id):
    guard = admin_mutation_guard()
    if guard:
        return guard
    if passkey_only_enabled() and active_credential_count() <= 1:
        return jsonify({"error": "不能撤銷最後一個可用 Passkey。"}), 409
    if not revoke_credential(credential_id, "owner_revoked"):
        return jsonify({"error": "找不到可撤銷的 Passkey。"}), 404
    log_audit("admin_passkey_revoked", f"credential:{credential_id}", "owner_revoked")
    return jsonify({"ok": True})


@admin_bp.post("/api/passkeys/recovery-codes")
@admin_required
def rotate_recovery_codes():
    guard = admin_mutation_guard()
    if guard:
        return guard
    admin_session = current_admin_session()
    if bool(admin_session["restricted"]):
        return jsonify({"error": "請先完成兩把 Passkey 的重新登記。"}), 409
    codes = generate_recovery_codes()
    log_audit("admin_recovery_codes_rotated", "admin", f"count={len(codes)};plaintext_not_persisted")
    return jsonify({"ok": True, "codes": codes, "count": len(codes)})


@admin_bp.get("/recovery")
def recovery_page():
    if not _recovery_available():
        return "", 404
    return render_template(
        "admin_recovery.html",
        error=None,
        turnstile_site_key=turnstile_site_key(),
    )


@admin_bp.post("/recovery")
def recovery_submit():
    if not _recovery_available():
        return "", 404
    if not is_admin_ip_allowed():
        return "", 404
    if not public_csrf_valid():
        return render_template(
            "admin_recovery.html",
            error="安全驗證已過期，請重新整理後再試。",
            turnstile_site_key=turnstile_site_key(),
        ), 403

    turnstile_token = request.form.get("cf-turnstile-response", "")[:2048]
    username = request.form.get("username", "")[:120]
    password = request.form.get("password", "")[:512]
    recovery_code = request.form.get("recovery_code", "")[:80]
    verified = (
        verify_turnstile(turnstile_token, get_client_ip())
        and admin_credentials_valid(username, password)
        and consume_recovery_code(recovery_code)
    )
    if not verified:
        failures = register_login_attempt(False)
        status = 429 if failures >= 5 else 403
        return render_template(
            "admin_recovery.html",
            error="復原驗證失敗，請確認三項資料後重新操作。",
            turnstile_site_key=turnstile_site_key(),
        ), status

    connection = get_db()
    connection.execute(
        "UPDATE admin_sessions SET revoked_at = ?, revoked_reason = 'emergency_recovery' WHERE revoked_at IS NULL",
        (utc_now(),),
    )
    connection.commit()
    revoked_credentials = revoke_all_passkeys("emergency_recovery")
    raw_token = create_admin_session(auth_method="recovery", restricted=True)
    register_login_attempt(True)
    log_security_event(
        "admin_emergency_recovery", "critical", "sessions_and_passkeys_revoked",
        f"passkeys_revoked={revoked_credentials};codes_not_logged",
    )
    log_audit("admin_emergency_recovery", "admin", "restricted_session_created;two_passkeys_required")
    response = make_response(redirect(url_for("admin.passkey_setup")))
    return _set_admin_cookie(response, raw_token)


@admin_bp.post("/logout")
@admin_required
def logout():
    guard = admin_mutation_guard()
    if guard:
        return guard
    revoke_admin_session("logout")
    log_audit("admin_logout", "admin", "session_revoked")
    response = make_response(redirect(url_for("admin.login_page")))
    response.delete_cookie(ADMIN_COOKIE, path="/admin")
    return response


@admin_bp.get("")
@admin_required
def dashboard():
    admin_session = current_admin_session()
    return render_template(
        "admin_dashboard.html",
        admin_csrf=admin_session["csrf_token"],
        username=os.environ.get("ADMIN_USERNAME", "admin"),
    )


@admin_bp.get("/api/dashboard")
@admin_required
def dashboard_data():
    from .payments import (
        checkout_url_for,
        payment_checkout_status,
        verification_payment_token,
    )

    connection = get_db()
    checkout_status = payment_checkout_status()
    verification_status = payment_checkout_status(verification=True)
    try:
        requested_analytics_days = int(request.args.get("analytics_days", 30))
    except (TypeError, ValueError):
        requested_analytics_days = 30
    analytics_days = requested_analytics_days if requested_analytics_days in ALLOWED_WINDOWS else 30
    metrics = connection.execute(
        """
        SELECT
            COUNT(*) AS total_orders,
            SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) AS paid_orders,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_orders,
            COALESCE(SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END), 0) AS revenue
        FROM orders
        WHERE purpose = 'sale'
        """
    ).fetchone()
    analytics_period_start = (
        datetime.now(timezone.utc) - timedelta(days=30)
    ).isoformat(timespec="seconds")
    views = connection.execute(
        """
        SELECT COUNT(DISTINCT session_id) AS count FROM analytics_events
        WHERE event_name = 'view_idea' AND is_automated = 0
          AND source <> 'admin-preview' AND session_id IS NOT NULL AND session_id <> ''
          AND created_at >= ?
        """,
        (analytics_period_start,),
    ).fetchone()["count"]
    paid_sessions = connection.execute(
        """
        SELECT COUNT(DISTINCT session_id) AS count FROM analytics_events
        WHERE event_name = 'purchase_completed' AND is_automated = 0
          AND session_id IS NOT NULL AND session_id <> '' AND created_at >= ?
        """,
        (analytics_period_start,),
    ).fetchone()["count"]
    conversion = (
        round((int(paid_sessions or 0) / max(int(views), 1)) * 100, 1)
        if checkout_status["ready"]
        else None
    )
    demand_radar = build_demand_radar(
        connection,
        days=analytics_days,
        payment_ready=checkout_status["ready"],
    )
    ideas = connection.execute(
        "SELECT * FROM ideas ORDER BY sort_order, id"
    ).fetchall()
    orders = connection.execute(
        """
        SELECT orders.*, ideas.title, ideas.role
        FROM orders JOIN ideas ON ideas.id = orders.idea_id
        ORDER BY orders.id DESC LIMIT 50
        """
    ).fetchall()
    customer_metrics = connection.execute(
        """
        SELECT
            COUNT(DISTINCT CASE WHEN orders.status = 'paid' AND orders.purpose = 'sale' THEN orders.customer_email END) AS paid_customers,
            COUNT(DISTINCT CASE WHEN orders.status = 'paid' AND orders.purpose = 'sale' THEN orders.id END) AS paid_entitlements,
            COUNT(DISTINCT CASE WHEN orders.status = 'paid' AND orders.purpose = 'sale' AND activation_codes.used_at IS NOT NULL THEN orders.id END) AS activated_entitlements
        FROM orders
        LEFT JOIN activation_codes ON activation_codes.order_id = orders.id
        """
    ).fetchone()
    active_customer_sessions = connection.execute(
        """
        SELECT COUNT(DISTINCT customer_email) AS count
        FROM customer_sessions AS sessions
        WHERE revoked_at IS NULL AND expires_at > ?
          AND EXISTS (
              SELECT 1 FROM orders
              WHERE orders.customer_id = sessions.customer_id
                AND orders.status = 'paid' AND orders.purpose = 'sale'
          )
        """,
        (utc_now(),),
    ).fetchone()["count"]
    trusted_devices = connection.execute(
        """
        SELECT COUNT(*) AS count FROM customer_devices AS devices
        WHERE revoked_at IS NULL AND trusted_until > ?
          AND EXISTS (
              SELECT 1 FROM orders
              WHERE orders.customer_id = devices.customer_id
                AND orders.status = 'paid' AND orders.purpose = 'sale'
          )
        """,
        (utc_now(),),
    ).fetchone()["count"]
    customer_access = connection.execute(
        """
        SELECT
            orders.order_no,
            orders.customer_name,
            orders.customer_email,
            orders.paid_at,
            ideas.title,
            customers.public_id AS customer_public_id,
            COALESCE(customers.risk_level, 'low') AS risk_level,
            COALESCE((
                SELECT COUNT(*) FROM customer_devices
                WHERE customer_devices.customer_id = orders.customer_id
                  AND customer_devices.revoked_at IS NULL
                  AND customer_devices.trusted_until > ?
            ), 0) AS trusted_devices,
            CASE WHEN EXISTS (
                SELECT 1 FROM activation_codes
                WHERE activation_codes.order_id = orders.id
                  AND activation_codes.used_at IS NOT NULL
            ) THEN 1 ELSE 0 END AS activated,
            COALESCE((
                SELECT activation_codes.delivery_status FROM activation_codes
                WHERE activation_codes.order_id = orders.id
                ORDER BY activation_codes.id DESC LIMIT 1
            ), 'pending') AS delivery_status
        FROM orders
        JOIN ideas ON ideas.id = orders.idea_id
        LEFT JOIN customers ON customers.id = orders.customer_id
        WHERE orders.status = 'paid' AND orders.purpose = 'sale'
        ORDER BY orders.paid_at DESC, orders.id DESC
        LIMIT 40
        """,
        (utc_now(),),
    ).fetchall()
    security_events = connection.execute(
        "SELECT * FROM security_events ORDER BY id DESC LIMIT 40"
    ).fetchall()
    access_events = connection.execute(
        """
        SELECT access_events.*, customers.public_id AS customer_public_id,
               customer_devices.public_id AS device_public_id
        FROM access_events
        LEFT JOIN customers ON customers.id = access_events.customer_id
        LEFT JOIN customer_devices ON customer_devices.id = access_events.device_id
        ORDER BY access_events.id DESC LIMIT 60
        """
    ).fetchall()
    risk_incidents = connection.execute(
        """
        SELECT risk_incidents.*, customers.public_id AS customer_public_id,
               access_events.event_type, access_events.risk_score
        FROM risk_incidents
        LEFT JOIN customers ON customers.id = risk_incidents.customer_id
        JOIN access_events ON access_events.id = risk_incidents.access_event_id
        ORDER BY risk_incidents.id DESC LIMIT 40
        """
    ).fetchall()
    notification_queue = connection.execute(
        """
        SELECT id, dedupe_key, incident_id, channel, recipient_masked, status, attempts,
               last_error, created_at, updated_at, sent_at
        FROM notification_queue ORDER BY id DESC LIMIT 40
        """
    ).fetchall()
    customer_devices = connection.execute(
        """
        SELECT customer_devices.*, customers.public_id AS customer_public_id
        FROM customer_devices
        JOIN customers ON customers.id = customer_devices.customer_id
        ORDER BY customer_devices.last_seen_at DESC, customer_devices.id DESC
        LIMIT 100
        """
    ).fetchall()
    blocks = connection.execute(
        "SELECT * FROM blocked_ips WHERE blocked_until > ? ORDER BY blocked_until DESC",
        (utc_now(),),
    ).fetchall()
    audits = connection.execute(
        "SELECT * FROM audit_logs ORDER BY id DESC LIMIT 30"
    ).fetchall()
    revenue_days = connection.execute(
        """
        SELECT substr(paid_at, 1, 10) AS day, COALESCE(SUM(amount), 0) AS revenue
        FROM orders
        WHERE status = 'paid' AND purpose = 'sale' AND paid_at >= ?
        GROUP BY substr(paid_at, 1, 10)
        ORDER BY day
        """,
        ((datetime.now(timezone.utc) - timedelta(days=6)).date().isoformat(),),
    ).fetchall()
    traffic_sources = connection.execute(
        """
        SELECT source, COUNT(*) AS count
        FROM analytics_events
        WHERE created_at >= ? AND is_automated = 0 AND source <> 'admin-preview'
        GROUP BY source ORDER BY count DESC
        """,
        ((datetime.now(timezone.utc) - timedelta(days=29)).isoformat(timespec="seconds"),),
    ).fetchall()
    line_event_count = connection.execute("SELECT COUNT(*) AS count FROM line_events").fetchone()["count"]
    conversation_counts = connection.execute(
        """
        SELECT
            SUM(CASE WHEN visibility = 'public' AND status = 'pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN visibility = 'public' AND status = 'published' THEN 1 ELSE 0 END) AS public_count,
            SUM(CASE WHEN visibility = 'private' AND status = 'published' THEN 1 ELSE 0 END) AS private_count
        FROM section_messages
        WHERE section_key = 'idea-detail' AND idea_id IS NOT NULL
        """
    ).fetchone()
    conversation_rows = connection.execute(
        f"{message_query()} WHERE section_messages.section_key = 'idea-detail' "
        "AND section_messages.idea_id IS NOT NULL "
        "ORDER BY section_messages.id DESC LIMIT 100"
    ).fetchall()
    conversation_customers = connection.execute(
        """
        SELECT customers.public_id
        FROM customers
        WHERE customers.status = 'active'
          AND EXISTS (
              SELECT 1 FROM orders
              WHERE orders.customer_id = customers.id
                AND orders.status = 'paid' AND orders.purpose = 'sale'
          )
        ORDER BY customers.created_at DESC, customers.id DESC
        LIMIT 200
        """
    ).fetchall()
    conversation_ideas = connection.execute(
        "SELECT slug, title FROM ideas WHERE published = 1 ORDER BY sort_order, id"
    ).fetchall()
    global_price = get_setting_int("idea_price", 199)
    base_url = os.environ.get("BASE_URL", "http://127.0.0.1:5088").strip()
    verification_order = connection.execute(
        """
        SELECT orders.*, ideas.title,
               CASE WHEN EXISTS (
                   SELECT 1 FROM activation_codes
                   WHERE activation_codes.order_id = orders.id
                     AND activation_codes.used_at IS NOT NULL
               ) THEN 1 ELSE 0 END AS activated
        FROM orders JOIN ideas ON ideas.id = orders.idea_id
        WHERE orders.purpose = 'verification'
        ORDER BY orders.id DESC LIMIT 1
        """
    ).fetchone()
    verification_latest = None
    if verification_order is not None:
        verification_latest = {
            "order_no": verification_order["order_no"],
            "title": verification_order["title"],
            "amount": int(verification_order["amount"]),
            "status": verification_order["status"],
            "activated": bool(verification_order["activated"]),
            "created_at": verification_order["created_at"],
            "paid_at": verification_order["paid_at"],
            "refunded_at": verification_order["refunded_at"],
            "checkout_url": (
                checkout_url_for(
                    verification_payment_token(verification_order["order_no"]),
                    verification=True,
                )
                if verification_order["status"] == "pending"
                and verification_status["ready"]
                else None
            ),
        }
    return jsonify(
        {
            "metrics": {
                "total_orders": int(metrics["total_orders"] or 0),
                "paid_orders": int(metrics["paid_orders"] or 0),
                "pending_orders": int(metrics["pending_orders"] or 0),
                "revenue": int(metrics["revenue"] or 0),
                "views": int(views or 0),
                "paid_sessions": int(paid_sessions or 0),
                "conversion": conversion,
                "conversion_available": bool(checkout_status["ready"]),
            },
            "demand_radar": demand_radar,
            "global_price": global_price,
            "ideas": [
                {
                    "id": row["id"],
                    "slug": row["slug"],
                    "title": row["title"],
                    "role": row["role"],
                    "seal": row["seal"],
                    "discipline": row["discipline"],
                    "summary": row["summary"],
                    "teaser": row["teaser"],
                    "paid_content": row["paid_content"],
                    "deliverables": row["deliverables"],
                    "tags": row["tags"],
                    "accent": row["accent"],
                    "sort_order": row["sort_order"],
                    "published": bool(row["published"]),
                    "price_override": row["price_override"],
                    "price": int(row["price_override"] if row["price_override"] is not None else global_price),
                }
                for row in ideas
            ],
            "orders": [
                {
                    "order_no": row["order_no"],
                    "title": row["title"],
                    "role": row["role"],
                    "customer_name": row["customer_name"],
                    "customer_email": _mask_email(row["customer_email"]),
                    "amount": row["amount"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "paid_at": row["paid_at"],
                    "purpose": row["purpose"],
                }
                for row in orders
            ],
            "customer_access": {
                "summary": {
                    "paid_customers": int(customer_metrics["paid_customers"] or 0),
                    "paid_entitlements": int(customer_metrics["paid_entitlements"] or 0),
                    "activated_entitlements": int(customer_metrics["activated_entitlements"] or 0),
                    "pending_activation": max(
                        int(customer_metrics["paid_entitlements"] or 0)
                        - int(customer_metrics["activated_entitlements"] or 0),
                        0,
                    ),
                    "active_sessions": int(active_customer_sessions or 0),
                    "trusted_devices": int(trusted_devices or 0),
                },
                "orders": [
                    {
                        "order_no": row["order_no"],
                        "customer_name": row["customer_name"],
                        "customer_email": _mask_email(row["customer_email"]),
                        "customer_public_id": row["customer_public_id"] or "尚未建立",
                        "risk_level": row["risk_level"],
                        "trusted_devices": int(row["trusted_devices"] or 0),
                        "title": row["title"],
                        "paid_at": row["paid_at"],
                        "activated": bool(row["activated"]),
                        "delivery_status": row["delivery_status"],
                    }
                    for row in customer_access
                ],
            },
            "security_events": [dict(row) for row in security_events],
            "access_events": [dict(row) for row in access_events],
            "risk_incidents": [dict(row) for row in risk_incidents],
            "notification_queue": [dict(row) for row in notification_queue],
            "customer_devices": [
                {
                    "id": row["id"],
                    "public_id": row["public_id"],
                    "customer_public_id": row["customer_public_id"],
                    "label": row["label"],
                    "last_ip": _mask_ip(row["last_ip"]),
                    "first_seen_at": row["first_seen_at"],
                    "last_seen_at": row["last_seen_at"],
                    "trusted_until": row["trusted_until"],
                    "revoked_at": row["revoked_at"],
                    "revoked_reason": row["revoked_reason"],
                }
                for row in customer_devices
            ],
            "evidence_chain": verify_access_event_chain(),
            "blocked_ips": [dict(row) for row in blocks],
            "audit_logs": [dict(row) for row in audits],
            "revenue_days": [dict(row) for row in revenue_days],
            "traffic_sources": [dict(row) for row in traffic_sources],
            "conversation_summary": {
                "pending": int(conversation_counts["pending"] or 0),
                "public": int(conversation_counts["public_count"] or 0),
                "private": int(conversation_counts["private_count"] or 0),
            },
            "conversation_messages": [
                serialize_message(row, admin_view=True) for row in conversation_rows
            ],
            "conversation_customers": [
                {
                    "public_id": row["public_id"],
                    **customer_identity(row["public_id"]),
                }
                for row in conversation_customers
            ],
            "conversation_sections": [
                {
                    "key": IDEA_SECTION,
                    "label": f"仙策・{row['title']}",
                    "idea_slug": row["slug"],
                }
                for row in conversation_ideas
            ],
            "integration_status": {
                "mode": checkout_status["mode"],
                "base_url": base_url,
                "public_https": base_url.lower().startswith("https://"),
                "line_channel": bool(os.environ.get("LINE_CHANNEL_SECRET") and os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")),
                "line_admin_alert": bool(
                    os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
                    and os.environ.get("LINE_ADMIN_USER_ID")
                ),
                "payment_provider": checkout_status["provider"],
                "payment_label": checkout_status["label"],
                "email_delivery": email_delivery_ready(),
                "admin_email_alert": bool(
                    os.environ.get("ADMIN_ALERT_EMAIL") and email_delivery_ready()
                ),
                "daily_summary_schedule": len(
                    os.environ.get("NOTIFICATION_CRON_SECRET", "").strip()
                ) >= 32,
                "line_events": int(line_event_count or 0),
            },
            "payment_verification": {
                "ready": verification_status["ready"],
                "enabled": verification_status.get("verification_enabled", False),
                "mode": verification_status["mode"],
                "amount": 1,
                "latest": verification_latest,
            },
            "security_config": {
                "admin_password_argon2": admin_password_hash_configured(),
                "allowlist_required": os.environ.get("ADMIN_IP_ALLOWLIST_REQUIRED", "false").lower()
                in {"1", "true", "yes", "on"},
                "session_ip_binding": os.environ.get("ADMIN_SESSION_BIND_IP", "true").lower()
                in {"1", "true", "yes", "on"},
                "line_signature_configured": bool(os.environ.get("LINE_CHANNEL_SECRET")),
                "line_admin_alert": bool(
                    os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
                    and os.environ.get("LINE_ADMIN_USER_ID")
                ),
                "admin_email_alert": bool(
                    os.environ.get("ADMIN_ALERT_EMAIL") and email_delivery_ready()
                ),
                "daily_summary_schedule": len(
                    os.environ.get("NOTIFICATION_CRON_SECRET", "").strip()
                ) >= 32,
                "payment_signature_configured": bool(os.environ.get("PAYMENT_WEBHOOK_SECRET")),
                "trusted_device_limit": 2,
                "single_active_session": True,
                "verification_code_minutes": 10,
            },
        }
    )


@admin_bp.post("/api/payment-verification/orders")
@admin_required
def create_payment_verification_order():
    guard = admin_mutation_guard()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    confirm_amount = data.get("confirm_amount")
    if isinstance(confirm_amount, bool) or confirm_amount != PAYMENT_VERIFICATION_AMOUNT:
        return jsonify({"error": "請明確確認本次驗證金額為 NT$6"}), 400

    from .payments import (
        checkout_url_for,
        payment_checkout_status,
        verification_payment_token,
    )
    from .security import derive_access_token, derive_activation_token, hash_token, safe_user_agent

    status = payment_checkout_status(verification=True)
    if not status["ready"] or status["provider"] != "ecpay":
        return jsonify({"error": "NT$6 正式驗證模式尚未安全就緒"}), 409

    connection = get_db()
    active = connection.execute(
        """
        SELECT * FROM orders
        WHERE purpose = 'verification' AND status IN ('pending', 'paid')
        ORDER BY id DESC LIMIT 1
        """
    ).fetchone()
    replaced_order_no = None
    if active is not None:
        if active["status"] == "paid":
            return jsonify({"error": "上一筆 NT$6 驗證訂單尚未完成退款與撤權"}), 409
        retry_order_no = str(data.get("retry_order_no") or "").strip()
        if not retry_order_no:
            payment_token = verification_payment_token(active["order_no"])
            return jsonify(
                {
                    "order_no": active["order_no"],
                    "amount": int(active["amount"]),
                    "checkout_url": checkout_url_for(payment_token, verification=True),
                    "payment_provider": "ecpay",
                    "result": "existing_pending",
                }
            )
        if retry_order_no != active["order_no"]:
            return jsonify({"error": "待付款驗證訂單已變更，請重新整理後再試"}), 409
        cancelled = connection.execute(
            "UPDATE orders SET status = 'cancelled' WHERE id = ? AND status = 'pending'",
            (active["id"],),
        )
        if cancelled.rowcount != 1:
            connection.rollback()
            return jsonify({"error": "待付款驗證訂單狀態已變更，請重新整理後再試"}), 409
        replaced_order_no = active["order_no"]

    idea = connection.execute(
        "SELECT id FROM ideas WHERE published = 1 ORDER BY sort_order, id LIMIT 1"
    ).fetchone()
    if idea is None:
        return jsonify({"error": "目前沒有可供驗證開通的仙策"}), 409

    verification_email = os.environ.get("PAYMENT_VERIFICATION_EMAIL", "").strip().lower()
    order_no = (
        f"TWYBV{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        f"{secrets.token_hex(4).upper()[:7]}"
    )
    payment_token = verification_payment_token(order_no)
    access_token = derive_access_token(payment_token)
    activation_token = derive_activation_token(order_no)
    now = utc_now()
    cursor = connection.execute(
        """
        INSERT INTO orders
            (order_no, idea_id, customer_name, customer_email, amount, status,
             purpose, payment_provider, payment_token_hash, access_token_hash,
             activation_token_hash, created_at)
        VALUES (?, ?, '金流驗收', ?, ?, 'pending', 'verification', ?, ?, ?, ?, ?)
        """,
        (
            order_no,
            idea["id"],
            verification_email,
            PAYMENT_VERIFICATION_AMOUNT,
            status["provider"],
            hash_token(payment_token),
            hash_token(access_token),
            hash_token(activation_token),
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO order_consents
            (order_id, terms_version, purchase_notice_consent, digital_content_consent,
             ip, user_agent, accepted_at)
        VALUES (?, '2026-08-24-payment-verification-v1', 1, 1, ?, ?, ?)
        """,
        (cursor.lastrowid, get_client_ip(), safe_user_agent(), now),
    )
    connection.commit()
    if replaced_order_no:
        log_audit(
            "replace_pending_payment_verification_order",
            replaced_order_no,
            f"replacement={order_no};amount={PAYMENT_VERIFICATION_AMOUNT};purpose=verification",
        )
    log_audit(
        "create_payment_verification_order",
        order_no,
        f"amount={PAYMENT_VERIFICATION_AMOUNT};purpose=verification",
    )
    return (
        jsonify(
            {
                "order_no": order_no,
                "amount": PAYMENT_VERIFICATION_AMOUNT,
                "checkout_url": checkout_url_for(payment_token, verification=True),
                "payment_provider": "ecpay",
                "result": "replaced" if replaced_order_no else "created",
            }
        ),
        201,
    )


@admin_bp.post(
    "/api/payment-verification/orders/<order_no>/refund-confirmation"
)
@admin_required
def confirm_payment_verification_refund(order_no):
    guard = admin_mutation_guard()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    confirmation = str(data.get("confirmation", ""))
    if data.get("external_refund_confirmed") is not True or not secrets.compare_digest(
        confirmation, str(order_no)
    ):
        return jsonify({"error": "請先在綠界確認退款成功，再輸入完整驗證訂單編號"}), 400

    connection = get_db()
    order = connection.execute(
        "SELECT * FROM orders WHERE order_no = ?", (str(order_no)[:20],)
    ).fetchone()
    if order is None:
        return jsonify({"error": "找不到驗證訂單"}), 404
    if order["status"] == "refunded":
        return jsonify(
            {"result": "already_refunded", "status": "refunded", "order_no": order["order_no"]}
        )
    if (
        order["purpose"] != "verification"
        or int(order["amount"]) != PAYMENT_VERIFICATION_AMOUNT
        or order["status"] != "paid"
        or order["payment_provider"] != "ecpay-production"
        or not str(order["payment_method"] or "").lower().startswith("credit_")
        or not order["payment_ref"]
    ):
        return jsonify({"error": "此訂單不符合 NT$6 正式信用卡退款撤權條件"}), 409

    now = utc_now()
    updated = connection.execute(
        """
        UPDATE orders SET status = 'refunded', refunded_at = ?
        WHERE id = ? AND status = 'paid' AND purpose = 'verification' AND amount = ?
        """,
        (now, order["id"], PAYMENT_VERIFICATION_AMOUNT),
    )
    if updated.rowcount != 1:
        connection.rollback()
        return jsonify({"error": "訂單狀態已變更，請重新整理確認"}), 409
    connection.execute(
        """
        INSERT INTO refund_events
            (event_id, order_id, provider, amount, method, result, created_at)
        VALUES (?, ?, 'ecpay-production', ?, 'ecpay-dashboard', 'confirmed', ?)
        """,
        (
            f"ecpay-dashboard:{order['order_no']}",
            order["id"],
            PAYMENT_VERIFICATION_AMOUNT,
            now,
        ),
    )
    connection.execute(
        """
        UPDATE activation_codes SET revoked_at = ?
        WHERE order_id = ? AND revoked_at IS NULL
        """,
        (now, order["id"]),
    )
    connection.execute(
        """
        UPDATE customer_login_codes SET revoked_at = ?
        WHERE customer_email = ? AND used_at IS NULL AND revoked_at IS NULL
        """,
        (now, order["customer_email"]),
    )
    remaining = connection.execute(
        """
        SELECT 1 FROM orders
        WHERE customer_id = ? AND status = 'paid' AND id <> ?
        LIMIT 1
        """,
        (order["customer_id"], order["id"]),
    ).fetchone()
    if order["customer_id"] is not None and remaining is None:
        connection.execute(
            """
            UPDATE customer_sessions
            SET revoked_at = ?, revoked_reason = 'verification_refunded'
            WHERE customer_id = ? AND revoked_at IS NULL
            """,
            (now, order["customer_id"]),
        )
        connection.execute(
            """
            UPDATE customer_devices
            SET revoked_at = ?, revoked_reason = 'verification_refunded'
            WHERE customer_id = ? AND revoked_at IS NULL
            """,
            (now, order["customer_id"]),
        )
    connection.execute(
        """
        INSERT INTO analytics_events (event_name, idea_id, source, session_id, created_at)
        VALUES ('payment_verification_refunded', ?, 'ecpay-production', NULL, ?)
        """,
        (order["idea_id"], now),
    )
    connection.commit()
    log_audit(
        "confirm_payment_verification_refund",
        order["order_no"],
        f"amount={PAYMENT_VERIFICATION_AMOUNT};provider=ecpay-production;entitlement_revoked",
    )
    return jsonify(
        {"result": "refund_confirmed", "status": "refunded", "order_no": order["order_no"]}
    )


@admin_bp.post("/api/conversations/<int:message_id>/moderate")
@admin_required
def moderate_conversation_message(message_id):
    guard = admin_mutation_guard()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    status = str(data.get("status", "")).strip().lower()
    if status not in {"published", "hidden"}:
        return jsonify({"error": "不支援的審核狀態"}), 400
    connection = get_db()
    message = connection.execute(
        "SELECT * FROM section_messages WHERE id = ?", (message_id,)
    ).fetchone()
    if message is None:
        return jsonify({"error": "找不到傳音"}), 404
    if status == "published" and message["visibility"] != "public":
        return jsonify({"error": "私密傳音不需要公開審核"}), 400
    now = utc_now()
    connection.execute(
        """
        UPDATE section_messages
        SET status = ?, moderated_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, now, now, message_id),
    )
    connection.commit()
    log_audit(
        "conversation_moderated",
        message["public_id"],
        f"visibility={message['visibility']};status={status}",
    )
    return jsonify({"ok": True, "status": status})


@admin_bp.post("/api/conversations/reply")
@admin_required
def reply_to_conversation():
    guard = admin_mutation_guard()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    visibility = str(data.get("visibility", "")).strip().lower()
    if visibility not in {"public", "private"}:
        return jsonify({"error": "不支援的傳音範圍"}), 400
    body, error = normalize_message_body(data.get("body", ""), visibility)
    if error:
        return jsonify({"error": error}), 400

    connection = get_db()
    reply_to = None
    reply_to_id = data.get("reply_to_id")
    if reply_to_id not in {None, ""}:
        try:
            reply_to_id = int(reply_to_id)
        except (TypeError, ValueError):
            return jsonify({"error": "回覆目標無效"}), 400
        reply_to = connection.execute(
            "SELECT * FROM section_messages WHERE id = ?", (reply_to_id,)
        ).fetchone()
        if reply_to is None:
            return jsonify({"error": "找不到原始傳音"}), 404
        if reply_to["visibility"] != visibility:
            return jsonify({"error": "公開與私密回覆不可混用"}), 400

    customer_public_id = str(data.get("customer_public_id", "")).strip()[:80]
    customer = None
    if customer_public_id:
        customer = connection.execute(
            "SELECT * FROM customers WHERE public_id = ? AND status = 'active'",
            (customer_public_id,),
        ).fetchone()
        if customer is None:
            return jsonify({"error": "找不到可用客戶"}), 404
    elif reply_to is not None and reply_to["customer_id"] is not None:
        customer = connection.execute(
            "SELECT * FROM customers WHERE id = ? AND status = 'active'",
            (reply_to["customer_id"],),
        ).fetchone()
    if visibility == "private" and customer is None:
        return jsonify({"error": "私密傳音必須指定客戶"}), 400
    if (
        reply_to is not None
        and customer is not None
        and reply_to["customer_id"] is not None
        and reply_to["customer_id"] != customer["id"]
    ):
        return jsonify({"error": "指定客戶與原始傳音不一致"}), 400
    if (
        reply_to is not None
        and reply_to["author_type"] == "visitor"
        and customer is not None
    ):
        return jsonify({"error": "訪客傳音不可改指定給客戶"}), 400

    if reply_to is not None:
        if reply_to["section_key"] != IDEA_SECTION or reply_to["idea_id"] is None:
            return jsonify({"error": "只支援六脈仙策傳音"}), 404
        section_key = reply_to["section_key"]
        idea_id = reply_to["idea_id"]
    else:
        context = resolve_section_context(
            data.get("section_key", ""), data.get("idea_slug", "")
        )
        if context is None:
            return jsonify({"error": "找不到傳音區塊"}), 404
        section_key = context["key"]
        idea_id = context["idea"]["id"] if context["idea"] else None

    now = utc_now()
    cursor = connection.execute(
        """
        INSERT INTO section_messages
            (public_id, section_key, idea_id, author_type, customer_id,
             visitor_token_hash, reply_to_id, visibility, status, body,
             moderated_at, created_at, updated_at)
        VALUES (?, ?, ?, 'admin', ?, ?, ?, ?, 'published', ?, ?, ?, ?)
        """,
        (
            f"MSG-{secrets.token_hex(8).upper()}",
            section_key,
            idea_id,
            customer["id"] if customer else None,
            (
                reply_to["visitor_token_hash"]
                if reply_to is not None and reply_to["customer_id"] is None
                else None
            ),
            reply_to_id,
            visibility,
            body,
            now,
            now,
            now,
        ),
    )
    message_id = cursor.lastrowid
    connection.commit()
    row = connection.execute(
        f"{message_query()} WHERE section_messages.id = ?", (message_id,)
    ).fetchone()
    delivery_status = _notify_customer_conversation_reply(
        connection, customer, visibility
    )
    log_audit(
        "conversation_replied",
        row["public_id"],
        f"visibility={visibility};section={section_key};target={'yes' if customer else 'no'};notice={delivery_status}",
    )
    response = jsonify(
        {"ok": True, "message": serialize_message(row, admin_view=True)}
    )
    response.status_code = 201
    return response


@admin_bp.post("/api/settings/price")
@admin_required
def update_price():
    guard = admin_mutation_guard()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    try:
        price = int(data.get("price"))
    except (TypeError, ValueError):
        return jsonify({"error": "價格必須是整數"}), 400
    if price < 1 or price > 100000:
        return jsonify({"error": "價格需介於 NT$1 與 NT$100,000"}), 400
    connection = get_db()
    connection.execute(
        """
        INSERT INTO settings (key, value, updated_at) VALUES ('idea_price', ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (str(price), utc_now()),
    )
    connection.commit()
    log_audit("update_global_price", str(price), "all_non_overridden_ideas")
    return jsonify({"ok": True, "price": price})


@admin_bp.post("/api/ideas/<int:idea_id>/publish")
@admin_required
def update_publish(idea_id):
    guard = admin_mutation_guard()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    published = data.get("published")
    if not isinstance(published, bool):
        return jsonify({"error": "published 必須是布林值"}), 400
    connection = get_db()
    cursor = connection.execute(
        "UPDATE ideas SET published = ?, updated_at = ? WHERE id = ?",
        (1 if published else 0, utc_now(), idea_id),
    )
    connection.commit()
    if cursor.rowcount == 0:
        return jsonify({"error": "找不到想法"}), 404
    log_audit("update_idea_publish", str(idea_id), f"published={published}")
    return jsonify({"ok": True, "published": published})


@admin_bp.post("/api/ideas/<int:idea_id>")
@admin_required
def update_idea(idea_id):
    guard = admin_mutation_guard()
    if guard:
        return guard
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "請提供有效的仙策資料"}), 400

    values = {}
    for field, (minimum, maximum) in IDEA_TEXT_RULES.items():
        value = str(data.get(field, "")).strip()
        if len(value) < minimum or len(value) > maximum:
            return jsonify({"error": f"{field} 長度需介於 {minimum} 與 {maximum} 個字元"}), 400
        values[field] = value

    accent = str(data.get("accent", "")).strip().lower()
    if accent not in IDEA_ACCENTS:
        return jsonify({"error": "accent 不在允許清單"}), 400
    try:
        sort_order = int(data.get("sort_order"))
    except (TypeError, ValueError):
        return jsonify({"error": "排序必須是整數"}), 400
    if sort_order < 1 or sort_order > 999:
        return jsonify({"error": "排序需介於 1 與 999"}), 400

    raw_override = data.get("price_override")
    if raw_override in (None, ""):
        price_override = None
    else:
        try:
            price_override = int(raw_override)
        except (TypeError, ValueError):
            return jsonify({"error": "單品價格必須是整數或留空"}), 400
        if price_override < 1 or price_override > 100000:
            return jsonify({"error": "單品價格需介於 NT$1 與 NT$100,000"}), 400

    connection = get_db()
    cursor = connection.execute(
        """
        UPDATE ideas SET
            title = ?, role = ?, seal = ?, discipline = ?, summary = ?, teaser = ?,
            paid_content = ?, deliverables = ?, tags = ?, accent = ?, sort_order = ?,
            price_override = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            values["title"], values["role"], values["seal"], values["discipline"],
            values["summary"], values["teaser"], values["paid_content"],
            values["deliverables"], values["tags"], accent, sort_order,
            price_override, utc_now(), idea_id,
        ),
    )
    connection.commit()
    if cursor.rowcount == 0:
        return jsonify({"error": "找不到想法"}), 404
    log_audit(
        "update_idea_content",
        str(idea_id),
        f"fields={','.join(IDEA_TEXT_RULES.keys())},accent,sort_order,price_override",
    )
    return jsonify({"ok": True, "idea_id": idea_id, "price_override": price_override})


@admin_bp.post("/api/security/test")
@admin_required
def security_test():
    guard = admin_mutation_guard()
    if guard:
        return guard
    log_security_event("manual_security_test", "info", "test_recorded", "admin_triggered")
    log_audit("security_test", "security_events", "manual_test")
    return jsonify({"ok": True}), 201


@admin_bp.post("/api/security/unblock")
@admin_required
def unblock_ip():
    guard = admin_mutation_guard()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    ip = str(data.get("ip", "")).strip()[:64]
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return jsonify({"error": "IP 格式不正確"}), 400
    connection = get_db()
    cursor = connection.execute("DELETE FROM blocked_ips WHERE ip = ?", (ip,))
    connection.commit()
    log_audit("security_unblock_ip", ip, f"removed={cursor.rowcount}")
    return jsonify({"ok": True, "removed": cursor.rowcount})


@admin_bp.post("/api/customers/devices/<int:device_id>/revoke")
@admin_required
def revoke_customer_device(device_id):
    guard = admin_mutation_guard()
    if guard:
        return guard
    from .risk import record_access_event

    connection = get_db()
    device = connection.execute(
        "SELECT * FROM customer_devices WHERE id = ?", (device_id,)
    ).fetchone()
    if device is None:
        return jsonify({"error": "找不到可信裝置"}), 404
    if device["revoked_at"] is None:
        now = utc_now()
        connection.execute(
            "UPDATE customer_devices SET revoked_at = ?, revoked_reason = 'admin_revoked' WHERE id = ?",
            (now, device_id),
        )
        connection.execute(
            """
            UPDATE customer_sessions
            SET revoked_at = ?, revoked_reason = 'admin_device_revoked'
            WHERE device_id = ? AND revoked_at IS NULL
            """,
            (now, device_id),
        )
        connection.commit()
        record_access_event(
            "trusted_device_admin_revoked", 5, "device_and_sessions_revoked",
            customer_id=device["customer_id"], device_id=device_id,
        )
    log_audit("revoke_customer_device", str(device_id), "device_and_sessions_revoked")
    return jsonify({"ok": True, "device_id": device_id})


@admin_bp.post("/api/security/incidents/<int:incident_id>")
@admin_required
def update_risk_incident(incident_id):
    guard = admin_mutation_guard()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    status = str(data.get("status", "")).strip().lower()
    if status not in {"reviewing", "resolved", "dismissed"}:
        return jsonify({"error": "案件狀態不正確"}), 400
    connection = get_db()
    cursor = connection.execute(
        "UPDATE risk_incidents SET status = ?, updated_at = ? WHERE id = ?",
        (status, utc_now(), incident_id),
    )
    connection.commit()
    if cursor.rowcount == 0:
        return jsonify({"error": "找不到風險案件"}), 404
    log_audit("update_risk_incident", str(incident_id), f"status={status}")
    return jsonify({"ok": True, "incident_id": incident_id, "status": status})


@admin_bp.post("/api/security/notifications/retry")
@admin_required
def retry_security_notifications():
    guard = admin_mutation_guard()
    if guard:
        return guard
    from .notifications import retry_private_alerts

    result = retry_private_alerts(limit=20)
    log_audit(
        "retry_security_notifications", "notification_queue",
        f"processed={result['processed']},sent={result['sent']}",
    )
    return jsonify({"ok": True, **result})
