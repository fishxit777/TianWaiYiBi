from pathlib import Path

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


def test_thirteen_sealed_scrolls_are_published_in_volume_order(app):
    with app.app_context():
        rows = get_db().execute(
            """
            SELECT slug, public_title, title, primary_vein, secondary_vein,
                   paid_content, hero_image, diagram_image, scene_image,
                   sort_order, published
            FROM ideas ORDER BY sort_order
            """
        ).fetchall()

    published = [row for row in rows if row["published"] == 1]
    assert len(published) == 13
    assert [row["sort_order"] for row in published] == list(range(1, 14))
    assert len({row["slug"] for row in published}) == 13
    assert published[0]["slug"] == "sealed-twin-tire-safety"
    assert published[0]["public_title"] == "封印盲策・第壹卷"
    assert published[0]["primary_vein"] == "守護脈"
    assert published[0]["secondary_vein"] == "造物脈"
    assert [row["public_title"] for row in published] == [
        "封印盲策・第壹卷", "封印盲策・第貳卷", "封印盲策・第參卷",
        "封印盲策・第肆卷", "封印盲策・第伍卷", "封印盲策・第陸卷",
        "封印盲策・第柒卷", "封印盲策・第捌卷", "封印盲策・第玖卷",
        "封印盲策・第拾卷", "封印盲策・第拾壹卷", "封印盲策・第拾貳卷",
        "封印盲策・第拾參卷",
    ]
    for row in published[1:]:
        assert row["slug"].startswith("sealed-concept-v")
        assert len(row["paid_content"]) >= 350
        assert all(row[key] for key in ("hero_image", "diagram_image", "scene_image"))


def test_every_new_volume_has_three_compact_webp_assets(app):
    static_root = Path(app.static_folder)
    with app.app_context():
        rows = get_db().execute(
            """
            SELECT hero_image, diagram_image, scene_image
            FROM ideas WHERE published = 1 AND sort_order > 1
            """
        ).fetchall()

    paths = [static_root / row[key] for row in rows for key in ("hero_image", "diagram_image", "scene_image")]
    assert len(paths) == 36
    assert len({path.name for path in paths}) == 36
    for path in paths:
        assert path.name.startswith("v31-")
        assert path.is_file(), path
        assert path.read_bytes()[:4] == b"RIFF"
        assert path.stat().st_size < 700_000


def test_new_public_surfaces_keep_all_true_titles_and_mechanisms_sealed(client, app):
    with app.app_context():
        ideas = get_db().execute(
            "SELECT slug, title, paid_content FROM ideas WHERE published = 1 AND sort_order > 1"
        ).fetchall()

    home = client.get("/").get_data(as_text=True)
    api = str(client.get("/api/ideas").get_json())
    for idea in ideas:
        detail = client.get(f"/ideas/{idea['slug']}")
        body = detail.get_data(as_text=True)
        assert detail.status_code == 200
        assert idea["title"] not in home
        assert idea["title"] not in body
        assert idea["title"] not in api
        assert idea["paid_content"] not in body


def test_revealed_visuals_have_volume_specific_engineering_captions(app):
    template = Path("templates/order_access.html").read_text(encoding="utf-8")

    assert "order['hero_caption']" in template
    assert "order['diagram_caption']" in template
    assert "order['scene_caption']" in template
    with app.app_context():
        rows = get_db().execute(
            """
            SELECT slug, hero_caption, diagram_caption, scene_caption
            FROM ideas WHERE published = 1 AND sort_order > 1
            """
        ).fetchall()

    assert len(rows) == 12
    captions = []
    for row in rows:
        assert all(row[key].strip() for key in ("hero_caption", "diagram_caption", "scene_caption"))
        captions.extend(row[key] for key in ("hero_caption", "diagram_caption", "scene_caption"))
    assert len(set(captions)) == 36


def test_v31_catalog_no_longer_references_ancient_v30_visuals():
    catalog = Path("tianwai/v30_catalog.py").read_text(encoding="utf-8")

    assert "brand/concepts/v30-" not in catalog
    assert catalog.count("brand/concepts/v31-") == 36


def test_mobile_revealed_header_wraps_long_engineering_titles():
    css = Path("static/v31.css").read_text(encoding="utf-8")

    assert ".revealed-scroll .access-header > div" in css
    assert "min-width: 0" in css
    assert "overflow-wrap: anywhere" in css
    assert "grid-template-columns: 52px minmax(0, 1fr)" in css


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
