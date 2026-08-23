import ipaddress
import os
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, make_response, redirect, render_template, request, url_for

from .db import get_db, get_setting_int, utc_now
from .mailer import email_delivery_ready
from .risk import verify_access_event_chain
from .security import (
    ADMIN_COOKIE,
    admin_cookie_secure,
    admin_credentials_valid,
    admin_password_hash_configured,
    admin_mutation_guard,
    admin_required,
    create_admin_session,
    current_admin_session,
    is_admin_ip_allowed,
    log_audit,
    log_security_event,
    public_csrf_valid,
    register_login_attempt,
    revoke_admin_session,
)


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

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


@admin_bp.get("/login")
def login_page():
    if current_admin_session() is not None:
        return redirect(url_for("admin.dashboard"))
    return render_template("admin_login.html", error=None)


@admin_bp.post("/login")
def login_submit():
    if not is_admin_ip_allowed():
        log_security_event("admin_ip_denied", "high", "rejected", "allowlist_mismatch")
        return "", 404
    if not public_csrf_valid():
        log_security_event("admin_login_csrf_rejected", "high", "rejected", "csrf_mismatch")
        return render_template("admin_login.html", error="安全驗證已過期，請重新整理後再試。"), 403
    username = request.form.get("username", "")[:120]
    password = request.form.get("password", "")[:512]
    if not admin_credentials_valid(username, password):
        failures = register_login_attempt(False)
        status = 429 if failures >= 5 else 403
        return render_template("admin_login.html", error="帳號或密碼錯誤，請稍後再試。"), status

    register_login_attempt(True)
    raw_token = create_admin_session()
    log_audit("admin_login", "admin", "server_side_session_created")
    response = make_response(redirect(url_for("admin.dashboard")))
    response.set_cookie(
        ADMIN_COOKIE,
        raw_token,
        max_age=8 * 3600,
        httponly=True,
        secure=admin_cookie_secure(),
        samesite="Strict",
        path="/admin",
    )
    return response


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
    from .payments import payment_checkout_status

    connection = get_db()
    checkout_status = payment_checkout_status()
    metrics = connection.execute(
        """
        SELECT
            COUNT(*) AS total_orders,
            SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) AS paid_orders,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_orders,
            COALESCE(SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END), 0) AS revenue
        FROM orders
        """
    ).fetchone()
    views = connection.execute(
        "SELECT COUNT(*) AS count FROM analytics_events WHERE event_name IN ('page_view', 'view_idea')"
    ).fetchone()["count"]
    conversion = round((int(metrics["paid_orders"] or 0) / max(int(views), 1)) * 100, 1)
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
            COUNT(DISTINCT CASE WHEN orders.status = 'paid' THEN orders.customer_email END) AS paid_customers,
            COUNT(DISTINCT CASE WHEN orders.status = 'paid' THEN orders.id END) AS paid_entitlements,
            COUNT(DISTINCT CASE WHEN orders.status = 'paid' AND activation_codes.used_at IS NOT NULL THEN orders.id END) AS activated_entitlements
        FROM orders
        LEFT JOIN activation_codes ON activation_codes.order_id = orders.id
        """
    ).fetchone()
    active_customer_sessions = connection.execute(
        """
        SELECT COUNT(DISTINCT customer_email) AS count
        FROM customer_sessions
        WHERE revoked_at IS NULL AND expires_at > ?
        """,
        (utc_now(),),
    ).fetchone()["count"]
    trusted_devices = connection.execute(
        """
        SELECT COUNT(*) AS count FROM customer_devices
        WHERE revoked_at IS NULL AND trusted_until > ?
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
        WHERE orders.status = 'paid'
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
        WHERE status = 'paid' AND paid_at >= ?
        GROUP BY substr(paid_at, 1, 10)
        ORDER BY day
        """,
        ((datetime.now(timezone.utc) - timedelta(days=6)).date().isoformat(),),
    ).fetchall()
    traffic_sources = connection.execute(
        """
        SELECT source, COUNT(*) AS count
        FROM analytics_events
        WHERE created_at >= ?
        GROUP BY source ORDER BY count DESC
        """,
        ((datetime.now(timezone.utc) - timedelta(days=29)).isoformat(timespec="seconds"),),
    ).fetchall()
    line_event_count = connection.execute("SELECT COUNT(*) AS count FROM line_events").fetchone()["count"]
    global_price = get_setting_int("idea_price", 199)
    base_url = os.environ.get("BASE_URL", "http://127.0.0.1:5088").strip()
    return jsonify(
        {
            "metrics": {
                "total_orders": int(metrics["total_orders"] or 0),
                "paid_orders": int(metrics["paid_orders"] or 0),
                "pending_orders": int(metrics["pending_orders"] or 0),
                "revenue": int(metrics["revenue"] or 0),
                "views": int(views or 0),
                "conversion": conversion,
            },
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
