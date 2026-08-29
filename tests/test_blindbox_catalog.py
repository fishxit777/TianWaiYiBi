from tianwai.db import get_db
from tianwai.ideas import classify_idea, publication_gaps


def test_classifier_uses_customer_value_before_implementation_medium():
    result = classify_idea("可拆分式雙輪胎，爆胎後由另一輪暫時支撐，降低路邊車禍風險")

    assert result["primary_vein"] == "守護脈"
    assert result["secondary_vein"] == "造物脈"
    assert result["confidence"] >= 80


def test_classifier_recognizes_software_automation():
    result = classify_idea("用 AI 與資料自動化整理網站訂單的軟體系統")

    assert result["primary_vein"] == "靈機脈"
    assert result["secondary_vein"] == "破局脈"


def test_first_sealed_scroll_is_the_only_published_seed(app):
    with app.app_context():
        rows = get_db().execute(
            "SELECT slug, public_title, title, primary_vein, secondary_vein, published FROM ideas ORDER BY id"
        ).fetchall()

    published = [row for row in rows if row["published"] == 1]
    assert len(published) == 1
    assert published[0]["slug"] == "sealed-twin-tire-safety"
    assert published[0]["public_title"] == "封印盲策・第壹卷"
    assert published[0]["primary_vein"] == "守護脈"
    assert published[0]["secondary_vein"] == "造物脈"


def test_public_surfaces_never_reveal_paid_title_or_mechanism(client, app):
    with app.app_context():
        idea = get_db().execute(
            "SELECT title, paid_content FROM ideas WHERE slug = ?",
            ("sealed-twin-tire-safety",),
        ).fetchone()
        secret_title = idea["title"]
        secret_mechanism = "兩個並列、可獨立維持基本形狀與承載"

    for path in ("/", "/ideas/sealed-twin-tire-safety", "/checkout/sealed-twin-tire-safety"):
        body = client.get(path).get_data(as_text=True)
        assert secret_title not in body
        assert secret_mechanism not in body

    payload = client.get("/api/ideas").get_json()
    serialized = str(payload)
    assert secret_title not in serialized
    assert secret_mechanism not in serialized
    assert payload["ideas"][0]["title"] == "封印盲策・第壹卷"


def test_publication_rules_block_empty_buyer_content():
    gaps = publication_gaps({"public_title": "封印盲策・草稿"})

    assert "真實標題" in gaps
    assert "拆封後完整內容" in gaps
    assert "主視覺" in gaps


def test_retired_conversation_routes_and_assets_are_not_exposed(client):
    assert client.get("/api/conversations/idea-activity").status_code == 404
    assert client.post("/api/conversations/messages", json={}).status_code == 404
    detail = client.get("/ideas/sealed-twin-tire-safety").get_data(as_text=True)
    home = client.get("/").get_data(as_text=True)

    assert "conversations.js" not in detail
    assert "turnstile" not in detail.lower()
    assert "公開留言" not in detail
    assert "匿名留言" not in home

