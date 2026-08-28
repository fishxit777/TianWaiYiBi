import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request

from .access import current_customer_session
from .analytics import record_event
from .db import get_db, utc_now
from .security import get_client_ip, hash_scoped_token, require_public_csrf
from .turnstile import CONVERSATION_ACTION, turnstile_configured, verify_turnstile


conversations_bp = Blueprint(
    "conversations", __name__, url_prefix="/api/conversations"
)

IDEA_SECTION = "idea-detail"
CUSTOMER_COLORS = ("jade", "gold", "azure", "violet", "coral", "silver")
SHORT_WINDOW_LIMIT = 5
DAILY_LIMIT = 30
VISITOR_SHORT_WINDOW_LIMIT = 3
VISITOR_DAILY_LIMIT = 10
BODY_MIN_LENGTH = 2
BODY_MAX_LENGTH = 800
VISITOR_BODY_MAX_LENGTH = 500
VISITOR_COOKIE = "twyb_visitor"
VISITOR_COOKIE_DAYS = 365
VISITOR_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{40,60}$")
PUBLIC_LINK_PATTERN = re.compile(
    r"(?:https?://|www\.|(?:[a-z0-9-]+\.)+[a-z]{2,24}\b)", re.IGNORECASE
)
MARKUP_PATTERN = re.compile(r"<[^>]*>")


def customer_identity(public_id, viewer=False):
    normalized = str(public_id or "")
    compact = "".join(character for character in normalized if character.isalnum())
    suffix = (compact[-4:] or "無名").upper()
    color_index = hashlib.sha256(normalized.encode("utf-8")).digest()[0] % len(
        CUSTOMER_COLORS
    )
    return {
        "alias": f"同道・{suffix}",
        "label": f"同道・{suffix}",
        "color": CUSTOMER_COLORS[color_index],
        "badge": "你的識別" if viewer else "同道",
    }


def visitor_identity(visitor_token_hash, viewer=False):
    normalized = str(visitor_token_hash or "")
    suffix = (normalized[:6] or "無名").upper()
    color_index = hashlib.sha256(normalized.encode("utf-8")).digest()[0] % len(
        CUSTOMER_COLORS
    )
    return {
        "alias": f"訪客・{suffix}",
        "label": f"訪客・{suffix}",
        "color": CUSTOMER_COLORS[color_index],
        "badge": "你的訪客代號" if viewer else "訪客",
    }


def keeper_identity():
    return {
        "alias": "守閣者",
        "label": "守閣者",
        "color": "keeper",
        "badge": "守閣者",
    }


def customer_activity_scope(public_id):
    """Create an opaque browser read-state scope without exposing customer IDs."""
    secret = str(current_app.config["SECRET_KEY"]).encode("utf-8")
    return hmac.new(secret, str(public_id).encode("utf-8"), hashlib.sha256).hexdigest()[:20]


def resolve_section_context(section_key, idea_slug="", include_unpublished=False):
    key = str(section_key or "").strip().lower()
    if key != IDEA_SECTION:
        return None
    slug = str(idea_slug or "").strip().lower()[:100]
    if not slug:
        return None
    query = "SELECT id, slug, title, published FROM ideas WHERE slug = ?"
    idea = get_db().execute(query, (slug,)).fetchone()
    if idea is None or (not include_unpublished and not bool(idea["published"])):
        return None
    return {
        "key": key,
        "label": f"仙策・{idea['title']}",
        "idea": idea,
    }


def normalize_message_body(value, visibility, max_length=BODY_MAX_LENGTH):
    body = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(body) < BODY_MIN_LENGTH or len(body) > max_length:
        return None, f"留言需介於 {BODY_MIN_LENGTH} 至 {max_length} 字"
    if MARKUP_PATTERN.search(body) or any(
        ord(character) < 32 and character not in "\n\t" for character in body
    ):
        return None, "留言只接受一般文字"
    if visibility == "public" and PUBLIC_LINK_PATTERN.search(body):
        return None, "公開傳音暫不接受網址，請改用純文字描述"
    return body, ""


def message_query():
    return """
        SELECT section_messages.*, ideas.slug AS idea_slug, ideas.title AS idea_title,
               customers.public_id AS customer_public_id
        FROM section_messages
        LEFT JOIN ideas ON ideas.id = section_messages.idea_id
        LEFT JOIN customers ON customers.id = section_messages.customer_id
    """


def serialize_message(
    row, viewer_customer_id=None, viewer_visitor_hash=None, admin_view=False
):
    customer = (
        customer_identity(row["customer_public_id"])
        if row["customer_public_id"]
        else None
    )
    visitor = (
        visitor_identity(row["visitor_token_hash"])
        if row["visitor_token_hash"]
        else None
    )
    if row["author_type"] == "admin":
        author = keeper_identity()
    elif row["author_type"] == "visitor":
        author = visitor
    else:
        author = customer
    badges = []
    if row["author_type"] == "visitor":
        badges.append("訪客")
    if row["status"] == "pending":
        badges.append("等待公開")
    elif row["visibility"] == "private":
        badges.append("指定給你" if row["author_type"] == "admin" else "私密")
    elif row["author_type"] == "admin":
        badges.append("守閣者回覆")
    payload = {
        "id": row["id"],
        "public_id": row["public_id"],
        "section_key": row["section_key"],
        "idea_slug": row["idea_slug"],
        "author_type": row["author_type"],
        "author": author,
        "target": (customer or visitor) if row["author_type"] == "admin" else None,
        "visibility": row["visibility"],
        "status": row["status"],
        "badges": badges,
        "body": row["body"],
        "reply_to_id": row["reply_to_id"],
        "mine": bool(
            (
                viewer_customer_id
                and row["author_type"] == "customer"
                and row["customer_id"] == viewer_customer_id
            )
            or (
                viewer_visitor_hash
                and row["author_type"] == "visitor"
                and hmac.compare_digest(
                    str(row["visitor_token_hash"]), str(viewer_visitor_hash)
                )
            )
        ),
        "created_at": row["created_at"],
    }
    if admin_view:
        payload["customer_public_id"] = row["customer_public_id"]
        payload["idea_title"] = row["idea_title"]
        payload["moderated_at"] = row["moderated_at"]
    return payload


def _context_conditions(context):
    if context["idea"] is None:
        return "section_messages.section_key = ? AND section_messages.idea_id IS NULL", [
            context["key"]
        ]
    return "section_messages.section_key = ? AND section_messages.idea_id = ?", [
        context["key"],
        context["idea"]["id"],
    ]


def _rate_limited(customer_id):
    now = datetime.now(timezone.utc)
    connection = get_db()
    short_start = (now - timedelta(minutes=10)).isoformat(timespec="seconds")
    day_start = (now - timedelta(days=1)).isoformat(timespec="seconds")
    short_count = connection.execute(
        """
        SELECT COUNT(*) AS count FROM section_messages
        WHERE customer_id = ? AND author_type = 'customer' AND created_at >= ?
        """,
        (customer_id, short_start),
    ).fetchone()["count"]
    daily_count = connection.execute(
        """
        SELECT COUNT(*) AS count FROM section_messages
        WHERE customer_id = ? AND author_type = 'customer' AND created_at >= ?
        """,
        (customer_id, day_start),
    ).fetchone()["count"]
    return int(short_count or 0) >= SHORT_WINDOW_LIMIT or int(
        daily_count or 0
    ) >= DAILY_LIMIT


def _visitor_credential(create=False):
    raw_token = str(request.cookies.get(VISITOR_COOKIE, ""))
    if not VISITOR_TOKEN_PATTERN.fullmatch(raw_token):
        if not create:
            return None, None
        raw_token = secrets.token_urlsafe(32)
    return raw_token, hash_scoped_token("conversation-visitor", raw_token)


def _visitor_source_hash():
    return hash_scoped_token("conversation-source", get_client_ip())


def _visitor_rate_limited(visitor_token_hash, source_hash):
    now = datetime.now(timezone.utc)
    short_start = (now - timedelta(minutes=10)).isoformat(timespec="seconds")
    day_start = (now - timedelta(days=1)).isoformat(timespec="seconds")
    connection = get_db()
    short_count = connection.execute(
        """
        SELECT COUNT(*) AS count FROM section_messages
        WHERE author_type = 'visitor'
          AND (visitor_token_hash = ? OR source_hash = ?)
          AND created_at >= ?
        """,
        (visitor_token_hash, source_hash, short_start),
    ).fetchone()["count"]
    daily_count = connection.execute(
        """
        SELECT COUNT(*) AS count FROM section_messages
        WHERE author_type = 'visitor'
          AND (visitor_token_hash = ? OR source_hash = ?)
          AND created_at >= ?
        """,
        (visitor_token_hash, source_hash, day_start),
    ).fetchone()["count"]
    return int(short_count or 0) >= VISITOR_SHORT_WINDOW_LIMIT or int(
        daily_count or 0
    ) >= VISITOR_DAILY_LIMIT


def _set_visitor_cookie(response, raw_token):
    secure = bool(current_app.config.get("SESSION_COOKIE_SECURE")) or request.is_secure
    if request.headers.get("X-Forwarded-Proto", "").lower() == "https":
        secure = True
    response.set_cookie(
        VISITOR_COOKIE,
        raw_token,
        max_age=VISITOR_COOKIE_DAYS * 24 * 60 * 60,
        secure=secure,
        httponly=True,
        samesite="Lax",
        path="/",
    )


def _no_store(response):
    response.headers["Cache-Control"] = "no-store, no-cache, max-age=0, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


def _notify_admin_new_message(context, visibility, public_id):
    """Notify the owner without exporting the customer identity or message body."""
    try:
        from .notifications import queue_admin_messages

        scope = "公開待審核" if visibility == "public" else "私密"
        base_url = os.environ.get("BASE_URL", "").strip().rstrip("/")
        admin_url = f"{base_url}/admin#conversations" if base_url else "後台的傳音對話工作區"
        notice = (
            f"天外一筆收到一則{scope}傳音。\n"
            f"區塊：{context['label']}\n"
            f"請至 {admin_url} 查看；通知不含客戶身分與訊息正文。"
        )
        queue_admin_messages(
            f"conversation:{public_id}",
            line_message=notice,
        )
    except Exception:
        current_app.logger.exception("Unable to queue conversation notification")


@conversations_bp.get("/idea-activity")
def idea_activity():
    """Return activity markers only; never return message bodies or identities."""
    customer_session = current_customer_session()
    customer_id = customer_session["customer_id"] if customer_session else None
    rows = get_db().execute(
        """
        SELECT ideas.slug,
               SUM(CASE
                   WHEN section_messages.visibility = 'public'
                    AND section_messages.status = 'published'
                   THEN 1 ELSE 0 END) AS public_count,
               MAX(CASE
                   WHEN section_messages.visibility = 'public'
                    AND section_messages.status = 'published'
                   THEN section_messages.id ELSE 0 END) AS latest_public_id,
               SUM(CASE
                   WHEN section_messages.visibility = 'private'
                    AND section_messages.status = 'published'
                    AND section_messages.author_type = 'admin'
                    AND section_messages.customer_id = ?
                   THEN 1 ELSE 0 END) AS private_reply_count,
               MAX(CASE
                   WHEN section_messages.visibility = 'private'
                    AND section_messages.status = 'published'
                    AND section_messages.author_type = 'admin'
                    AND section_messages.customer_id = ?
                   THEN section_messages.id ELSE 0 END) AS latest_private_reply_id
        FROM ideas
        LEFT JOIN section_messages
          ON section_messages.idea_id = ideas.id
         AND section_messages.section_key = 'idea-detail'
        WHERE ideas.published = 1
        GROUP BY ideas.id, ideas.slug, ideas.sort_order
        ORDER BY ideas.sort_order, ideas.id
        """,
        (customer_id, customer_id),
    ).fetchall()
    ideas = []
    for row in rows:
        item = {
            "slug": row["slug"],
            "public_count": int(row["public_count"] or 0),
            "latest_public_id": int(row["latest_public_id"] or 0),
        }
        if customer_session is not None:
            item.update(
                {
                    "private_reply_count": int(row["private_reply_count"] or 0),
                    "latest_private_reply_id": int(
                        row["latest_private_reply_id"] or 0
                    ),
                }
            )
        ideas.append(item)
    viewer = {"authenticated": customer_session is not None}
    if customer_session is not None:
        viewer["activity_scope"] = customer_activity_scope(
            customer_session["customer_public_id"]
        )
    return _no_store(
        jsonify(
            {
                "viewer": viewer,
                "ideas": ideas,
            }
        )
    )


@conversations_bp.get("/<section_key>")
def list_messages(section_key):
    visibility = str(request.args.get("visibility", "public")).strip().lower()
    if visibility not in {"public", "private"}:
        return jsonify({"error": "不支援的傳音範圍"}), 400
    context = resolve_section_context(section_key, request.args.get("idea_slug", ""))
    if context is None:
        return jsonify({"error": "找不到傳音區塊"}), 404

    customer_session = current_customer_session()
    _visitor_raw, visitor_token_hash = _visitor_credential()
    if visibility == "private" and customer_session is None:
        return _no_store(jsonify({"error": "請先登入客戶專區"})), 401

    conditions, parameters = _context_conditions(context)
    if visibility == "public":
        if customer_session is None:
            if visitor_token_hash:
                status_condition = """(
                    section_messages.status = 'published'
                    OR (section_messages.status = 'pending'
                        AND section_messages.author_type = 'visitor'
                        AND section_messages.visitor_token_hash = ?)
                )"""
                parameters.extend(["public", visitor_token_hash])
            else:
                status_condition = "section_messages.status = 'published'"
                parameters.append("public")
        else:
            status_condition = """(
                section_messages.status = 'published'
                OR (section_messages.status = 'pending'
                    AND section_messages.author_type = 'customer'
                    AND section_messages.customer_id = ?)
            )"""
            parameters.extend(["public", customer_session["customer_id"]])
        where = f"{conditions} AND section_messages.visibility = ? AND {status_condition}"
    else:
        parameters.extend(["private", customer_session["customer_id"]])
        where = (
            f"{conditions} AND section_messages.visibility = ? "
            "AND section_messages.customer_id = ? AND section_messages.status = 'published'"
        )
    rows = get_db().execute(
        f"{message_query()} WHERE {where} ORDER BY section_messages.created_at, section_messages.id LIMIT 60",
        tuple(parameters),
    ).fetchall()
    marker_conditions, marker_parameters = _context_conditions(context)
    if visibility == "public":
        marker_parameters.extend(["public", "published"])
        marker_where = (
            f"{marker_conditions} AND section_messages.visibility = ? "
            "AND section_messages.status = ?"
        )
    else:
        marker_parameters.extend(
            ["private", "published", "admin", customer_session["customer_id"]]
        )
        marker_where = (
            f"{marker_conditions} AND section_messages.visibility = ? "
            "AND section_messages.status = ? AND section_messages.author_type = ? "
            "AND section_messages.customer_id = ?"
        )
    latest_activity_id = get_db().execute(
        f"SELECT COALESCE(MAX(section_messages.id), 0) AS id "
        f"FROM section_messages WHERE {marker_where}",
        tuple(marker_parameters),
    ).fetchone()["id"]
    viewer = {
        "authenticated": customer_session is not None,
        "visitor_submission_enabled": turnstile_configured(),
    }
    if customer_session is not None:
        viewer.update(customer_identity(customer_session["customer_public_id"], viewer=True))
        viewer["activity_scope"] = customer_activity_scope(
            customer_session["customer_public_id"]
        )
    elif visitor_token_hash:
        viewer.update(visitor_identity(visitor_token_hash, viewer=True))
    response = jsonify(
        {
            "section": {"key": context["key"], "label": context["label"]},
            "visibility": visibility,
            "latest_activity_id": int(latest_activity_id or 0),
            "viewer": viewer,
            "messages": [
                serialize_message(
                    row,
                    viewer_customer_id=(
                        customer_session["customer_id"] if customer_session else None
                    ),
                    viewer_visitor_hash=(
                        visitor_token_hash if customer_session is None else None
                    ),
                )
                for row in rows
            ],
        }
    )
    return _no_store(response)


@conversations_bp.post("/<section_key>/messages")
def create_message(section_key):
    customer_session = current_customer_session()
    csrf_error = require_public_csrf()
    if csrf_error:
        return csrf_error
    data = request.get_json(silent=True) or {}
    visibility = str(data.get("visibility", "public")).strip().lower()
    if visibility not in {"public", "private"}:
        return jsonify({"error": "不支援的傳音範圍"}), 400
    if customer_session is None and visibility == "private":
        return _no_store(jsonify({"error": "請先登入客戶專區"})), 401
    context = resolve_section_context(section_key, data.get("idea_slug", ""))
    if context is None:
        return jsonify({"error": "找不到傳音區塊"}), 404
    visitor_raw = None
    visitor_token_hash = None
    source_hash = None
    if customer_session is None:
        if not turnstile_configured():
            return _no_store(jsonify({"error": "訪客留言目前暫停，請稍後再試"})), 503
        if str(data.get("website", "")).strip():
            return jsonify({"error": "留言未通過安全檢查"}), 400
        if not verify_turnstile(
            data.get("turnstile_token", ""),
            get_client_ip(),
            expected_action=CONVERSATION_ACTION,
        ):
            return jsonify({"error": "請完成訪客安全驗證後再送出"}), 403
        visitor_raw, visitor_token_hash = _visitor_credential(create=True)
        source_hash = _visitor_source_hash()
    body, error = normalize_message_body(
        data.get("body", ""),
        visibility,
        max_length=(
            VISITOR_BODY_MAX_LENGTH if customer_session is None else BODY_MAX_LENGTH
        ),
    )
    if error:
        return jsonify({"error": error}), 400
    if customer_session is not None and _rate_limited(customer_session["customer_id"]):
        return jsonify({"error": "傳音過於頻繁，請稍後再試"}), 429
    if customer_session is None and _visitor_rate_limited(
        visitor_token_hash, source_hash
    ):
        return jsonify({"error": "訪客傳音過於頻繁，請稍後再試"}), 429

    now = utc_now()
    connection = get_db()
    public_id = f"MSG-{secrets.token_hex(8).upper()}"
    cursor = connection.execute(
        """
        INSERT INTO section_messages
            (public_id, section_key, idea_id, author_type, customer_id,
             visitor_token_hash, source_hash, visibility, status, body,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            public_id,
            context["key"],
            context["idea"]["id"] if context["idea"] else None,
            "customer" if customer_session is not None else "visitor",
            customer_session["customer_id"] if customer_session is not None else None,
            visitor_token_hash,
            source_hash,
            visibility,
            "pending" if visibility == "public" else "published",
            body,
            now,
            now,
        ),
    )
    message_id = cursor.lastrowid
    if context["idea"] is not None:
        record_event(
            "conversation_submitted",
            idea_id=context["idea"]["id"],
            dedupe_scope=f"message:{public_id}",
            connection=connection,
            commit=False,
        )
    connection.commit()
    row = connection.execute(
        f"{message_query()} WHERE section_messages.id = ?", (message_id,)
    ).fetchone()
    _notify_admin_new_message(context, visibility, row["public_id"])
    response = jsonify(
        {
            "ok": True,
            "message": serialize_message(
                row,
                viewer_customer_id=(
                    customer_session["customer_id"] if customer_session else None
                ),
                viewer_visitor_hash=visitor_token_hash,
            ),
        }
    )
    response.status_code = 201
    if customer_session is None:
        _set_visitor_cookie(response, visitor_raw)
    return _no_store(response)
