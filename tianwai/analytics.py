import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from flask import current_app, has_request_context, request, session

from .db import get_db, utc_now


EVENT_VERSION = 1
ALLOWED_WINDOWS = {7, 30, 90}
PUBLIC_EVENT_VALUES = {
    "view_idea": None,
    "checkout_opened": None,
    "line_cta_clicked": None,
    "filter_used": {"all", "品牌", "成長", "自動化", "策略"},
    "reading_depth": {"50", "90"},
    "engaged_read": {"45"},
    "interest_registered": None,
    "conversation_cta_clicked": None,
}
IDEA_EVENTS = {
    "view_idea",
    "checkout_opened",
    "reading_depth",
    "engaged_read",
    "interest_registered",
    "conversation_cta_clicked",
    "conversation_submitted",
    "order_created",
    "purchase_completed",
}
BOT_PATTERN = re.compile(
    r"bot|crawler|spider|slurp|curl|wget|python-requests|uptime|monitor|healthcheck|headless",
    re.IGNORECASE,
)
SEARCH_HOSTS = ("google.", "bing.", "yahoo.", "duckduckgo.", "baidu.")
SOCIAL_HOSTS = (
    "facebook.com",
    "instagram.com",
    "threads.net",
    "linkedin.com",
    "tiktok.com",
    "youtube.com",
    "x.com",
    "twitter.com",
)


def ensure_analytics_session():
    analytics_sid = str(session.get("analytics_sid", "")).strip()
    if not analytics_sid:
        analytics_sid = secrets.token_urlsafe(18)
        session["analytics_sid"] = analytics_sid
    return analytics_sid


def _coarse_source():
    if not has_request_context():
        return "web"
    explicit = str(request.args.get("source", "")).strip().lower()
    if explicit in {"line", "admin-preview"}:
        source = explicit
    else:
        utm_source = str(request.args.get("utm_source", "")).strip().lower()
        utm_medium = str(request.args.get("utm_medium", "")).strip().lower()
        joined = f"{utm_source} {utm_medium}"
        if "email" in joined or "newsletter" in joined:
            source = "email"
        elif any(item in joined for item in ("facebook", "instagram", "threads", "tiktok", "social")):
            source = "social"
        elif any(item in joined for item in ("google", "bing", "search", "organic", "cpc")):
            source = "search"
        else:
            referrer = request.referrer or ""
            referrer_host = (urlparse(referrer).hostname or "").lower()
            request_host = (request.host.split(":", 1)[0] or "").lower()
            if referrer_host and referrer_host != request_host:
                if any(host in referrer_host for host in SEARCH_HOSTS):
                    source = "search"
                elif any(referrer_host.endswith(host) for host in SOCIAL_HOSTS):
                    source = "social"
                else:
                    source = "referral"
            elif referrer_host == request_host:
                source = str(session.get("analytics_source", "web"))
            else:
                source = "direct"
    if source != "admin-preview":
        session["analytics_source"] = source
    return source


def _request_is_automated():
    if not has_request_context():
        return False
    return bool(BOT_PATTERN.search(str(request.user_agent.string or "")))


def _dedupe_key(event_name, idea_id, analytics_sid, scope):
    secret = str(current_app.config.get("SECRET_KEY", "analytics-dedupe"))
    message = "|".join(
        (str(EVENT_VERSION), str(event_name), str(idea_id or ""), str(analytics_sid or ""), str(scope))
    )
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def record_event(
    event_name,
    *,
    idea_id=None,
    event_value="",
    source=None,
    dedupe_scope=None,
    session_id=None,
    page_path=None,
    automated=None,
    connection=None,
    commit=True,
):
    """Record a privacy-minimized first-party event and return whether it was new."""
    if session_id is None and has_request_context():
        session_id = ensure_analytics_session()
    normalized_source = str(source or _coarse_source())[:40]
    normalized_value = str(event_value or "")[:80]
    normalized_path = str(
        page_path if page_path is not None else (request.path if has_request_context() else "")
    )[:120]
    is_automated = _request_is_automated() if automated is None else bool(automated)
    dedupe_key = None
    if dedupe_scope:
        dedupe_key = _dedupe_key(event_name, idea_id, session_id, dedupe_scope)
    database = connection or get_db()
    cursor = database.execute(
        """
        INSERT OR IGNORE INTO analytics_events
            (event_name, idea_id, source, session_id, event_value, event_version,
             dedupe_key, is_automated, page_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(event_name)[:60],
            idea_id,
            normalized_source,
            session_id,
            normalized_value,
            EVENT_VERSION,
            dedupe_key,
            1 if is_automated else 0,
            normalized_path,
            utc_now(),
        ),
    )
    if commit:
        database.commit()
    return cursor.rowcount > 0


def validate_public_event(event_name, event_value):
    allowed_values = PUBLIC_EVENT_VALUES.get(event_name, "unsupported")
    if allowed_values == "unsupported":
        return False
    if allowed_values is None:
        return event_value == ""
    return event_value in allowed_values


def public_event_dedupe_scope(event_name, event_value=""):
    day = datetime.now(timezone.utc).date().isoformat()
    if event_name in {"view_idea", "checkout_opened", "filter_used", "line_cta_clicked", "conversation_cta_clicked"}:
        return f"{day}:{event_value}"
    if event_name in {"reading_depth", "engaged_read", "interest_registered"}:
        return event_value or event_name
    return None


def _rate(numerator, denominator):
    return round((int(numerator or 0) / max(int(denominator or 0), 1)) * 100, 1)


def _confidence(visitors):
    if visitors < 10:
        return {"level": "insufficient", "label": "資料不足", "note": "少於 10 位有效訪客，不下營運結論"}
    if visitors < 30:
        return {"level": "exploratory", "label": "探索級", "note": "可觀察現象，不代表需求已成立"}
    if visitors < 100:
        return {"level": "directional", "label": "方向級", "note": "可用於排序下一個驗證動作"}
    return {"level": "stable", "label": "穩定級", "note": "樣本較穩定，仍須以詢問與付款交叉驗證"}


def _evidence_index(funnel, payment_ready):
    visitors = int(funnel["visitors"] or 0)
    if visitors < 10:
        return None
    reach = min(visitors / 30, 1)
    rates = {
        "read_50": min(funnel["read_50"] / visitors, 1),
        "engaged": min(funnel["engaged"] / visitors, 1),
        "interest": min(funnel["interest"] / visitors, 1),
        "conversations": min(funnel["conversations"] / visitors, 1),
        "checkout": min(funnel["checkout"] / visitors, 1),
        "orders": min(funnel["orders"] / visitors, 1),
        "paid": min(funnel["paid"] / visitors, 1),
    }
    if payment_ready:
        score = (
            reach * 10
            + rates["read_50"] * 15
            + rates["engaged"] * 15
            + rates["interest"] * 15
            + rates["conversations"] * 10
            + rates["checkout"] * 10
            + rates["orders"] * 10
            + rates["paid"] * 15
        )
    else:
        score = (
            reach * 20
            + rates["read_50"] * 20
            + rates["engaged"] * 20
            + rates["interest"] * 25
            + rates["conversations"] * 15
        )
    return round(min(score, 100), 1)


def _stage(funnel):
    if funnel["paid"]:
        return "paid", "已有付款證據"
    if funnel["orders"]:
        return "ordered", "已建立訂單"
    if funnel["checkout"]:
        return "checkout", "進入結帳"
    if funnel["interest"] or funnel["conversations"]:
        return "intent", "出現主動意願"
    if funnel["engaged"]:
        return "engaged", "出現有效閱讀"
    if funnel["visitors"]:
        return "observed", "已有瀏覽"
    return "empty", "尚無資料"


def _diagnosis(funnel, payment_ready, confidence):
    visitors = funnel["visitors"]
    read_50 = funnel["read_50"]
    engaged = funnel["engaged"]
    intent = funnel["interest"] + funnel["conversations"]
    if confidence["level"] == "insufficient":
        return {
            "code": "insufficient_sample",
            "title": "先收集，不下結論",
            "evidence": f"有效訪客 {visitors} 位；最低判讀門檻為 10 位",
            "action": "繼續導入目標客戶，暫不改價格或內容方向。",
        }
    if _rate(read_50, visitors) < 35:
        return {
            "code": "opening_dropoff",
            "title": "摘要前段留不住人",
            "evidence": f"50% 閱讀 {read_50} / {visitors}（{_rate(read_50, visitors)}%）",
            "action": "先改成果承諾與公開摘要前兩段，只測一個版本差異。",
        }
    if read_50 >= 5 and _rate(engaged, read_50) < 45:
        return {
            "code": "depth_dropoff",
            "title": "中段價值不足或篇幅失衡",
            "evidence": f"有效讀完 {engaged} / 50% 閱讀 {read_50}（{_rate(engaged, read_50)}%）",
            "action": "補具體範例、交付清單與判斷工具，刪除不能推進決策的段落。",
        }
    if engaged >= 5 and intent == 0:
        return {
            "code": "intent_gap",
            "title": "有人讀完，但沒有主動意願",
            "evidence": f"有效閱讀 {engaged} 位；意願與傳音皆為 0",
            "action": "把交付結果與「適合誰」說得更具體，保留單一低摩擦意願按鈕。",
        }
    if not payment_ready:
        if intent >= 3:
            return {
                "code": "prelaunch_signal",
                "title": "累積到可訪談的前置信號",
                "evidence": f"主動意願與傳音合計 {intent} 位；正式收款仍關閉",
                "action": "優先訪談這一策的目標客戶，確認交付內容與願付價格，不先開收款。",
            }
        return {
            "code": "collecting_prelaunch",
            "title": "閱讀成立，繼續收集意願",
            "evidence": f"有效閱讀 {engaged} 位；主動意願與傳音合計 {intent} 位",
            "action": "維持摘要，增加合格目標訪客；達 3 位主動意願後進行訪談。",
        }
    if funnel["checkout"] >= 5 and _rate(funnel["orders"], funnel["checkout"]) < 40:
        return {
            "code": "checkout_friction",
            "title": "結帳頁出現明顯流失",
            "evidence": f"建單 {funnel['orders']} / 結帳 {funnel['checkout']}（{_rate(funnel['orders'], funnel['checkout'])}%）",
            "action": "檢查價格、交付、退款與表單摩擦；一次只修改一項。",
        }
    if funnel["orders"] >= 5 and _rate(funnel["paid"], funnel["orders"]) < 50:
        return {
            "code": "payment_friction",
            "title": "建單後付款流失",
            "evidence": f"付款 {funnel['paid']} / 建單 {funnel['orders']}（{_rate(funnel['paid'], funnel['orders'])}%）",
            "action": "優先檢查付款失敗、信任說明與付款方式，不先改商品內容。",
        }
    return {
        "code": "healthy_signal",
        "title": "漏斗暫無單一明顯瓶頸",
        "evidence": f"有效閱讀 {engaged} 位；意願 {intent} 位；付款 {funnel['paid']} 位",
        "action": "繼續累積樣本並只測一個變數，避免同時改標題、內容與價格。",
    }


def _period_aggregates(connection, start, end):
    rows = connection.execute(
        """
        SELECT idea_id, event_name, event_value,
               COUNT(*) AS event_count,
               COUNT(DISTINCT CASE WHEN session_id IS NOT NULL AND session_id <> '' THEN session_id END) AS sessions
        FROM analytics_events
        WHERE idea_id IS NOT NULL AND created_at >= ? AND created_at < ?
          AND is_automated = 0 AND source <> 'admin-preview'
        GROUP BY idea_id, event_name, event_value
        """,
        (start, end),
    ).fetchall()
    aggregates = {}
    for row in rows:
        key = (int(row["idea_id"]), str(row["event_name"]), str(row["event_value"] or ""))
        aggregates[key] = int(row["sessions"] or 0)
    engaged_rows = connection.execute(
        """
        SELECT idea_id, COUNT(DISTINCT session_id) AS sessions
        FROM analytics_events
        WHERE idea_id IS NOT NULL AND session_id IS NOT NULL AND session_id <> ''
          AND created_at >= ? AND created_at < ?
          AND is_automated = 0 AND source <> 'admin-preview'
          AND (event_name = 'engaged_read'
               OR (event_name = 'reading_depth' AND event_value = '90'))
        GROUP BY idea_id
        """,
        (start, end),
    ).fetchall()
    engaged = {int(row["idea_id"]): int(row["sessions"] or 0) for row in engaged_rows}
    return aggregates, engaged


def _aggregate_value(aggregates, idea_id, event_name, event_value=""):
    return int(aggregates.get((int(idea_id), event_name, event_value), 0))


def build_demand_radar(connection=None, *, days=30, now=None, payment_ready=False):
    database = connection or get_db()
    try:
        requested_days = int(days)
    except (TypeError, ValueError):
        requested_days = 30
    days = requested_days if requested_days in ALLOWED_WINDOWS else 30
    end_dt = now or datetime.now(timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)
    end_dt = (end_dt + timedelta(seconds=1)).replace(microsecond=0)
    start_dt = end_dt - timedelta(days=days)
    previous_start_dt = start_dt - timedelta(days=days)
    current, current_engaged = _period_aggregates(
        database, start_dt.isoformat(timespec="seconds"), end_dt.isoformat(timespec="seconds")
    )
    previous, _previous_engaged = _period_aggregates(
        database,
        previous_start_dt.isoformat(timespec="seconds"),
        start_dt.isoformat(timespec="seconds"),
    )
    ideas = database.execute(
        "SELECT id, slug, title, role, published, sort_order FROM ideas ORDER BY sort_order, id"
    ).fetchall()
    items = []
    for idea in ideas:
        idea_id = int(idea["id"])
        funnel = {
            "visitors": _aggregate_value(current, idea_id, "view_idea"),
            "read_50": _aggregate_value(current, idea_id, "reading_depth", "50"),
            "read_90": _aggregate_value(current, idea_id, "reading_depth", "90"),
            "engaged": int(current_engaged.get(idea_id, 0)),
            "interest": _aggregate_value(current, idea_id, "interest_registered"),
            "conversation_clicks": _aggregate_value(current, idea_id, "conversation_cta_clicked"),
            "conversations": _aggregate_value(current, idea_id, "conversation_submitted"),
            "checkout": _aggregate_value(current, idea_id, "checkout_opened"),
            "orders": _aggregate_value(current, idea_id, "order_created"),
            "paid": _aggregate_value(current, idea_id, "purchase_completed"),
        }
        previous_visitors = _aggregate_value(previous, idea_id, "view_idea")
        confidence = _confidence(funnel["visitors"])
        stage_key, stage_label = _stage(funnel)
        trend_percent = None
        if previous_visitors > 0:
            trend_percent = round(((funnel["visitors"] - previous_visitors) / previous_visitors) * 100, 1)
        items.append(
            {
                "slug": idea["slug"],
                "title": idea["title"],
                "role": idea["role"],
                "published": bool(idea["published"]),
                "funnel": funnel,
                "rates": {
                    "read_50": _rate(funnel["read_50"], funnel["visitors"]),
                    "engaged": _rate(funnel["engaged"], funnel["visitors"]),
                    "interest": _rate(funnel["interest"] + funnel["conversations"], funnel["visitors"]),
                    "checkout": _rate(funnel["checkout"], funnel["visitors"]),
                    "paid": _rate(funnel["paid"], funnel["visitors"]),
                },
                "confidence": confidence,
                "evidence_index": _evidence_index(funnel, payment_ready),
                "stage": {"key": stage_key, "label": stage_label},
                "diagnosis": _diagnosis(funnel, payment_ready, confidence),
                "trend": {
                    "current_visitors": funnel["visitors"],
                    "previous_visitors": previous_visitors,
                    "percent": trend_percent,
                    "direction": (
                        "new"
                        if previous_visitors == 0 and funnel["visitors"] > 0
                        else ("up" if trend_percent and trend_percent > 0 else ("down" if trend_percent and trend_percent < 0 else "flat"))
                    ),
                },
            }
        )
    quality = database.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN is_automated = 1 THEN 1 ELSE 0 END) AS automated,
               SUM(CASE WHEN source = 'admin-preview' THEN 1 ELSE 0 END) AS admin_preview,
               SUM(CASE WHEN session_id IS NULL OR session_id = '' THEN 1 ELSE 0 END) AS missing_session,
               COUNT(DISTINCT CASE WHEN is_automated = 0 AND source <> 'admin-preview' THEN session_id END) AS usable_sessions
        FROM analytics_events WHERE created_at >= ? AND created_at < ?
        """,
        (start_dt.isoformat(timespec="seconds"), end_dt.isoformat(timespec="seconds")),
    ).fetchone()
    ranked = [
        item
        for item in items
        if item["evidence_index"] is not None
        and item["confidence"]["level"] in {"directional", "stable"}
    ]
    ranked.sort(key=lambda item: (-item["evidence_index"], -item["funnel"]["visitors"], item["title"]))
    return {
        "window_days": days,
        "period_start": start_dt.date().isoformat(),
        "period_end": end_dt.date().isoformat(),
        "payment_ready": bool(payment_ready),
        "items": items,
        "leader": ranked[0]["slug"] if ranked else None,
        "data_quality": {
            "total_events": int(quality["total"] or 0),
            "automated_excluded": int(quality["automated"] or 0),
            "admin_preview_excluded": int(quality["admin_preview"] or 0),
            "missing_session": int(quality["missing_session"] or 0),
            "usable_sessions": int(quality["usable_sessions"] or 0),
        },
        "method": {
            "event_version": EVENT_VERSION,
            "minimum_sample": 10,
            "stable_sample": 100,
            "claim": "需求證據指數，不是購買機率",
        },
    }
