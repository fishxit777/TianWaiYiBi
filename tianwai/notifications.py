import json
import os
import urllib.error
import urllib.request

from flask import current_app

from .db import get_db, utc_now


def _masked_recipient(value):
    if not value:
        return "not-configured"
    return f"LINE:{value[-4:].rjust(len(value), '*')}"


def send_line_push(message):
    """Send a private text alert to the TianWai admin; never include customer PII."""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    admin_user_id = os.environ.get("LINE_ADMIN_USER_ID", "").strip()
    if not token or not admin_user_id:
        return "skipped", "line_admin_not_configured"

    payload = json.dumps(
        {"to": admin_user_id, "messages": [{"type": "text", "text": str(message)[:1800]}]},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/push",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            if 200 <= int(response.status) < 300:
                return "sent", ""
            return "failed", f"http_{response.status}"
    except urllib.error.HTTPError as exc:
        return "failed", f"http_{exc.code}"
    except (urllib.error.URLError, TimeoutError):
        return "failed", "network_error"


def queue_private_alert(incident_id, incident_no, level, event_type, customer_public_id):
    """Persist then attempt a privacy-minimized LINE alert. Failures stay retryable."""
    connection = get_db()
    dedupe_key = f"line-risk:{incident_no}"
    admin_user_id = os.environ.get("LINE_ADMIN_USER_ID", "").strip()
    message = (
        f"天外一筆安全警示｜{level.upper()}\n"
        f"事件：{event_type}\n"
        f"案件：{incident_no}\n"
        f"客戶代碼：{customer_public_id or 'unknown'}\n"
        "完整資訊請登入管理後台查看。"
    )
    payload = json.dumps({"message": message}, ensure_ascii=False, separators=(",", ":"))
    now = utc_now()
    connection.execute(
        """
        INSERT OR IGNORE INTO notification_queue
            (dedupe_key, incident_id, channel, recipient_masked, payload_json,
             status, attempts, last_error, created_at, updated_at)
        VALUES (?, ?, 'line', ?, ?, 'pending', 0, '', ?, ?)
        """,
        (dedupe_key, incident_id, _masked_recipient(admin_user_id), payload, now, now),
    )
    connection.commit()

    row = connection.execute(
        "SELECT * FROM notification_queue WHERE dedupe_key = ?", (dedupe_key,)
    ).fetchone()
    if row is None or row["status"] == "sent":
        return
    status, error = send_line_push(message)
    try:
        connection.execute(
            """
            UPDATE notification_queue
            SET status = ?, attempts = attempts + 1, last_error = ?, updated_at = ?,
                sent_at = CASE WHEN ? = 'sent' THEN ? ELSE sent_at END
            WHERE id = ?
            """,
            (status, error[:120], utc_now(), status, utc_now(), row["id"]),
        )
        connection.commit()
    except Exception:
        current_app.logger.exception("Unable to update LINE security notification status")


def retry_private_alerts(limit=10):
    connection = get_db()
    rows = connection.execute(
        """
        SELECT * FROM notification_queue
        WHERE channel = 'line' AND status IN ('pending', 'failed', 'skipped')
        ORDER BY id ASC LIMIT ?
        """,
        (max(1, min(int(limit), 50)),),
    ).fetchall()
    sent = 0
    for row in rows:
        try:
            message = json.loads(row["payload_json"])["message"]
            status, error = send_line_push(message)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            status, error = "failed", "invalid_queue_payload"
        now = utc_now()
        connection.execute(
            """
            UPDATE notification_queue
            SET status = ?, attempts = attempts + 1, last_error = ?, updated_at = ?,
                sent_at = CASE WHEN ? = 'sent' THEN ? ELSE sent_at END
            WHERE id = ?
            """,
            (status, error[:120], now, status, now, row["id"]),
        )
        if status == "sent":
            sent += 1
    connection.commit()
    return {"processed": len(rows), "sent": sent}
