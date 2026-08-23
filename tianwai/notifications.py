import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from flask import current_app

from .db import get_db, utc_now


TAIPEI = timezone(timedelta(hours=8), name="Asia/Taipei")
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
    return f"LINE:{'*' * max(len(value) - 4, 4)}{value[-4:]}"


def _mask_email(value):
    local, separator, domain = str(value or "").partition("@")
    if not separator:
        return "not-configured"
    return f"{local[:1]}***@{domain}"


def mask_ip(value):
    value = str(value or "unknown").strip()
    if value in {"unknown", "system"}:
        return value
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", value):
        parts = value.split(".")
        return ".".join(parts[:3] + ["*"])
    if ":" in value:
        parts = [part for part in value.split(":") if part]
        return ":".join(parts[:3]) + ":*"
    return "masked"


def _sanitize_detail(value):
    text = str(value or "").replace("\r", " ").replace("\n", " ")[:280]
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email-hidden]", text)
    text = re.sub(
        r"(?i)\b(token|code|secret|password|cookie|authorization|signature)\s*[:=]\s*[^\s,;]+",
        r"\1=[hidden]",
        text,
    )
    text = re.sub(
        r"(?<!\d)(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}(?!\d)",
        r"\1.*",
        text,
    )
    return text


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


def _deliver(row):
    try:
        payload = json.loads(row["payload_json"])
        if row["channel"] == "line":
            return send_line_push(payload["message"])
        if row["channel"] == "email":
            recipient = os.environ.get("ADMIN_ALERT_EMAIL", "").strip()
            if not recipient:
                return "skipped", "admin_alert_email_not_configured"
            from .mailer import send_email

            result = send_email(
                recipient,
                payload["subject"],
                payload["text"],
                payload.get("kind", "admin_alert"),
            )
            if result in {"sent", "development"}:
                return "sent", ""
            return "failed", "smtp_delivery_failed"
        return "failed", "unsupported_channel"
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return "failed", "invalid_queue_payload"


def _persist_delivery(row_id, status, error):
    connection = get_db()
    now = utc_now()
    connection.execute(
        """
        UPDATE notification_queue
        SET status = ?, attempts = attempts + 1, last_error = ?, updated_at = ?,
            sent_at = CASE WHEN ? = 'sent' THEN ? ELSE sent_at END
        WHERE id = ?
        """,
        (status, str(error)[:120], now, status, now, row_id),
    )
    connection.commit()


def queue_admin_messages(
    dedupe_base,
    *,
    line_message,
    email_subject,
    email_text,
    email_kind="admin_alert",
    incident_id=None,
):
    """Queue and independently deliver an admin-only LINE and email message."""
    connection = get_db()
    now = utc_now()
    channel_payloads = {
        "line": (
            _mask_line(os.environ.get("LINE_ADMIN_USER_ID", "").strip()),
            {"message": str(line_message)[:1800]},
        ),
        "email": (
            _mask_email(os.environ.get("ADMIN_ALERT_EMAIL", "").strip()),
            {
                "subject": str(email_subject)[:160],
                "text": str(email_text)[:12000],
                "kind": str(email_kind)[:40],
            },
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
        status, error = _deliver(row)
        _persist_delivery(row["id"], status, error)
        result["channels"][channel] = status
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
    level_text = SEVERITY_LABELS.get(str(level), str(level).upper())
    event_text = EVENT_LABELS.get(str(event_type), str(event_type))
    occurred = _format_taipei(occurred_at)
    recommendation = (
        "立即登入後台檢查案件、相關存取紀錄與付款狀態；確認無誤前不要手動解除限制。"
        if level in {"high", "critical"}
        else "請於本日內登入後台複核事件與關聯紀錄。"
    )
    details = [
        f"嚴重度：{level_text}",
        f"事件：{event_text}（{event_type}）",
        f"時間：{occurred}（台北）",
        f"事件編號：{event_id or '未提供'}",
        f"案件編號：{incident_no or '未建立'}",
        f"客戶代碼：{customer_public_id or 'unknown'}",
        f"風險分數：{risk_score if risk_score is not None else '未評分'}",
        f"來源 IP：{mask_ip(ip)}",
        f"路徑：{str(path or 'system')[:160]}",
        f"系統動作：{str(action_taken or 'logged')[:100]}",
    ]
    safe_detail = _sanitize_detail(detail)
    if safe_detail:
        details.append(f"判定摘要：{safe_detail}")
    if user_agent:
        details.append(f"裝置／瀏覽器：{_sanitize_detail(user_agent)[:120]}")
    details.extend(
        [
            f"建議處置：{recommendation}",
            f"管理後台：{os.environ.get('BASE_URL', 'http://127.0.0.1:5088').rstrip('/')}/admin",
            "隱私提醒：通知已隱藏完整 Email、完整 IP、驗證碼、Token 與密鑰。",
        ]
    )
    email_text = "天外一筆管理員即時異常告警\n\n" + "\n".join(details)
    line_details = ["天外一筆｜即時異常告警"] + details
    return "\n".join(line_details)[:1800], f"[天外一筆][{level_text}] {event_text}", email_text


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
    line, subject, email = _event_messages(
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
        email_subject=subject,
        email_text=email,
        email_kind="admin_security_alert",
        incident_id=incident_id,
    )


def queue_security_alert(security_event_id, **context):
    line, subject, email = _event_messages(**context)
    return queue_admin_messages(
        f"security:{security_event_id}",
        line_message=line,
        email_subject=subject,
        email_text=email,
        email_kind="admin_security_alert",
    )


def _daily_metrics():
    connection = get_db()
    now_local = _taipei_now()
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_local.astimezone(timezone.utc).isoformat(timespec="seconds")
    now_utc = now_local.astimezone(timezone.utc).isoformat(timespec="seconds")

    orders = connection.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) AS paid,
               SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
               SUM(CASE WHEN status IN ('cancelled', 'refunded') THEN 1 ELSE 0 END) AS reversed,
               COALESCE(SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END), 0) AS revenue
        FROM orders WHERE created_at >= ? AND created_at <= ?
        """,
        (start_utc, now_utc),
    ).fetchone()
    access = connection.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM orders WHERE status = 'paid') AS entitlements,
          (SELECT COUNT(DISTINCT order_id) FROM activation_codes WHERE used_at IS NOT NULL) AS activated,
          (SELECT COUNT(*) FROM customer_sessions WHERE revoked_at IS NULL AND expires_at > ?) AS sessions,
          (SELECT COUNT(*) FROM customer_devices WHERE revoked_at IS NULL AND trusted_until > ?) AS devices
        """,
        (now_utc, now_utc),
    ).fetchone()
    traffic = connection.execute(
        """
        SELECT COUNT(*) AS views FROM analytics_events
        WHERE event_name IN ('page_view', 'view_idea') AND created_at >= ? AND created_at <= ?
        """,
        (start_utc, now_utc),
    ).fetchone()
    top_idea = connection.execute(
        """
        SELECT ideas.title, COUNT(*) AS count
        FROM analytics_events JOIN ideas ON ideas.id = analytics_events.idea_id
        WHERE analytics_events.event_name = 'view_idea'
          AND analytics_events.created_at >= ? AND analytics_events.created_at <= ?
        GROUP BY ideas.id ORDER BY count DESC, ideas.id LIMIT 1
        """,
        (start_utc, now_utc),
    ).fetchone()
    risk = connection.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM risk_incidents WHERE status IN ('open', 'reviewing')) AS open_incidents,
          (SELECT COUNT(*) FROM access_events WHERE severity IN ('high', 'critical') AND created_at >= ?) AS high_access,
          (SELECT COUNT(*) FROM security_events WHERE severity IN ('high', 'critical') AND created_at >= ?) AS high_security,
          (SELECT COUNT(*) FROM blocked_ips WHERE blocked_until > ?) AS blocked_ips,
          (SELECT COUNT(*) FROM notification_queue WHERE status IN ('failed', 'skipped')) AS notification_failures,
          (SELECT COUNT(*) FROM email_events WHERE status = 'failed' AND created_at >= ?) AS email_failures
        """,
        (start_utc, start_utc, now_utc, start_utc),
    ).fetchone()
    from .mailer import email_delivery_ready
    from .payments import payment_checkout_status
    from .risk import verify_access_event_chain

    checkout = payment_checkout_status()
    base_url = os.environ.get("BASE_URL", "http://127.0.0.1:5088").strip()
    line_ready = bool(
        os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
        and os.environ.get("LINE_ADMIN_USER_ID", "").strip()
    )
    email_ready = bool(
        os.environ.get("ADMIN_ALERT_EMAIL", "").strip() and email_delivery_ready()
    )
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
            "views": int(traffic["views"] or 0),
            "top": f"{top_idea['title']}（{top_idea['count']} 次）" if top_idea else "目前無想法頁瀏覽紀錄",
        },
        "risk": {key: int(risk[key] or 0) for key in risk.keys()},
        "integrations": {
            "line": line_ready,
            "email": email_ready,
            "payment": checkout["provider"] != "unavailable",
            "payment_label": checkout["label"],
            "https": base_url.lower().startswith("https://") or current_app.config.get("TESTING", False),
            "chain": bool(chain["valid"]),
            "chain_checked": int(chain["checked"]),
        },
        "admin_url": f"{base_url.rstrip('/')}/admin",
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
    if risk["notification_failures"]:
        todo.append(f"重試或修正 {risk['notification_failures']} 筆未送達管理通知。")
    if risk["email_failures"]:
        todo.append(f"確認 {risk['email_failures']} 筆今日交易郵件寄送失敗。")
    if access["pending"]:
        todo.append(f"確認 {access['pending']} 份已付款但尚未完成開通的權限。")
    if not integrations["line"]:
        todo.append("補齊或檢查 LINE 管理員推播設定。")
    if not integrations["email"]:
        todo.append("補齊或檢查 Gmail／SMTP 管理員告警設定。")
    if not integrations["payment"]:
        todo.append("金流目前不可用，付款前請先完成設定。")
    if not integrations["chain"]:
        todo.append("重大：存取證據鏈驗證失敗，請停止手動變更並立即查核。")
    if not todo:
        todo.append("目前無需立即處理；系統持續監控中。")

    normal = [
        f"今日高／重大存取事件 {risk['high_access']} 件；一般安全事件高／重大 {risk['high_security']} 件。",
        f"證據鏈{'完整' if integrations['chain'] else '異常'}，已驗證 {integrations['chain_checked']} 筆存取事件。",
        f"目前封鎖來源 {risk['blocked_ips']} 個；活躍工作階段 {access['sessions']} 個。",
        f"LINE 管理告警{'已就緒' if integrations['line'] else '尚未就緒'}；Gmail 告警{'已就緒' if integrations['email'] else '尚未就緒'}。",
        f"金流：{integrations['payment_label']}；HTTPS：{'正常' if integrations['https'] else '未啟用'}。",
    ]
    heading = f"天外一筆｜{SLOTS[slot]}管理員營運摘要"
    sections = [
        heading,
        f"統計期間：{data['period']}",
        f"產生時間：{data['generated']}（台北）",
        "",
        "【訂單與營收】",
        f"今日訂單 {orders['total']} 筆｜已付款 {orders['paid']}｜待付款 {orders['pending']}｜取消／退款 {orders['reversed']}",
        f"今日實收 NT$ {orders['revenue']:,}｜瀏覽 {data['traffic']['views']} 次｜熱門想法：{data['traffic']['top']}",
        "",
        "【開通與存取】",
        f"已付款權限 {access['entitlements']}｜已開通 {access['activated']}｜待開通 {access['pending']}",
        f"活躍工作階段 {access['sessions']}｜可信裝置 {access['devices']}",
        "",
        "【安全與風險】",
        f"未結案件 {risk['open_incidents']}｜今日高／重大存取 {risk['high_access']}｜高／重大安全事件 {risk['high_security']}｜封鎖來源 {risk['blocked_ips']}",
        "",
        "【系統與通知】",
        f"未送達管理通知 {risk['notification_failures']}｜今日交易郵件失敗 {risk['email_failures']}",
        f"LINE {'就緒' if integrations['line'] else '未就緒'}｜Gmail {'就緒' if integrations['email'] else '未就緒'}｜金流 {integrations['payment_label']}｜HTTPS {'正常' if integrations['https'] else '未啟用'}",
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
    email_text = "\n".join(sections)
    return {
        "date": data["date"],
        "line": email_text[:1800],
        "subject": f"[天外一筆] {SLOTS[slot]}營運摘要｜{data['date']}",
        "email": email_text,
    }


def queue_daily_summary(slot):
    summary = build_daily_summary(slot)
    result = queue_admin_messages(
        f"daily-summary:{summary['date']}:{slot}",
        line_message=summary["line"],
        email_subject=summary["subject"],
        email_text=summary["email"],
        email_kind="admin_daily_summary",
    )
    return {"slot": slot, **result}


def retry_private_alerts(limit=10):
    connection = get_db()
    rows = connection.execute(
        """
        SELECT * FROM notification_queue
        WHERE channel IN ('line', 'email') AND status IN ('pending', 'failed', 'skipped')
        ORDER BY id ASC LIMIT ?
        """,
        (max(1, min(int(limit), 50)),),
    ).fetchall()
    sent = 0
    by_channel = {"line": 0, "email": 0}
    for row in rows:
        status, error = _deliver(row)
        _persist_delivery(row["id"], status, error)
        if status == "sent":
            sent += 1
            by_channel[row["channel"]] += 1
    return {"processed": len(rows), "sent": sent, "sent_by_channel": by_channel}
