"""Private price preparation and the shared, fail-closed per-volume sale gate.

Prepared prices are database data only. Public projections never include them
until the owner explicitly moves the volume into a price-visible state.
"""

from .ideas import publication_gaps


SALE_STATES = frozenset({"preparing", "price_listed", "for_sale"})
PRICING_BATCH_SLUGS = (
    "sealed-twin-tire-safety",
    *(f"sealed-concept-v{number:02d}" for number in range(2, 14)),
)


def valid_prepared_price(value):
    return type(value) is int and 1 <= value <= 100000


def commerce_status(idea, payment_status, *, private=False):
    """Return one authoritative gate for catalogue, checkout and order creation."""
    idea = dict(idea)
    state = idea.get("sale_state", "preparing")
    if state not in SALE_STATES:
        state = "preparing"
    price = idea.get("prepared_price")
    valid_price = valid_prepared_price(price)
    published = idea.get("published") == 1
    ready = idea.get("release_ready") == 1
    gaps = publication_gaps(idea)
    visible = bool(published and state in {"price_listed", "for_sale"} and valid_price)
    payment_ready = bool(payment_status.get("ready"))
    result = {
        "sale_state": state,
        "price_visible": visible,
        "can_purchase": bool(
            visible and state == "for_sale" and ready and not gaps and payment_ready
        ),
    }
    if visible:
        result["price"] = price
    if private:
        result.update(
            prepared_price=price,
            release_ready=ready,
            in_pricing_batch=idea.get("slug") in PRICING_BATCH_SLUGS,
            global_checkout_enabled=payment_ready,
            payment_ready=payment_ready,
            public_sales_open=bool(payment_status.get("public_sales_open")),
            publication_gaps=gaps,
        )
    return result


def public_idea(idea, payment_status):
    """Allowlist the fields templates need; keep preparation and content private."""
    source = dict(idea)
    fields = (
        "id", "slug", "public_title", "role", "seal", "discipline",
        "primary_vein", "secondary_vein", "maturity", "summary", "teaser",
        "deliverables", "tags", "accent", "sort_order", "published",
    )
    result = {field: source[field] for field in fields}
    result["commerce"] = commerce_status(source, payment_status)
    return result


def private_commerce_payload(idea, payment_status):
    source = dict(idea)
    sections = str(source.get("paid_content") or "").replace("\r\n", "\n").split("\n\n")
    limitations = [
        section.strip() for section in sections
        if any(term in section.split("\n", 1)[0] for term in ("限制", "未知", "安全邊界", "風險邊界"))
    ]
    return {
        "ok": True,
        "commerce": commerce_status(source, payment_status, private=True),
        "preview": {
            "deliverables": source.get("deliverables", ""),
            "maturity": source.get("maturity", ""),
            "limitations": "\n\n".join(limitations) or "請在完整內容編輯器確認限制、未知及安全邊界。",
        },
    }


def validate_commerce_update(data, idea):
    """Validate without mutating or embedding submitted price data in errors."""
    if not isinstance(data, dict) or set(data) - {
        "prepared_price", "sale_state", "release_ready", "confirm_publication",
    }:
        return "請提供有效的銷售準備資料", 400
    if not {"prepared_price", "sale_state", "release_ready"}.issubset(data):
        return "請提供完整的銷售準備欄位", 400
    price = data["prepared_price"]
    if price is not None and not valid_prepared_price(price):
        return "預備價格必須是 NT$1 至 NT$100,000 的整數或留空", 400
    state = data["sale_state"]
    if not isinstance(state, str) or state not in SALE_STATES:
        return "銷售狀態不正確", 400
    if type(data["release_ready"]) is not bool or type(data.get("confirm_publication", False)) is not bool:
        return "交付檢查與公開確認必須是布林值", 400
    if state != "preparing":
        if not valid_prepared_price(price):
            return "公開價格前請先設定有效的預備價格", 409
        if data.get("confirm_publication") is not True:
            return "顯示價格或開賣前，請明確確認本次公開操作", 409
    if state == "for_sale":
        if not data["release_ready"]:
            return "開賣前請完成人工交付與營運檢查", 409
        gaps = publication_gaps(dict(idea))
        if gaps:
            return "開賣前仍缺少：" + "、".join(gaps), 409
        if not idea["published"]:
            return "請先完成公開卷面發布，再設定開賣", 409
    return None


def lock_commerce(connection):
    """Serialize price/state changes with the point-in-time order snapshot."""
    if getattr(connection, "backend", "sqlite") == "postgresql":
        connection.execute("SELECT pg_advisory_xact_lock(1415006530, 37)")
    elif not connection.in_transaction:
        connection.execute("BEGIN IMMEDIATE")
