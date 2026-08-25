import json
import os
import smtplib
import urllib.error
import urllib.request
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


def _email_provider():
    provider = os.environ.get("EMAIL_PROVIDER", "auto").strip().lower()
    if provider == "auto":
        return "brevo" if os.environ.get("BREVO_API_KEY", "").strip() else "smtp"
    return provider


def _brevo_sender_id():
    value = os.environ.get("BREVO_SENDER_ID", "").strip()
    if not value:
        return None
    try:
        sender_id = int(value)
    except ValueError:
        return None
    return sender_id if sender_id > 0 else None


def email_delivery_ready():
    if development_delivery_enabled():
        return True
    sender = os.environ.get("MAIL_FROM", "").strip()
    provider = _email_provider()
    if provider == "brevo":
        sender_id_configured = bool(os.environ.get("BREVO_SENDER_ID", "").strip())
        sender_ready = (
            _brevo_sender_id() is not None if sender_id_configured else bool(sender)
        )
        return bool(sender_ready and os.environ.get("BREVO_API_KEY", "").strip())
    if provider != "smtp":
        return False
    host = os.environ.get("SMTP_HOST", "").strip()
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


def _record_failure(order_id, kind, recipient, error_code):
    event_id = _record_event(order_id, kind, recipient, "failed", error_code)
    _queue_delivery_failure(event_id, kind, error_code)
    return "failed"


def _send_brevo(recipient, subject, text_body):
    configured_sender_id = os.environ.get("BREVO_SENDER_ID", "").strip()
    if configured_sender_id:
        sender_id = _brevo_sender_id()
        if sender_id is None:
            raise ValueError("Invalid Brevo sender ID")
        sender = {"id": sender_id}
    else:
        sender = {
            "name": os.environ.get("MAIL_FROM_NAME", "天外一筆工作室").strip()
            or "天外一筆工作室",
            "email": os.environ["MAIL_FROM"].strip(),
        }
    payload = json.dumps(
        {
            "sender": sender,
            "to": [{"email": recipient}],
            "subject": subject,
            "textContent": text_body,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request_data = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=payload,
        headers={
            "accept": "application/json",
            "api-key": os.environ["BREVO_API_KEY"].strip(),
            "content-type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(request_data, timeout=15) as response:
        status = int(getattr(response, "status", 0))
        if status < 200 or status >= 300:
            raise urllib.error.HTTPError(
                request_data.full_url,
                status,
                "Unexpected transactional email API response",
                response.headers,
                None,
            )


def _send_smtp(recipient, subject, text_body):
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

    smtp_class = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
    with smtp_class(host, port, timeout=15) as server:
        if security == "starttls":
            server.starttls()
        if username:
            server.login(username, password)
        server.send_message(message)


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
        return _record_failure(order_id, kind, recipient, "email_provider_not_configured")

    provider = _email_provider()
    try:
        if provider == "brevo":
            _send_brevo(recipient, subject, text_body)
        else:
            _send_smtp(recipient, subject, text_body)
    except urllib.error.HTTPError as error:
        error_code = f"brevo_http_{int(error.code)}"
        current_app.logger.error(
            "Transactional email API delivery failed with HTTP status %s",
            int(error.code),
        )
        return _record_failure(order_id, kind, recipient, error_code)
    except (OSError, smtplib.SMTPException, urllib.error.URLError, ValueError) as error:
        error_code = type(error).__name__
        current_app.logger.error(
            "Transactional email delivery failed via %s: %s",
            provider,
            error_code,
        )
        return _record_failure(order_id, kind, recipient, error_code)

    _record_event(order_id, kind, recipient, "sent")
    return "sent"
