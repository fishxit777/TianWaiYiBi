import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request

from .access import current_customer_session
from .db import get_db, utc_now
from .security import require_public_csrf


conversations_bp = Blueprint(
    "conversations", __name__, url_prefix="/api/conversations"
)

HOME_SECTIONS = {
    "home-hero": "卷首・一筆開天",
    "home-world": "卷一・擇法",
    "home-ideas": "卷二・六脈仙策",
    "home-how": "卷三・入世之法",
    "home-creed": "卷四・仙閣心訣",
    "home-transmission": "卷五・傳音閣",
}
IDEA_SECTION = "idea-detail"
CUSTOMER_COLORS = ("jade", "gold", "azure", "violet", "coral", "silver")
SHORT_WINDOW_LIMIT = 5
DAILY_LIMIT = 30
BODY_MIN_LENGTH = 2
BODY_MAX_LENGTH = 800
PUBLIC_LINK_PATTERN = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
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


def keeper_identity():
    return {
        "alias": "守閣者",
        "label": "守閣者",
        "color": "keeper",
        "badge": "守閣者",
    }


def resolve_section_context(section_key, idea_slug="", include_unpublished=False):
    key = str(section_key or "").strip().lower()
    if key in HOME_SECTIONS:
        return {"key": key, "label": HOME_SECTIONS[key], "idea": None}
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


def normalize_message_body(value, visibility):
    body = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(body) < BODY_MIN_LENGTH or len(body) > BODY_MAX_LENGTH:
        return None, f"留言需介於 {BODY_MIN_LENGTH} 至 {BODY_MAX_LENGTH} 字"
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


def serialize_message(row, viewer_customer_id=None, admin_view=False):
    customer = (
        customer_identity(row["customer_public_id"])
        if row["customer_public_id"]
        else None
    )
    author = keeper_identity() if row["author_type"] == "admin" else customer
    badges = []
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
        "target": customer if row["author_type"] == "admin" and customer else None,
        "visibility": row["visibility"],
        "status": row["status"],
        "badges": badges,
        "body": row["body"],
        "reply_to_id": row["reply_to_id"],
        "mine": bool(
            viewer_customer_id
            and row["author_type"] == "customer"
            and row["customer_id"] == viewer_customer_id
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
            email_subject=f"天外一筆｜新{scope}傳音",
            email_text=notice,
            email_kind="conversation_notice",
        )
    except Exception:
        current_app.logger.exception("Unable to queue conversation notification")


@conversations_bp.get("/<section_key>")
def list_messages(section_key):
    visibility = str(request.args.get("visibility", "public")).strip().lower()
    if visibility not in {"public", "private"}:
        return jsonify({"error": "不支援的傳音範圍"}), 400
    context = resolve_section_context(section_key, request.args.get("idea_slug", ""))
    if context is None:
        return jsonify({"error": "找不到傳音區塊"}), 404

    customer_session = current_customer_session()
    if visibility == "private" and customer_session is None:
        return _no_store(jsonify({"error": "請先登入客戶專區"})), 401

    conditions, parameters = _context_conditions(context)
    if visibility == "public":
        if customer_session is None:
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
    viewer = {"authenticated": customer_session is not None}
    if customer_session is not None:
        viewer.update(customer_identity(customer_session["customer_public_id"], viewer=True))
    response = jsonify(
        {
            "section": {"key": context["key"], "label": context["label"]},
            "visibility": visibility,
            "viewer": viewer,
            "messages": [
                serialize_message(
                    row,
                    viewer_customer_id=(
                        customer_session["customer_id"] if customer_session else None
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
    if customer_session is None:
        return _no_store(jsonify({"error": "請先登入客戶專區"})), 401
    csrf_error = require_public_csrf()
    if csrf_error:
        return csrf_error
    data = request.get_json(silent=True) or {}
    visibility = str(data.get("visibility", "public")).strip().lower()
    if visibility not in {"public", "private"}:
        return jsonify({"error": "不支援的傳音範圍"}), 400
    context = resolve_section_context(section_key, data.get("idea_slug", ""))
    if context is None:
        return jsonify({"error": "找不到傳音區塊"}), 404
    body, error = normalize_message_body(data.get("body", ""), visibility)
    if error:
        return jsonify({"error": error}), 400
    if _rate_limited(customer_session["customer_id"]):
        return jsonify({"error": "傳音過於頻繁，請稍後再試"}), 429

    now = utc_now()
    connection = get_db()
    cursor = connection.execute(
        """
        INSERT INTO section_messages
            (public_id, section_key, idea_id, author_type, customer_id,
             visibility, status, body, created_at, updated_at)
        VALUES (?, ?, ?, 'customer', ?, ?, ?, ?, ?, ?)
        """,
        (
            f"MSG-{secrets.token_hex(8).upper()}",
            context["key"],
            context["idea"]["id"] if context["idea"] else None,
            customer_session["customer_id"],
            visibility,
            "pending" if visibility == "public" else "published",
            body,
            now,
            now,
        ),
    )
    connection.commit()
    row = connection.execute(
        f"{message_query()} WHERE section_messages.id = ?", (cursor.lastrowid,)
    ).fetchone()
    _notify_admin_new_message(context, visibility, row["public_id"])
    response = jsonify(
        {
            "ok": True,
            "message": serialize_message(
                row, viewer_customer_id=customer_session["customer_id"]
            ),
        }
    )
    response.status_code = 201
    return _no_store(response)
