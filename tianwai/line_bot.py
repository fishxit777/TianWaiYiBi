import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request

from flask import Blueprint, current_app, has_request_context, jsonify, render_template, request

from .db import get_db, get_setting_int, utc_now
from .security import log_security_event, require_public_csrf


line_bp = Blueprint("line", __name__)

ACCENT_COLORS = {
    "cinnabar": "#C95045",
    "jade": "#348F8A",
    "gold": "#A98235",
    "azure": "#397A98",
    "violet": "#6254A5",
    "silver": "#687A84",
}


def line_signature_valid(raw_body, supplied):
    secret = os.environ.get("LINE_CHANNEL_SECRET", "")
    if not secret or not supplied:
        return False
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, supplied)


def _published_ideas():
    return get_db().execute(
        """
        SELECT slug, title, role, seal, discipline, summary, accent, price_override
        FROM ideas WHERE published = 1 ORDER BY sort_order, id
        """
    ).fetchall()


def _idea_price(idea, global_price):
    return int(idea["price_override"] if idea["price_override"] is not None else global_price)


def _public_base_url():
    configured = os.environ.get("BASE_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    if has_request_context():
        return request.url_root.rstrip("/")
    return "http://127.0.0.1:5088"


def _catalog_text(ideas):
    listing = "\n".join(
        f"{index}.【{idea['seal']}】{idea['role']}｜{idea['title']}" for index, idea in enumerate(ideas, 1)
    )
    return f"六脈仙策已開閣：\n{listing}\n\n點下卡片可看公開摘要，或直接回覆 1～{len(ideas)}。"


def _idea_flex_bubble(idea, index, global_price, base_url):
    accent = ACCENT_COLORS.get(idea["accent"], ACCENT_COLORS["jade"])
    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "18px",
            "backgroundColor": accent,
            "contents": [
                {"type": "text", "text": f"第 {index} 脈・{idea['seal']}", "color": "#F8F0DD", "size": "xs"},
                {
                    "type": "text", "text": idea["role"], "color": "#FFFFFF", "size": "lg",
                    "weight": "bold", "margin": "sm", "wrap": True,
                },
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "18px",
            "contents": [
                {"type": "text", "text": idea["title"], "weight": "bold", "size": "xl", "wrap": True},
                {
                    "type": "text", "text": idea["discipline"], "color": "#766E86", "size": "xs",
                    "margin": "sm", "wrap": True,
                },
                {
                    "type": "text", "text": idea["summary"][:110], "color": "#4D4A58", "size": "sm",
                    "margin": "md", "wrap": True,
                },
                {
                    "type": "text", "text": f"NT${_idea_price(idea, global_price)}・一次解鎖",
                    "color": "#9B493E", "size": "sm", "weight": "bold", "margin": "lg",
                },
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "14px",
            "contents": [{
                "type": "button",
                "style": "primary",
                "height": "sm",
                "color": "#292652",
                "action": {
                    "type": "uri",
                    "label": "翻閱免費摘要",
                    "uri": f"{base_url}/ideas/{idea['slug']}?source=line",
                },
            }],
        },
    }


def build_messages(message, event_type="message"):
    text = str(message or "").strip().lower()
    price = get_setting_int("idea_price", 199)
    ideas = _published_ideas()
    base_url = _public_base_url()

    if event_type == "follow":
        return [
            {
                "type": "text",
                "text": "歡迎來到天外一筆・仙策閣。這裡把天馬行空的想法煉成可執行心法。回覆『靈感』看六脈仙策，回覆『價格』看統一試行價。",
            }
        ]
    if any(keyword in text for keyword in ("價格", "多少", "price")):
        return [{
            "type": "text",
            "text": f"目前六脈仙策統一試行價 NT${price}／份。每份皆為一次買斷的數位心法；正式金流上線前，本機測試不會真的扣款。",
        }]
    if any(keyword in text for keyword in ("靈感", "想法", "仙策", "目錄", "menu")):
        return [
            {"type": "text", "text": _catalog_text(ideas)},
            {
                "type": "flex",
                "altText": "天外一筆六脈仙策導覽",
                "contents": {
                    "type": "carousel",
                    "contents": [
                        _idea_flex_bubble(idea, index, price, base_url)
                        for index, idea in enumerate(ideas, 1)
                    ],
                },
            },
        ]
    if text.isdigit() and 1 <= int(text) <= len(ideas):
        idea = ideas[int(text) - 1]
        return [
            {"type": "text", "text": f"你選的是第 {text} 脈：{idea['role']}。這一脈專治「{idea['discipline']}」。"},
            {
                "type": "flex",
                "altText": f"{idea['role']}｜{idea['title']}",
                "contents": _idea_flex_bubble(idea, int(text), price, base_url),
            },
        ]
    if any(keyword in text for keyword in ("開始", "說明", "幫助", "help", "你好", "哈囉")):
        return [{
            "type": "text",
            "text": "可用指令：\n・靈感：查看六脈仙策卡片\n・價格：查看目前統一試行價\n・1～6：查看單一仙策\n・說明：再次查看這份指令表",
        }]
    return [{
        "type": "text",
        "text": "我還沒辨識這句。你可以回覆『靈感』看六脈仙策、回覆『價格』，或直接輸入 1～6。",
    }]


def build_reply(message):
    """Plain-text compatibility view used by tests and non-Flex clients."""
    parts = []
    for item in build_messages(message):
        parts.append(item.get("text") or item.get("altText") or "")
    return "\n\n".join(part for part in parts if part)


def send_line_reply(reply_token, messages):
    access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not access_token or not reply_token:
        return False
    body = json.dumps({"replyToken": reply_token, "messages": messages[:5]}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/reply",
        data=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError):
        current_app.logger.exception("LINE reply failed")
        return False


@line_bp.post("/line/webhook")
def webhook():
    raw_body = request.get_data(cache=True)
    if not line_signature_valid(raw_body, request.headers.get("X-Line-Signature", "")):
        log_security_event("line_signature_mismatch", "critical", "rejected", "invalid_signature")
        return jsonify({"error": "簽章驗證失敗"}), 401
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict) or not isinstance(payload.get("events", []), list):
        log_security_event("line_payload_invalid", "medium", "rejected", "invalid_json_shape")
        return jsonify({"error": "LINE 事件格式不正確"}), 400
    processed = 0
    connection = get_db()
    for event in payload.get("events", [])[:20]:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("webhookEventId", ""))[:120]
        event_type = str(event.get("type", "unknown"))[:40]
        if not event_id:
            continue
        exists = connection.execute("SELECT 1 FROM line_events WHERE event_id = ?", (event_id,)).fetchone()
        if exists:
            continue
        connection.execute(
            "INSERT INTO line_events (event_id, event_type, created_at) VALUES (?, ?, ?)",
            (event_id, event_type, utc_now()),
        )
        connection.commit()
        if event_type == "message" and event.get("message", {}).get("type") == "text":
            messages = build_messages(event["message"].get("text", ""))
            send_line_reply(str(event.get("replyToken", "")), messages)
        elif event_type == "follow":
            send_line_reply(str(event.get("replyToken", "")), build_messages("", event_type="follow"))
        processed += 1
    return jsonify({"ok": True, "processed": processed})


@line_bp.get("/dev/line")
def simulator_page():
    if not current_app.config.get("TESTING") and os.environ.get("ENABLE_DEV_TOOLS", "").lower() not in {
        "1", "true", "yes", "on"
    }:
        return "", 404
    return render_template("line_simulator.html")


@line_bp.post("/dev/line/reply")
def simulator_reply():
    if not current_app.config.get("TESTING") and os.environ.get("ENABLE_DEV_TOOLS", "").lower() not in {
        "1", "true", "yes", "on"
    }:
        return "", 404
    csrf_error = require_public_csrf()
    if csrf_error:
        return csrf_error
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", ""))[:200]
    messages = build_messages(message)
    cards = []
    for item in messages:
        if item.get("type") != "flex":
            continue
        contents = item.get("contents", {})
        bubbles = contents.get("contents", []) if contents.get("type") == "carousel" else [contents]
        for bubble in bubbles:
            header = bubble.get("header", {})
            body = bubble.get("body", {})
            header_text = [part.get("text", "") for part in header.get("contents", [])]
            body_text = [part.get("text", "") for part in body.get("contents", [])]
            action = (bubble.get("footer", {}).get("contents") or [{}])[0].get("action", {})
            cards.append({
                "eyebrow": header_text[0] if header_text else "仙策",
                "role": header_text[1] if len(header_text) > 1 else "",
                "title": body_text[0] if body_text else "",
                "summary": body_text[2] if len(body_text) > 2 else "",
                "price": body_text[3] if len(body_text) > 3 else "",
                "url": action.get("uri", ""),
                "color": header.get("backgroundColor", ACCENT_COLORS["jade"]),
            })
    return jsonify({"reply": build_reply(message), "messages": messages, "cards": cards})
