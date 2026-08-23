import os
import smtplib
from email.message import EmailMessage

from flask import current_app, has_request_context, request

from .db import get_db, utc_now


def _enabled(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def development_delivery_enabled():
    return bool(current_app.config.get("TESTING")) or _enabled("ENABLE_DEV_TOOLS", False)


def email_delivery_ready():
    if development_delivery_enabled():
        return True
    host = os.environ.get("SMTP_HOST", "").strip()
    sender = os.environ.get("MAIL_FROM", "").strip()
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    security = os.environ.get("SMTP_SECURITY", "starttls").strip().lower()
    return bool(
        host
        and sender
        and security in {"starttls", "ssl"}
        and (not username or password)
    )


def _mask_email(address):
    local, separator, domain = str(address).partition("@")
    if not separator:
        return "***"
    return f"{local[:1]}***@{domain}"


def _record_event(order_id, kind, recipient, status, error_code=""):
    connection = get_db()
    cursor = connection.execute(
        """
        INSERT INTO email_events
            (order_id, email_kind, recipient_masked, status, error_code, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            order_id,
            str(kind)[:40],
            _mask_email(recipient)[:254],
            str(status)[:30],
            str(error_code)[:80],
            utc_now(),
        ),
    )
    connection.commit()
    return cursor.lastrowid


def _queue_delivery_failure(email_event_id, kind, error_code):
    if str(kind).startswith("admin_"):
        return
    try:
        from .notifications import queue_security_alert
        from .security import get_client_ip, safe_user_agent

        queue_security_alert(
            f"mail-{email_event_id}",
            level="high",
            event_type="transactional_email_delivery_failed",
            event_id=f"MAIL-{email_event_id}",
            action_taken="delivery_failed_queued_for_review",
            ip=get_client_ip() if has_request_context() else "system",
            path=request.path if has_request_context() else "system",
            user_agent=safe_user_agent() if has_request_context() else "system",
            detail=f"email_kind={str(kind)[:40]}; error={str(error_code)[:80]}",
            occurred_at=utc_now(),
        )
    except Exception:
        current_app.logger.exception("Unable to queue transactional email failure alert")


def send_email(recipient, subject, text_body, kind, order_id=None):
    """Send a transactional email without persisting its secret-bearing body."""
    if development_delivery_enabled():
        current_app.extensions.setdefault("mail_outbox", []).append(
            {
                "to": recipient,
                "subject": subject,
                "text": text_body,
                "kind": kind,
                "order_id": order_id,
            }
        )
        _record_event(order_id, kind, recipient, "development")
        return "development"

    if not email_delivery_ready():
        event_id = _record_event(order_id, kind, recipient, "failed", "smtp_not_configured")
        _queue_delivery_failure(event_id, kind, "smtp_not_configured")
        return "failed"

    message = EmailMessage()
    message["From"] = os.environ["MAIL_FROM"].strip()
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(text_body)

    host = os.environ["SMTP_HOST"].strip()
    port = int(os.environ.get("SMTP_PORT", "587"))
    security = os.environ.get("SMTP_SECURITY", "starttls").strip().lower()
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")

    try:
        smtp_class = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
        with smtp_class(host, port, timeout=15) as server:
            if security == "starttls":
                server.starttls()
            if username:
                server.login(username, password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        current_app.logger.exception("Transactional email delivery failed")
        error_code = type(error).__name__
        event_id = _record_event(order_id, kind, recipient, "failed", error_code)
        _queue_delivery_failure(event_id, kind, error_code)
        return "failed"

    _record_event(order_id, kind, recipient, "sent")
    return "sent"
