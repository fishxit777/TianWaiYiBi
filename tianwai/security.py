import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type
from flask import current_app, jsonify, redirect, request, session, url_for

from .db import get_db, utc_now


ADMIN_COOKIE = "twyb_admin"
LOGIN_WINDOW_MINUTES = 15
LOGIN_FAILURE_LIMIT = 5
BLOCK_MINUTES = 15
ADMIN_SESSION_HOURS = 8
ADMIN_PASSWORD_BYTES = 32
ADMIN_PASSWORD_ENTROPY_BITS = ADMIN_PASSWORD_BYTES * 8
ADMIN_PASSWORD_HASHER = PasswordHasher(
    time_cost=2,
    memory_cost=19 * 1024,
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def env_enabled(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def generate_admin_password():
    """Return a password-manager credential backed by 256 random bits."""
    return secrets.token_urlsafe(ADMIN_PASSWORD_BYTES)


def hash_admin_password(password):
    value = str(password)
    if not value:
        raise ValueError("Admin password must not be empty")
    return ADMIN_PASSWORD_HASHER.hash(value)


def verify_admin_password(password, encoded_hash):
    if not str(encoded_hash).startswith("$argon2id$"):
        return False
    try:
        return bool(ADMIN_PASSWORD_HASHER.verify(str(encoded_hash), str(password)))
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def admin_password_hash_configured():
    return os.environ.get("ADMIN_PASSWORD_HASH", "").strip().startswith("$argon2id$")


def get_client_ip():
    if env_enabled("TRUST_PROXY", False):
        forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if forwarded:
            return forwarded[:64]
    return (request.remote_addr or "unknown")[:64]


def safe_user_agent():
    return request.headers.get("User-Agent", "")[:240]


def log_security_event(event_type, severity="medium", action_taken="logged", detail=""):
    try:
        connection = get_db()
        now = utc_now()
        ip = get_client_ip()
        path = request.path[:240]
        user_agent = safe_user_agent()
        cursor = connection.execute(
            """
            INSERT INTO security_events
                (event_type, severity, ip, path, action_taken, detail, user_agent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event_type)[:80], str(severity)[:20], ip, path,
                str(action_taken)[:80], str(detail)[:500], user_agent, now,
            ),
        )
        security_event_id = cursor.lastrowid
        connection.commit()
    except Exception:
        current_app.logger.exception("Unable to persist security event")
        return
    if str(severity).lower() in {"high", "critical"}:
        try:
            from .notifications import queue_security_alert

            queue_security_alert(
                security_event_id,
                level=str(severity).lower(),
                event_type=str(event_type),
                event_id=f"SE-{security_event_id}",
                action_taken=str(action_taken),
                ip=ip,
                path=path,
                user_agent=user_agent,
                detail=str(detail),
                occurred_at=now,
            )
        except Exception:
            current_app.logger.exception("Unable to queue immediate security alert")


def log_audit(action, target="", detail=""):
    connection = get_db()
    connection.execute(
        "INSERT INTO audit_logs (action, target, detail, ip, created_at) VALUES (?, ?, ?, ?, ?)",
        (str(action)[:100], str(target)[:160], str(detail)[:500], get_client_ip(), utc_now()),
    )
    connection.commit()


def get_public_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def public_csrf_valid():
    expected = session.get("csrf_token", "")
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    return bool(expected and supplied and hmac.compare_digest(str(expected), str(supplied)))


def require_public_csrf():
    if public_csrf_valid():
        return None
    log_security_event("csrf_rejected", "medium", "rejected", "public_csrf_mismatch")
    return jsonify({"error": "安全驗證已過期，請重新整理後再試"}), 403


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def derive_access_token(payment_token):
    secret = str(current_app.config["SECRET_KEY"]).encode("utf-8")
    digest = hmac.new(secret, f"access:{payment_token}".encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def derive_activation_token(order_no):
    """Derive a stable, non-guessable activation-link token for an order."""
    secret = str(current_app.config["SECRET_KEY"]).encode("utf-8")
    digest = hmac.new(secret, f"activation:{order_no}".encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def hash_scoped_token(scope, token):
    """Hash short-lived codes with the app secret and a purpose boundary."""
    secret = str(current_app.config["SECRET_KEY"]).encode("utf-8")
    return hmac.new(
        secret,
        f"{scope}:{token}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _parse_time(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _blocked_row(ip):
    return get_db().execute(
        "SELECT * FROM blocked_ips WHERE ip = ? AND blocked_until > ?",
        (ip, utc_now()),
    ).fetchone()


def is_admin_ip_allowed():
    raw = os.environ.get("ADMIN_ALLOWED_IPS", "").strip()
    required = env_enabled("ADMIN_IP_ALLOWLIST_REQUIRED", False)
    if not raw:
        return not required
    allowed = {item.strip() for item in raw.split(",") if item.strip()}
    return get_client_ip() in allowed


def security_preflight():
    ip = get_client_ip()
    blocked = _blocked_row(ip)
    if blocked:
        get_db().execute(
            "UPDATE blocked_ips SET hit_count = hit_count + 1, updated_at = ? WHERE ip = ?",
            (utc_now(), ip),
        )
        get_db().commit()
        return jsonify({"error": "請求過於頻繁，請稍後再試"}), 429

    target = request.full_path.lower()
    sensitive_markers = (
        "/.env", "/.git", "/phpmyadmin", "/wp-admin", "/wp-login", "/actuator",
        "/server-status", "../", "%2e%2e", "<script", "%3cscript", "union%20select",
    )
    if any(marker in target for marker in sensitive_markers):
        log_security_event("sensitive_path_probe", "high", "rejected", "known_probe_pattern")
        return "", 404

    if request.content_length and request.content_length > current_app.config["MAX_CONTENT_LENGTH"]:
        log_security_event("oversized_request", "medium", "rejected", "content_length_limit")
        return jsonify({"error": "請求內容過大"}), 413
    return None


def register_login_attempt(success):
    connection = get_db()
    now = datetime.now(timezone.utc)
    ip = get_client_ip()
    connection.execute(
        "INSERT INTO admin_login_attempts (ip, success, attempted_at) VALUES (?, ?, ?)",
        (ip, 1 if success else 0, now.isoformat(timespec="seconds")),
    )
    if success:
        connection.execute("DELETE FROM blocked_ips WHERE ip = ?", (ip,))
        connection.commit()
        return 0

    window_start = (now - timedelta(minutes=LOGIN_WINDOW_MINUTES)).isoformat(timespec="seconds")
    row = connection.execute(
        "SELECT COUNT(*) AS count FROM admin_login_attempts WHERE ip = ? AND success = 0 AND attempted_at >= ?",
        (ip, window_start),
    ).fetchone()
    failures = int(row["count"])
    if failures >= LOGIN_FAILURE_LIMIT:
        blocked_until = (now + timedelta(minutes=BLOCK_MINUTES)).isoformat(timespec="seconds")
        connection.execute(
            """
            INSERT INTO blocked_ips (ip, reason, blocked_until, hit_count, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(ip) DO UPDATE SET
                reason = excluded.reason,
                blocked_until = excluded.blocked_until,
                hit_count = blocked_ips.hit_count + 1,
                updated_at = excluded.updated_at
            """,
            (ip, "admin_login_failures", blocked_until, utc_now(), utc_now()),
        )
        connection.commit()
        log_security_event("admin_auth_blocked", "critical", "temporarily_blocked", f"failures={failures}")
    else:
        connection.commit()
        log_security_event("admin_auth_failed", "medium", "logged", f"failures={failures}")
    return failures


def admin_credentials_valid(username, password):
    expected_user = os.environ.get("ADMIN_USERNAME", "")
    expected_hash = os.environ.get("ADMIN_PASSWORD_HASH", "").strip()
    expected_password = os.environ.get("ADMIN_PASSWORD", "")
    if not expected_user or not (expected_hash or expected_password):
        return False
    if expected_hash:
        password_valid = verify_admin_password(password, expected_hash)
    else:
        password_valid = hmac.compare_digest(str(password), expected_password)
    user_valid = hmac.compare_digest(str(username), expected_user)
    return user_valid and password_valid


def create_admin_session(auth_method="password", restricted=False):
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=ADMIN_SESSION_HOURS)
    connection = get_db()
    connection.execute(
        """
        INSERT INTO admin_sessions
            (session_hash, csrf_token, ip, user_agent, created_at, last_seen_at, expires_at,
             auth_method, restricted)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hash_token(raw_token), csrf_token, get_client_ip(), safe_user_agent(),
            now.isoformat(timespec="seconds"), now.isoformat(timespec="seconds"),
            expires.isoformat(timespec="seconds"),
            str(auth_method)[:32], 1 if restricted else 0,
        ),
    )
    connection.commit()
    return raw_token


def current_admin_session():
    raw_token = request.cookies.get(ADMIN_COOKIE, "")
    if not raw_token:
        return None
    connection = get_db()
    row = connection.execute(
        """
        SELECT * FROM admin_sessions
        WHERE session_hash = ? AND revoked_at IS NULL AND expires_at > ?
        LIMIT 1
        """,
        (hash_token(raw_token), utc_now()),
    ).fetchone()
    if row is None:
        return None
    if env_enabled("ADMIN_SESSION_BIND_IP", True) and row["ip"] != get_client_ip():
        connection.execute(
            "UPDATE admin_sessions SET revoked_at = ?, revoked_reason = ? WHERE id = ?",
            (utc_now(), "ip_mismatch", row["id"]),
        )
        connection.commit()
        log_security_event("admin_session_ip_mismatch", "critical", "session_revoked", "ip_mismatch")
        return None
    connection.execute("UPDATE admin_sessions SET last_seen_at = ? WHERE id = ?", (utc_now(), row["id"]))
    connection.commit()
    return row


def admin_csrf_valid(admin_session=None):
    admin_session = admin_session or current_admin_session()
    if admin_session is None:
        return False
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    return bool(supplied and hmac.compare_digest(str(admin_session["csrf_token"]), str(supplied)))


def revoke_admin_session(reason="logout"):
    raw_token = request.cookies.get(ADMIN_COOKIE, "")
    if not raw_token:
        return
    connection = get_db()
    connection.execute(
        "UPDATE admin_sessions SET revoked_at = ?, revoked_reason = ? WHERE session_hash = ?",
        (utc_now(), reason, hash_token(raw_token)),
    )
    connection.commit()


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_admin_ip_allowed():
            log_security_event("admin_ip_denied", "high", "rejected", "allowlist_mismatch")
            if request.path.startswith("/admin/api/"):
                return jsonify({"error": "未授權"}), 403
            return "", 404
        admin_session = current_admin_session()
        if admin_session is None:
            if request.path.startswith("/admin/api/"):
                return jsonify({"error": "請先登入"}), 401
            return redirect(url_for("admin.login_page"))
        if bool(admin_session["restricted"]):
            allowed = (
                request.path == "/admin/passkeys/setup"
                or request.path == "/admin/logout"
                or request.path.startswith("/admin/api/passkeys/")
            )
            if not allowed:
                if request.path.startswith("/admin/api/"):
                    return jsonify({"error": "請先完成兩把 Passkey 的重新登記"}), 403
                return redirect(url_for("admin.passkey_setup"))
        return view(*args, **kwargs)

    return wrapped


def admin_mutation_guard():
    admin_session = current_admin_session()
    if admin_session is None:
        return jsonify({"error": "請先登入"}), 401
    if not admin_csrf_valid(admin_session):
        log_security_event("admin_csrf_rejected", "high", "rejected", "admin_csrf_mismatch")
        return jsonify({"error": "安全驗證失敗"}), 403
    return None


def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault("Origin-Agent-Cluster", "?1")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "font-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'self'; "
        "base-uri 'self'; form-action 'self'",
    )
    if request.path.startswith("/pay/ecpay/"):
        response.headers["Content-Security-Policy"] = response.headers["Content-Security-Policy"].replace(
            "form-action 'self'",
            "form-action 'self' https://payment-stage.ecpay.com.tw https://payment.ecpay.com.tw",
        )
    sensitive_customer_paths = (
        "/activate/",
        "/payment/status/",
        "/customer/",
        "/library/",
        "/orders/",
    )
    if request.path.startswith(sensitive_customer_paths):
        response.headers["Cache-Control"] = "no-store, no-cache, max-age=0, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = response.headers["Content-Security-Policy"].replace(
            "frame-ancestors 'self'", "frame-ancestors 'none'"
        )
    if request.path.startswith("/admin"):
        response.headers["Cache-Control"] = "no-store, no-cache, max-age=0, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = response.headers["Content-Security-Policy"].replace(
            "frame-ancestors 'self'", "frame-ancestors 'none'"
        )
    if request.path.startswith("/admin/recovery") or request.path.startswith("/ideas/"):
        policy = response.headers["Content-Security-Policy"]
        policy = policy.replace("script-src 'self'", "script-src 'self' https://challenges.cloudflare.com")
        policy = policy.replace("connect-src 'self'", "connect-src 'self' https://challenges.cloudflare.com")
        policy = policy.replace("object-src 'none'", "frame-src https://challenges.cloudflare.com; object-src 'none'")
        response.headers["Content-Security-Policy"] = policy
    if request.is_secure or request.headers.get("X-Forwarded-Proto", "").lower() == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def admin_cookie_secure():
    if current_app.config.get("TESTING"):
        return bool(current_app.config.get("SESSION_COOKIE_SECURE", False))
    return request.is_secure or request.headers.get("X-Forwarded-Proto", "").lower() == "https"
