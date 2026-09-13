import json
import hashlib
import ipaddress
import os
import re
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from flask import current_app

from .analytics import trusted_analytics_start
from .db import get_db, utc_now


TAIPEI = timezone(timedelta(hours=8), name="Asia/Taipei")
TOP_IDEA_MINIMUM_SESSIONS = 10
DAILY_SUMMARY_RETRY_HOURS = 24
PRIVATE_ALERT_RETRY_DAYS = 7
MAX_DELIVERY_ATTEMPTS = 5
CLAIM_LEASE_SECONDS = 60
ALERT_WINDOW_SECONDS = 300
ALERT_WINDOW_LIMIT = 10
ALERT_HOURLY_LIMIT = 60
PAYLOAD_VERSION = 32
SLOTS = {
    "morning": "晨間 08:00",
    "noon": "午間 12:00",
    "evening": "晚間 20:00",
}
SEVERITY_LABELS = {
    "low": "一般",
    "medium": "注意",
    "high": "高風險",
    "critical": "重大",
}
EVENT_LABELS = {
    "activation_code_rejected": "開通碼連續輸入失敗",
    "customer_login_code_rejected": "客戶登入碼連續輸入失敗",
    "revoked_session_replay": "已撤銷工作階段遭重複使用",
    "payment_signature_rejected": "付款回呼簽章驗證失敗",
    "payment_signature_mismatch": "付款回呼簽章驗證失敗",
    "payment_order_not_found": "付款回呼找不到對應訂單",
    "payment_amount_mismatch": "付款金額與訂單不一致",
    "ecpay_signature_mismatch": "綠界付款回呼簽章驗證失敗",
    "ecpay_result_signature_mismatch": "綠界付款結果簽章驗證失敗",
    "line_signature_mismatch": "LINE Webhook 簽章驗證失敗",
    "transactional_email_delivery_failed": "客戶交易郵件寄送失敗",
    "admin_auth_blocked": "管理後台登入來源遭暫時封鎖",
    "admin_session_ip_mismatch": "管理工作階段來源 IP 不一致",
    "admin_ip_denied": "非允許來源嘗試進入管理後台",
    "admin_csrf_rejected": "管理操作安全驗證遭拒絕",
    "admin_login_csrf_rejected": "管理登入安全驗證遭拒絕",
    "admin_emergency_recovery": "管理員緊急復原已啟動",
    "admin_recovery_completed": "管理員緊急復原已完成",
    "sensitive_path_probe": "敏感檔案或已知弱點掃描",
    "csrf_rejected": "網頁安全驗證遭拒絕",
}


def _mask_line(value):
    if not value:
        return "not-configured"
    return "LINE:private-admin"


def mask_ip(value):
    value = str(value or "unknown").strip()
    if value in {"unknown", "system"}:
        return value
    if "%" in value:
        return "masked"
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return "masked"
    if address.version == 4:
        return ".".join(str(address).split(".")[:3] + ["*"])
    return ":".join(address.exploded.split(":")[:3]) + ":*"


def _taipei_now():
    return datetime.now(timezone.utc).astimezone(TAIPEI)


def _format_taipei(value=None):
    moment = value or _taipei_now()
    if isinstance(moment, str):
        try:
            moment = datetime.fromisoformat(moment)
        except ValueError:
            moment = _taipei_now()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M:%S")


def line_admin_delivery_ready():
    return bool(
        os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
        and re.fullmatch(r"U[0-9a-fA-F]{32}", os.environ.get("LINE_ADMIN_USER_ID", "").strip())
    )


def _recipient_fingerprint():
    """Bind retries to the original channel and private recipient without storing them."""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    recipient = os.environ.get("LINE_ADMIN_USER_ID", "").strip()
    return hashlib.sha256(f"tianwai-admin-line\0{token}\0{recipient}".encode()).hexdigest()


def send_line_push(message, *, retry_key=None):
    """Send a private text alert to the TianWai admin; never include customer PII."""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    admin_user_id = os.environ.get("LINE_ADMIN_USER_ID", "").strip()
    if not line_admin_delivery_ready():
        return "skipped", "line_admin_not_configured"
    try:
        retry_key = str(uuid.UUID(str(retry_key)))
    except (ValueError, TypeError, AttributeError):
        return "failed", "invalid_provider_retry_key"

    payload = json.dumps(
        {"to": admin_user_id, "messages": [{"type": "text", "text": str(message)[:1800]}]},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/push",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "X-Line-Retry-Key": retry_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            if 200 <= int(response.status) < 300:
                return "sent", ""
            return "failed", f"http_{response.status}"
    except urllib.error.HTTPError as exc:
        # This means API acceptance, not a read receipt or guaranteed recipient delivery.
        if exc.code == 409 and exc.headers and exc.headers.get("x-line-accepted-request-id"):
            return "sent", ""
        return "failed", f"http_{exc.code}"
    except (urllib.error.URLError, TimeoutError):
        return "failed", "network_error"


def _deliver(row):
    try:
        payload = json.loads(row["payload_json"])
        if row["channel"] == "line":
            if payload.get("version") != PAYLOAD_VERSION:
                return "skipped", "legacy_payload_disabled"
            first_attempt = datetime.fromisoformat(row["first_attempt_at"])
            if datetime.now(timezone.utc) - first_attempt >= timedelta(hours=23):
                return "skipped", "provider_retry_window_expired"
            if row["recipient_fingerprint"] != _recipient_fingerprint():
                return "skipped", "recipient_configuration_changed"
            return send_line_push(payload["message"], retry_key=row["provider_retry_key"])
        if row["channel"] == "email":
            return "skipped", "legacy_admin_email_delivery_disabled"
        return "failed", "unsupported_channel"
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return "failed", "invalid_queue_payload"


def _persist_delivery(row_id, status, error, claim_token):
    connection = get_db()
    now = utc_now()
    row = connection.execute(
        "SELECT attempts FROM notification_queue WHERE id = ? AND claim_token = ?",
        (row_id, claim_token),
    ).fetchone()
    if row is None:
        return
    # Only bounded internal error codes are stored, never exceptions/provider bodies.
    error = str(error) if re.fullmatch(r"[a-z_0-9]{0,60}", str(error)) else "delivery_error"
    attempts = int(row["attempts"])
    retryable = status == "failed" and (error == "network_error" or bool(re.fullmatch(r"http_5\d\d", error)))
    if attempts >= MAX_DELIVERY_ATTEMPTS and status != "sent":
        error, retryable = "retry_exhausted", False
    next_attempt = (
        (datetime.now(timezone.utc) + timedelta(seconds=60 * (2 ** (attempts - 1)))).isoformat(timespec="seconds")
        if retryable else ""
    )
    connection.execute(
        """
        UPDATE notification_queue
        SET status = ?, last_error = ?, updated_at = ?,
            sent_at = CASE WHEN ? = 'sent' THEN ? ELSE sent_at END,
            claim_token = '', claimed_until = '', next_attempt_at = ?, retryable = ?
        WHERE id = ? AND claim_token = ?
        """,
        (status, error, now, status, now, next_attempt, int(retryable), row_id, claim_token),
    )
    connection.commit()


def _claim_delivery(row):
    """One transactional CAS lease + quota reservation, valid across app workers."""
    if not line_admin_delivery_ready():
        return None
    connection = get_db()
    moment = datetime.now(timezone.utc)
    now = moment.isoformat(timespec="seconds")
    token = str(uuid.uuid4())
    lease = (moment + timedelta(seconds=CLAIM_LEASE_SECONDS)).isoformat(timespec="seconds")
    cursor = connection.execute(
        """UPDATE notification_queue
           SET claim_token = ?, claimed_until = ?, attempts = attempts + 1,
               first_attempt_at = CASE WHEN first_attempt_at = '' THEN ? ELSE first_attempt_at END,
               provider_retry_key = CASE WHEN provider_retry_key = '' THEN ? ELSE provider_retry_key END,
               recipient_fingerprint = CASE WHEN recipient_fingerprint = '' THEN ? ELSE recipient_fingerprint END
           WHERE id = ? AND channel = 'line' AND status IN ('pending', 'failed', 'skipped')
             AND retryable = 1 AND attempts < ? AND next_attempt_at <= ? AND claimed_until <= ?""",
        (token, lease, now, str(uuid.uuid4()), _recipient_fingerprint(), row["id"],
         MAX_DELIVERY_ATTEMPTS, now, now),
    )
    if cursor.rowcount != 1:
        connection.rollback()
        return None
    # A storm cannot consume the summary's separate delivery budget.
    summary = ":daily-summary:" in row["dedupe_key"]
    group = "summary" if summary else "alert"
    for seconds, cap in ((ALERT_WINDOW_SECONDS, 3 if summary else ALERT_WINDOW_LIMIT),
                         (3600, 6 if summary else ALERT_HOURLY_LIMIT)):
        bucket = int(moment.timestamp()) // seconds
        bucket_key = f"tianwai:line:{group}:{seconds}:{bucket}"
        expires = datetime.fromtimestamp((bucket + 1) * seconds, timezone.utc).isoformat(timespec="seconds")
        connection.execute(
            "INSERT OR IGNORE INTO notification_delivery_windows (bucket_key, attempts, expires_at) VALUES (?, 0, ?)",
            (bucket_key, expires),
        )
        reserved = connection.execute(
            "UPDATE notification_delivery_windows SET attempts = attempts + 1 WHERE bucket_key = ? AND attempts < ?",
            (bucket_key, cap),
        )
        if reserved.rowcount != 1:
            connection.rollback()
            connection.execute(
                "UPDATE notification_queue SET next_attempt_at = ?, last_error = 'rate_deferred' "
                "WHERE id = ? AND claimed_until <= ? AND status <> 'sent' AND retryable = 1",
                (expires, row["id"], now),
            )
            connection.commit()
            return None
    connection.execute("DELETE FROM notification_delivery_windows WHERE expires_at < ?", (now,))
    connection.commit()
    return connection.execute("SELECT * FROM notification_queue WHERE id = ? AND claim_token = ?", (row["id"], token)).fetchone()


def _attempt_delivery(row):
    claimed = _claim_delivery(row)
    if claimed is None:
        return None
    try:
        status, error = _deliver(claimed)
    except Exception:
        # Keep customer/security actions available; no raw provider exception logging.
        status, error = "failed", "delivery_error"
    _persist_delivery(row["id"], status, error, claimed["claim_token"])
    return status


def queue_admin_messages(
    dedupe_base,
    *,
    line_message,
    incident_id=None,
):
    """Queue and deliver one privacy-minimized admin-only LINE message."""
    connection = get_db()
    now = utc_now()
    channel_payloads = {
        "line": (
            _mask_line(os.environ.get("LINE_ADMIN_USER_ID", "").strip()),
            {"version": PAYLOAD_VERSION, "message": str(line_message)[:1800]},
        ),
    }
    result = {"queued": 0, "deduplicated": 0, "channels": {}}
    for channel, (recipient_masked, payload) in channel_payloads.items():
        dedupe_key = f"{channel}:{str(dedupe_base)[:180]}"
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO notification_queue
                (dedupe_key, incident_id, channel, recipient_masked, payload_json,
                 status, attempts, last_error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'pending', 0, '', ?, ?)
            """,
            (
                dedupe_key,
                incident_id,
                channel,
                recipient_masked,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                now,
                now,
            ),
        )
        connection.commit()
        inserted = cursor.rowcount == 1
        result["queued" if inserted else "deduplicated"] += 1
        row = connection.execute(
            "SELECT * FROM notification_queue WHERE dedupe_key = ?", (dedupe_key,)
        ).fetchone()
        if row is None:
            result["channels"][channel] = "failed"
            continue
        if row["status"] == "sent":
            result["channels"][channel] = row["status"]
            continue
        status = _attempt_delivery(row)
        result["channels"][channel] = status or ("skipped" if not line_admin_delivery_ready() else row["status"])
    return result


def _event_messages(
    *,
    level,
    event_type,
    event_id,
    incident_no="",
    customer_public_id="unknown",
    risk_score=None,
    action_taken="logged",
    ip="unknown",
    path="",
    user_agent="",
    detail="",
    occurred_at=None,
):
    level_text = SEVERITY_LABELS.get(str(level), "注意")
    event_text = EVENT_LABELS.get(str(event_type), "未分類高風險事件")
    safe_type = str(event_type) if str(event_type) in EVENT_LABELS else "unclassified"
    safe_event = str(event_id) if re.fullmatch(r"(?:AE-[A-F0-9]{16}|(?:SE|MAIL)-[0-9]{1,12})", str(event_id)) else "請於後台查核"
    safe_incident = str(incident_no) if re.fullmatch(r"RI-[A-F0-9]{12}", str(incident_no)) else "請於後台查核"
    safe_score = risk_score if isinstance(risk_score, int) and 0 <= risk_score <= 100 else "未評分"
    safe_actions = {"logged": "已記錄", "rejected": "已拒絕", "blocked": "已封鎖", "session_revoked": "已撤銷工作階段"}
    occurred = _format_taipei(occurred_at)
    recommendation = (
        "立即登入後台檢查案件、相關存取紀錄與付款狀態；確認無誤前不要手動解除限制。"
        if level in {"high", "critical"}
        else "請於本日內登入後台複核事件與關聯紀錄。"
    )
    details = [
        f"嚴重度：{level_text}",
        f"事件：{event_text}（{safe_type}）",
        f"時間：{occurred}（台北）",
        f"事件編號：{safe_event}",
        f"案件編號：{safe_incident}",
        f"風險分數：{safe_score}",
        f"來源 IP：{mask_ip(ip)}",
        f"系統動作：{safe_actions.get(str(action_taken), '已記錄，請於後台查核')}",
    ]
    details.extend(
        [
            f"建議處置：{recommendation}",
            "管理後台：請從天外一筆官網進入，不經由事件提供的連結。",
            "隱私提醒：通知不含客戶／訂單代碼、原始路徑、自由文字、付費內容或憑證。",
        ]
    )
    line_details = ["天外一筆｜即時異常告警"] + details
    return "\n".join(line_details)[:1800]


def queue_private_alert(
    incident_id,
    incident_no,
    level,
    event_type,
    customer_public_id,
    *,
    event_id="",
    risk_score=None,
    action_taken="logged",
    ip="unknown",
    path="",
    user_agent="",
    detail="",
    occurred_at=None,
):
    if level not in {"high", "critical"}:
        return {"queued": 0, "deduplicated": 0, "channels": {}}
    line = _event_messages(
        level=level,
        event_type=event_type,
        event_id=event_id,
        incident_no=incident_no,
        customer_public_id=customer_public_id,
        risk_score=risk_score,
        action_taken=action_taken,
        ip=ip,
        path=path,
        user_agent=user_agent,
        detail=detail,
        occurred_at=occurred_at,
    )
    return queue_admin_messages(
        f"risk:{incident_no}",
        line_message=line,
        incident_id=incident_id,
    )


def queue_security_alert(security_event_id, **context):
    if context.get("level") not in {"high", "critical"}:
        return {"queued": 0, "deduplicated": 0, "channels": {}}
    line = _event_messages(**context)
    return queue_admin_messages(
        f"security:{security_event_id}",
        line_message=line,
    )


def _daily_metrics():
    connection = get_db()
    now_local = _taipei_now()
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_local.astimezone(timezone.utc).isoformat(timespec="seconds")
    now_utc = now_local.astimezone(timezone.utc).isoformat(timespec="seconds")
    trusted_start_utc = trusted_analytics_start(start_utc)

    orders = connection.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) AS paid,
               SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
               SUM(CASE WHEN status IN ('cancelled', 'refunded') THEN 1 ELSE 0 END) AS reversed,
               COALESCE(SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END), 0) AS revenue
        FROM orders
        WHERE purpose = 'sale' AND created_at >= ? AND created_at <= ?
        """,
        (start_utc, now_utc),
    ).fetchone()
    access = connection.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM orders WHERE status = 'paid' AND purpose = 'sale') AS entitlements,
          (SELECT COUNT(DISTINCT activation_codes.order_id)
             FROM activation_codes JOIN orders ON orders.id = activation_codes.order_id
            WHERE activation_codes.used_at IS NOT NULL AND orders.purpose = 'sale') AS activated,
          (SELECT COUNT(*) FROM customer_sessions AS sessions
            WHERE revoked_at IS NULL AND expires_at > ?
              AND EXISTS (SELECT 1 FROM orders WHERE orders.customer_id = sessions.customer_id
                            AND orders.status = 'paid' AND orders.purpose = 'sale')) AS sessions,
          (SELECT COUNT(*) FROM customer_devices AS devices
            WHERE revoked_at IS NULL AND trusted_until > ?
              AND EXISTS (SELECT 1 FROM orders WHERE orders.customer_id = devices.customer_id
                            AND orders.status = 'paid' AND orders.purpose = 'sale')) AS devices
        """,
        (now_utc, now_utc),
    ).fetchone()
    traffic = connection.execute(
        """
        SELECT
          COUNT(DISTINCT CASE WHEN created_at >= ? AND is_automated = 0
                                AND source <> 'admin-preview' THEN session_id END) AS public_sessions,
          COUNT(DISTINCT CASE WHEN created_at >= ? AND is_automated = 0
                                AND source <> 'admin-preview' AND event_name = 'page_view'
                              THEN session_id END) AS homepage,
          COUNT(DISTINCT CASE WHEN created_at >= ? AND is_automated = 0
                                AND source <> 'admin-preview' AND event_name = 'view_idea'
                              THEN session_id END) AS idea_sessions,
          COUNT(DISTINCT CASE WHEN created_at >= ? AND is_automated = 0
                                AND source <> 'admin-preview'
                                AND source IN ('search', 'social', 'referral', 'line', 'email')
                              THEN session_id END) AS attributable_sessions,
          COUNT(DISTINCT CASE WHEN created_at >= ? AND is_automated = 0
                                AND source <> 'admin-preview'
                                AND source NOT IN ('search', 'social', 'referral', 'line', 'email')
                              THEN session_id END) AS unattributed_sessions,
          COUNT(DISTINCT CASE WHEN created_at >= ? AND source = 'admin-preview'
                              THEN session_id END) AS admin_preview_sessions,
          COUNT(DISTINCT CASE WHEN created_at >= ? AND is_automated = 1
                              THEN session_id END) AS automated_sessions,
          COUNT(DISTINCT CASE WHEN created_at < ? THEN session_id END) AS legacy_sessions
        FROM analytics_events
        WHERE event_name IN ('page_view', 'view_idea')
          AND session_id IS NOT NULL AND session_id <> ''
          AND created_at >= ? AND created_at <= ?
        """,
        (
            trusted_start_utc,
            trusted_start_utc,
            trusted_start_utc,
            trusted_start_utc,
            trusted_start_utc,
            trusted_start_utc,
            trusted_start_utc,
            trusted_start_utc,
            start_utc,
            now_utc,
        ),
    ).fetchone()
    top_idea = connection.execute(
        """
        SELECT COUNT(DISTINCT analytics_events.session_id) AS count
        FROM analytics_events JOIN ideas ON ideas.id = analytics_events.idea_id
        WHERE analytics_events.event_name = 'view_idea'
          AND analytics_events.is_automated = 0
          AND analytics_events.source <> 'admin-preview'
          AND analytics_events.session_id IS NOT NULL
          AND analytics_events.session_id <> ''
          AND analytics_events.created_at >= ? AND analytics_events.created_at <= ?
        GROUP BY ideas.id ORDER BY count DESC, ideas.id LIMIT 1
        """,
        (trusted_start_utc, now_utc),
    ).fetchone()
    risk = connection.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM risk_incidents WHERE status IN ('open', 'reviewing')) AS open_incidents,
          (SELECT COUNT(*) FROM access_events WHERE severity IN ('high', 'critical') AND created_at >= ?) AS high_access,
          (SELECT COUNT(*) FROM security_events WHERE severity IN ('high', 'critical') AND created_at >= ?) AS high_security,
          (SELECT COUNT(*) FROM blocked_ips WHERE blocked_until > ?) AS blocked_ips,
          (SELECT COUNT(*) FROM notification_queue WHERE channel = 'line' AND status = 'failed' AND created_at >= ?) AS notification_failures_today,
          (SELECT COUNT(*) FROM notification_queue WHERE channel = 'line' AND status = 'skipped' AND created_at >= ?) AS notification_skipped_today,
          (SELECT COUNT(*) FROM notification_queue WHERE status IN ('failed', 'skipped') AND created_at < ?) AS notification_history,
          (SELECT COUNT(*) FROM email_events WHERE status = 'failed' AND created_at >= ?) AS email_failures
        """,
        (start_utc, start_utc, now_utc, start_utc, start_utc, start_utc, start_utc),
    ).fetchone()
    from .mailer import email_delivery_ready
    from .payments import payment_checkout_status
    from .risk import verify_access_event_chain

    checkout = payment_checkout_status()
    base_url = os.environ.get("BASE_URL", "http://127.0.0.1:5088").strip()
    line_token_ready = bool(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip())
    line_admin_ready = line_admin_delivery_ready()
    transactional_email_ready = email_delivery_ready()
    chain = verify_access_event_chain()
    return {
        "date": now_local.date().isoformat(),
        "generated": _format_taipei(now_local),
        "period": f"{start_local.strftime('%Y-%m-%d %H:%M')}～{now_local.strftime('%H:%M')}（台北）",
        "orders": {key: int(orders[key] or 0) for key in ("total", "paid", "pending", "reversed", "revenue")},
        "access": {
            "entitlements": int(access["entitlements"] or 0),
            "activated": int(access["activated"] or 0),
            "pending": max(int(access["entitlements"] or 0) - int(access["activated"] or 0), 0),
            "sessions": int(access["sessions"] or 0),
            "devices": int(access["devices"] or 0),
        },
        "traffic": {
            "visitors": int(traffic["public_sessions"] or 0),
            "public_sessions": int(traffic["public_sessions"] or 0),
            "homepage": int(traffic["homepage"] or 0),
            "idea_visitors": int(traffic["idea_sessions"] or 0),
            "attributable_sessions": int(traffic["attributable_sessions"] or 0),
            "unattributed_sessions": int(traffic["unattributed_sessions"] or 0),
            "admin_preview_sessions": int(traffic["admin_preview_sessions"] or 0),
            "automated_sessions": int(traffic["automated_sessions"] or 0),
            "legacy_sessions": int(traffic["legacy_sessions"] or 0),
            "top": (
                f"最高 {top_idea['count']} 個仙策工作階段（品項請於後台查看）"
                if top_idea and int(top_idea["count"] or 0) >= TOP_IDEA_MINIMUM_SESSIONS
                else (
                    f"暫不排名：最高 {top_idea['count']} 個工作階段，"
                    f"未達 {TOP_IDEA_MINIMUM_SESSIONS} 個工作階段門檻"
                    if top_idea
                    else "目前沒有公開仙策詳情工作階段"
                )
            ),
        },
        "risk": {key: int(risk[key] or 0) for key in risk.keys()},
        "integrations": {
            "line_delivery": line_token_ready,
            "line_admin": line_admin_ready,
            "transactional_email": transactional_email_ready,
            "payment_state": checkout.get("state", "misconfigured"),
            "payment_label": checkout["label"],
            "https": base_url.lower().startswith("https://") or current_app.config.get("TESTING", False),
            "chain": bool(chain["valid"]),
            "chain_checked": int(chain["checked"]),
        },
        "admin_url": "請從天外一筆官網進入管理後台",
    }


def build_daily_summary(slot):
    if slot not in SLOTS:
        raise ValueError("invalid_summary_slot")
    data = _daily_metrics()
    orders = data["orders"]
    access = data["access"]
    risk = data["risk"]
    integrations = data["integrations"]
    todo = []
    if risk["open_incidents"]:
        todo.append(f"立即複核 {risk['open_incidents']} 件未結風險案件。")
    if risk["notification_failures_today"]:
        todo.append(f"今日有 {risk['notification_failures_today']} 筆管理通知送達失敗，請檢查近期佇列。")
    if risk["email_failures"]:
        todo.append(f"確認 {risk['email_failures']} 筆今日交易郵件寄送失敗。")
    if access["pending"]:
        todo.append(f"確認 {access['pending']} 份已付款但尚未完成開通的權限。")
    if not integrations["line_delivery"]:
        todo.append("管理員 LINE 推播存取權杖尚未設定。")
    elif not integrations["line_admin"]:
        todo.append("管理員 LINE 推播已連線，但私訊收件人尚未設定。")
    if not integrations["transactional_email"]:
        todo.append("補齊或檢查客戶交易郵件寄送設定。")
    if integrations["payment_state"] == "misconfigured":
        todo.append("金流設定未完成；維持公開收款關閉，完成檢查前不得建立訂單。")
    if not integrations["chain"]:
        todo.append("重大：存取證據鏈驗證失敗，請停止手動變更並立即查核。")
    if not todo:
        todo.append("目前無需立即處理；系統持續監控中。")

    normal = [
        f"今日高／重大存取事件 {risk['high_access']} 件；一般安全事件高／重大 {risk['high_security']} 件。",
        f"證據鏈{'完整' if integrations['chain'] else '異常'}，已驗證 {integrations['chain_checked']} 筆存取事件。",
        f"目前封鎖來源 {risk['blocked_ips']} 個；活躍工作階段 {access['sessions']} 個。",
        (
            f"管理員 LINE 推播{'已就緒' if integrations['line_admin'] else '未就緒'}；"
            f"客戶交易 Email {'已就緒' if integrations['transactional_email'] else '尚未就緒'}。"
        ),
        f"金流：{integrations['payment_label']}；HTTPS：{'正常' if integrations['https'] else '未啟用'}。",
    ]
    if risk["notification_history"]:
        normal.append(
            f"歷史未投遞紀錄 {risk['notification_history']} 筆保留供稽核，已排除於即時待辦且不自動重送。"
        )
    heading = f"天外一筆｜{SLOTS[slot]}管理員營運摘要"
    sections = [
        heading,
        f"統計期間：{data['period']}",
        f"產生時間：{data['generated']}（台北）",
        "",
        "【訂單與營收】",
        f"今日訂單 {orders['total']} 筆｜已付款 {orders['paid']}｜待付款 {orders['pending']}｜取消／退款 {orders['reversed']}",
        (
            f"今日實收 NT$ {orders['revenue']:,}｜公開工作階段 {data['traffic']['public_sessions']}｜"
            f"首頁 {data['traffic']['homepage']}｜仙策詳情 {data['traffic']['idea_visitors']}"
        ),
        (
            f"流量分類：可歸因 {data['traffic']['attributable_sessions']}｜"
            f"未歸因 {data['traffic']['unattributed_sessions']}｜"
            f"管理測試 {data['traffic']['admin_preview_sessions']}｜"
            f"機器 {data['traffic']['automated_sessions']}｜"
            f"舊基準排除 {data['traffic']['legacy_sessions']}"
        ),
        f"熱門仙策：{data['traffic']['top']}",
        "",
        "【開通與存取】",
        f"已付款權限 {access['entitlements']}｜已開通 {access['activated']}｜待開通 {access['pending']}",
        f"活躍工作階段 {access['sessions']}｜可信裝置 {access['devices']}",
        "",
        "【安全與風險】",
        f"未結案件 {risk['open_incidents']}｜今日高／重大存取 {risk['high_access']}｜高／重大安全事件 {risk['high_security']}｜封鎖來源 {risk['blocked_ips']}",
        "",
        "【系統與通知】",
        (
            f"今日管理通知失敗 {risk['notification_failures_today']}｜"
            f"今日略過 {risk['notification_skipped_today']} 筆｜"
            f"歷史稽核存量 {risk['notification_history']}｜"
            f"今日交易郵件失敗 {risk['email_failures']}"
        ),
        (
            f"管理員 LINE 推播 {'就緒' if integrations['line_admin'] else '未就緒'}｜"
            f"交易 Email {'就緒' if integrations['transactional_email'] else '未就緒'}｜"
            f"金流 {integrations['payment_label']}｜HTTPS {'正常' if integrations['https'] else '未啟用'}"
        ),
        "",
        "【需要處理】",
        *[f"{index}. {item}" for index, item in enumerate(todo, 1)],
        "",
        "【正常但值得知道】",
        *[f"• {item}" for item in normal],
        "",
        f"完整資料：{data['admin_url']}",
        "本通知僅供管理員；完整客戶 Email、IP、驗證碼與 Token 不會出現在通知中。",
    ]
    summary_text = "\n".join(sections)
    return {
        "date": data["date"],
        "line": summary_text[:1800],
    }


def queue_daily_summary(slot):
    summary = build_daily_summary(slot)
    result = queue_admin_messages(
        f"daily-summary:{summary['date']}:{slot}",
        line_message=summary["line"],
    )
    return {"slot": slot, **result}


def retry_private_alerts(limit=10):
    connection = get_db()
    attempt_limit = max(1, min(int(limit), 50))
    now = datetime.now(timezone.utc)
    # A worker can crash after reserving its final attempt but before persistence.
    # Atomically retire only expired final leases; active workers retain ownership.
    connection.execute(
        """UPDATE notification_queue
           SET status = 'failed', last_error = 'retry_exhausted', retryable = 0,
               claim_token = '', claimed_until = '', next_attempt_at = '', updated_at = ?
           WHERE channel = 'line' AND status IN ('pending', 'failed', 'skipped')
             AND retryable = 1 AND attempts >= ? AND claim_token <> ''
             AND claimed_until <> '' AND claimed_until <= ?""",
        (now.isoformat(timespec="seconds"), MAX_DELIVERY_ATTEMPTS, now.isoformat(timespec="seconds")),
    )
    connection.commit()
    summary_cutoff = (now - timedelta(hours=DAILY_SUMMARY_RETRY_HOURS)).isoformat(timespec="seconds")
    alert_cutoff = (now - timedelta(days=PRIVATE_ALERT_RETRY_DAYS)).isoformat(timespec="seconds")
    eligibility = """
        ((dedupe_key LIKE '%:daily-summary:%' AND created_at >= ?)
         OR (dedupe_key NOT LIKE '%:daily-summary:%' AND created_at >= ?))
    """
    stale = connection.execute(
        f"""
        SELECT COUNT(*) AS count FROM notification_queue
        WHERE channel = 'line' AND status IN ('pending', 'failed', 'skipped')
          AND NOT {eligibility}
        """,
        (summary_cutoff, alert_cutoff),
    ).fetchone()
    rows = connection.execute(
        f"""
        SELECT * FROM notification_queue
        WHERE channel = 'line' AND status IN ('pending', 'failed', 'skipped')
          AND retryable = 1 AND attempts < ? AND next_attempt_at <= ? AND claimed_until <= ?
          AND {eligibility}
        ORDER BY id ASC LIMIT ?
        """,
        (MAX_DELIVERY_ATTEMPTS, now.isoformat(timespec="seconds"), now.isoformat(timespec="seconds"),
         summary_cutoff, alert_cutoff, 50),
    ).fetchall()
    sent = 0
    processed = 0
    deferred_unconfigured = 0
    by_channel = {"line": 0}
    deadline = time.monotonic() + 8
    for row in rows:
        if processed >= attempt_limit or time.monotonic() >= deadline:
            break
        if not line_admin_delivery_ready():
            deferred_unconfigured += 1
            continue
        status = _attempt_delivery(row)
        if status is None:
            continue
        processed += 1
        if status == "sent":
            sent += 1
            by_channel[row["channel"]] += 1
    legacy_email = connection.execute(
        """
        SELECT COUNT(*) AS count FROM notification_queue
        WHERE channel = 'email' AND status IN ('pending', 'failed', 'skipped')
        """
    ).fetchone()
    return {
        "processed": processed,
        "sent": sent,
        "sent_by_channel": by_channel,
        "ignored_stale": int(stale["count"] or 0),
        "ignored_legacy_email": int(legacy_email["count"] or 0),
        "deferred_unconfigured": deferred_unconfigured,
    }
