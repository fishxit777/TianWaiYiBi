import hashlib
import hmac
import json
import secrets

from flask import current_app, has_request_context

from .db import get_db, utc_now
from .notifications import queue_private_alert
from .security import get_client_ip, safe_user_agent


SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def severity_for_score(score):
    if score >= 85:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def _chain_hash(previous_hash, canonical):
    key = str(current_app.config["SECRET_KEY"]).encode("utf-8")
    return hmac.new(key, f"{previous_hash}|{canonical}".encode("utf-8"), hashlib.sha256).hexdigest()


def record_access_event(
    event_type,
    risk_score,
    action_taken,
    *,
    customer_id=None,
    device_id=None,
    order_id=None,
    metadata=None,
):
    """Write an append-only, HMAC-chained access event and open incidents when needed."""
    connection = get_db()
    if not connection.in_transaction:
        connection.execute("BEGIN IMMEDIATE")
    event_id = f"AE-{secrets.token_hex(8).upper()}"
    now = utc_now()
    severity = severity_for_score(int(risk_score))
    ip = get_client_ip() if has_request_context() else "system"
    user_agent = safe_user_agent() if has_request_context() else "system"
    clean_metadata = {
        str(key)[:40]: str(value)[:160]
        for key, value in (metadata or {}).items()
        if key not in {"email", "code", "token", "full_ip"}
    }
    metadata_json = json.dumps(clean_metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    previous = connection.execute(
        "SELECT event_hash FROM access_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    previous_hash = previous["event_hash"] if previous else "GENESIS"
    canonical = "|".join(
        [
            event_id,
            str(customer_id or ""),
            str(device_id or ""),
            str(order_id or ""),
            str(event_type),
            severity,
            str(int(risk_score)),
            str(action_taken),
            ip,
            user_agent,
            metadata_json,
            now,
        ]
    )
    event_hash = _chain_hash(previous_hash, canonical)
    cursor = connection.execute(
        """
        INSERT INTO access_events
            (event_id, customer_id, device_id, order_id, event_type, severity,
             risk_score, action_taken, ip, user_agent, metadata_json,
             previous_hash, event_hash, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id, customer_id, device_id, order_id, str(event_type)[:80], severity,
            int(risk_score), str(action_taken)[:80], ip[:64], user_agent[:240],
            metadata_json, previous_hash, event_hash, now,
        ),
    )
    incident = None
    if severity != "low":
        incident_no = f"RI-{secrets.token_hex(6).upper()}"
        incident_cursor = connection.execute(
            """
            INSERT INTO risk_incidents
                (incident_no, access_event_id, customer_id, level, reason_codes,
                 status, action_taken, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (
                incident_no, cursor.lastrowid, customer_id, severity,
                json.dumps([str(event_type)[:80]], ensure_ascii=False),
                str(action_taken)[:80], now, now,
            ),
        )
        incident = (incident_cursor.lastrowid, incident_no)
        if customer_id:
            current = connection.execute(
                "SELECT risk_level FROM customers WHERE id = ?", (customer_id,)
            ).fetchone()
            if current and SEVERITY_RANK[severity] > SEVERITY_RANK.get(current["risk_level"], 0):
                connection.execute(
                    "UPDATE customers SET risk_level = ?, updated_at = ? WHERE id = ?",
                    (severity, now, customer_id),
                )
    connection.commit()

    if incident and severity in {"high", "critical"}:
        customer = connection.execute(
            "SELECT public_id FROM customers WHERE id = ?", (customer_id,)
        ).fetchone() if customer_id else None
        try:
            queue_private_alert(
                incident[0], incident[1], severity, str(event_type),
                customer["public_id"] if customer else "unknown",
            )
        except Exception:
            current_app.logger.exception("Unable to queue private security alert")
    return event_id


def verify_access_event_chain():
    """Return integrity summary for admin inspection without mutating evidence."""
    rows = get_db().execute("SELECT * FROM access_events ORDER BY id").fetchall()
    previous_hash = "GENESIS"
    for row in rows:
        metadata_json = row["metadata_json"]
        canonical = "|".join(
            [
                row["event_id"], str(row["customer_id"] or ""), str(row["device_id"] or ""),
                str(row["order_id"] or ""), row["event_type"], row["severity"],
                str(row["risk_score"]), row["action_taken"], row["ip"], row["user_agent"],
                metadata_json, row["created_at"],
            ]
        )
        expected = _chain_hash(previous_hash, canonical)
        if row["previous_hash"] != previous_hash or not hmac.compare_digest(row["event_hash"], expected):
            return {"valid": False, "checked": len(rows), "broken_event_id": row["event_id"]}
        previous_hash = row["event_hash"]
    return {"valid": True, "checked": len(rows), "broken_event_id": ""}
