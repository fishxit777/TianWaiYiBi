import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for

from .analytics import (
    IDEA_EVENTS,
    ensure_analytics_session,
    public_event_dedupe_scope,
    record_event,
    validate_public_event,
)
from .db import get_db, get_setting_int, utc_now
from .payments import checkout_url_for, payment_checkout_status
from .security import (
    derive_access_token,
    derive_activation_token,
    get_client_ip,
    hash_token,
    require_public_csrf,
    safe_user_agent,
)


public_bp = Blueprint("public", __name__)
TAIPEI_TIMEZONE = timezone(timedelta(hours=8))
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _published_ideas():
    return get_db().execute(
        "SELECT * FROM ideas WHERE published = 1 ORDER BY sort_order, id"
    ).fetchall()


def _idea_price(idea):
    if idea["price_override"] is not None:
        return int(idea["price_override"])
    return get_setting_int("idea_price", 199)


def _public_support_contact():
    email = str(current_app.config.get("SUPPORT_EMAIL", "")).strip().lower()
    form_url = str(current_app.config.get("SUPPORT_FORM_URL", "")).strip()
    try:
        parsed = urlparse(form_url)
        valid_form = (
            parsed.scheme == "https"
            and parsed.username is None
            and parsed.password is None
            and (
                (parsed.hostname == "docs.google.com" and parsed.path.startswith("/forms/"))
                or (parsed.hostname == "forms.gle" and len(parsed.path) > 1)
            )
        )
    except ValueError:
        valid_form = False
    ready = bool(EMAIL_PATTERN.fullmatch(email) and valid_form)
    return {
        "ready": ready,
        "email": email if ready else "",
        "form_url": form_url if ready else "",
    }


@public_bp.get("/")
def home():
    ideas = _published_ideas()
    price = get_setting_int("idea_price", 199)
    record_event("page_view", dedupe_scope=datetime.now(timezone.utc).date().isoformat())
    return render_template("home.html", ideas=ideas, global_price=price)


@public_bp.get("/faq")
def faq():
    return render_template("faq.html")


@public_bp.get("/policies")
def policies():
    return render_template("policies.html")


@public_bp.get("/terms")
def terms():
    return redirect(f"{url_for('public.policies')}#terms")


@public_bp.get("/privacy")
def privacy():
    return redirect(f"{url_for('public.policies')}#privacy")


@public_bp.get("/refunds")
def refunds():
    return redirect(f"{url_for('public.policies')}#refunds")


@public_bp.get("/support")
def support():
    return render_template("support.html", support_contact=_public_support_contact())


@public_bp.get("/ideas/<slug>")
def idea_detail(slug):
    idea = get_db().execute(
        "SELECT * FROM ideas WHERE slug = ? AND published = 1", (slug,)
    ).fetchone()
    if idea is None:
        return render_template("message.html", title="此想法尚未開放", message="請回仙策閣查看其他心法。"), 404
    record_event(
        "view_idea",
        idea_id=idea["id"],
        dedupe_scope=public_event_dedupe_scope("view_idea"),
    )
    return render_template("idea_detail.html", idea=idea, price=_idea_price(idea))


@public_bp.get("/checkout/<slug>")
def checkout(slug):
    idea = get_db().execute(
        "SELECT * FROM ideas WHERE slug = ? AND published = 1", (slug,)
    ).fetchone()
    if idea is None:
        return render_template("message.html", title="無法結帳", message="此想法目前未開放。"), 404
    record_event(
        "checkout_opened",
        idea_id=idea["id"],
        dedupe_scope=public_event_dedupe_scope("checkout_opened"),
    )
    return render_template(
        "checkout.html",
        idea=idea,
        price=_idea_price(idea),
        payment_status=payment_checkout_status(),
    )


@public_bp.post("/api/orders")
def create_order():
    csrf_error = require_public_csrf()
    if csrf_error:
        return csrf_error
    data = request.get_json(silent=True) or request.form
    slug = str(data.get("idea_slug", "")).strip()[:100]
    name = str(data.get("customer_name", "")).strip()[:80]
    email = str(data.get("customer_email", "")).strip().lower()[:254]
    purchase_notice_consent = data.get("purchase_notice_consent") is True
    digital_content_consent = data.get("digital_content_consent") is True
    if not EMAIL_PATTERN.fullmatch(email):
        return jsonify({"error": "請輸入有效的 Email"}), 400
    if len(name) < 2:
        return jsonify({"error": "請輸入至少 2 個字的稱呼"}), 400
    if not purchase_notice_consent or not digital_content_consent:
        return jsonify({"error": "請先閱讀並同意付款、開通與數位內容說明"}), 400
    idea = get_db().execute(
        "SELECT * FROM ideas WHERE slug = ? AND published = 1", (slug,)
    ).fetchone()
    if idea is None:
        return jsonify({"error": "此想法目前未開放"}), 404

    payment_status = payment_checkout_status()
    if not payment_status["ready"]:
        return jsonify({"error": "正式付款尚未開放，目前不會建立扣款"}), 503

    local_now = datetime.now(TAIPEI_TIMEZONE)
    order_no = f"TWYB{local_now.strftime('%Y%m%d')}{secrets.token_hex(4).upper()}"
    payment_token = secrets.token_urlsafe(32)
    access_token = derive_access_token(payment_token)
    activation_token = derive_activation_token(order_no)
    amount = _idea_price(idea)
    connection = get_db()
    analytics_sid = ensure_analytics_session()
    cursor = connection.execute(
        """
        INSERT INTO orders
            (order_no, idea_id, customer_name, customer_email, amount, status,
             payment_provider, payment_token_hash, access_token_hash,
             activation_token_hash, analytics_session_id, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)
        """,
        (
            order_no, idea["id"], name, email, amount, payment_status["provider"],
            hash_token(payment_token), hash_token(access_token), hash_token(activation_token),
            analytics_sid, utc_now(),
        ),
    )
    connection.execute(
        """
        INSERT INTO order_consents
            (order_id, terms_version, purchase_notice_consent, digital_content_consent,
             ip, user_agent, accepted_at)
        VALUES (?, '2026-08-30-v29-risk-boundary', 1, 1, ?, ?, ?)
        """,
        (cursor.lastrowid, get_client_ip(), safe_user_agent(), utc_now()),
    )
    record_event(
        "order_created",
        idea_id=idea["id"],
        session_id=analytics_sid,
        dedupe_scope=f"order:{order_no}",
        connection=connection,
        commit=False,
    )
    connection.commit()
    return (
        jsonify(
            {
                "order_no": order_no,
                "amount": amount,
                "checkout_url": checkout_url_for(payment_token),
                "payment_provider": payment_status["provider"],
            }
        ),
        201,
    )


@public_bp.get("/orders/<access_token>")
def order_access(access_token):
    order = get_db().execute(
        """
        SELECT orders.* FROM orders
        WHERE orders.access_token_hash = ?
        """,
        (hash_token(access_token),),
    ).fetchone()
    if order is None:
        return render_template("message.html", title="找不到訂單", message="請確認你的專屬連結是否完整。"), 404
    return redirect(
        url_for(
            "access.activate_page",
            activation_token=derive_activation_token(order["order_no"]),
        )
    )


@public_bp.get("/api/ideas")
def ideas_api():
    ideas = _published_ideas()
    return jsonify(
        {
            "ideas": [
                {
                    "slug": item["slug"],
                    "title": item["public_title"],
                    "public_title": item["public_title"],
                    "primary_vein": item["primary_vein"],
                    "discipline": item["discipline"],
                    "summary": item["summary"],
                    "maturity": item["maturity"],
                    "tags": item["tags"].split(","),
                    "price": _idea_price(item),
                }
                for item in ideas
            ]
        }
    )


@public_bp.post("/api/events")
def analytics_event():
    csrf_error = require_public_csrf()
    if csrf_error:
        return csrf_error
    data = request.get_json(silent=True) or {}
    event_name = str(data.get("event_name", "")).strip()
    event_value = str(data.get("event_value", "")).strip()[:80]
    if not validate_public_event(event_name, event_value):
        return jsonify({"error": "不支援的事件"}), 400
    idea_id = None
    slug = str(data.get("idea_slug", ""))[:100]
    if slug:
        idea = get_db().execute(
            "SELECT id FROM ideas WHERE slug = ? AND published = 1", (slug,)
        ).fetchone()
        if idea:
            idea_id = idea["id"]
    if event_name in IDEA_EVENTS and idea_id is None:
        return jsonify({"error": "找不到仙策"}), 404
    recorded = record_event(
        event_name,
        idea_id=idea_id,
        event_value=event_value,
        dedupe_scope=public_event_dedupe_scope(event_name, event_value),
    )
    if event_name == "interest_registered":
        return jsonify({"recorded": recorded}), 200
    return "", 204
