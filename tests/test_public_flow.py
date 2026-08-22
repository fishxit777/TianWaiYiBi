import re
from pathlib import Path

from conftest import set_public_csrf


def create_order(client, slug="brand-world-forge"):
    csrf = set_public_csrf(client)
    response = client.post(
        "/api/orders",
        json={
            "idea_slug": slug,
            "customer_name": "測試旅人",
            "customer_email": "traveler@example.com",
            "purchase_notice_consent": True,
            "digital_content_consent": True,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201
    return response.get_json()


def test_home_lists_six_distinct_cultivators(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "仙策閣" in response.get_data(as_text=True)
    assert "brand/home-title-xianxia-v14.webp" in response.get_data(as_text=True)
    assert "brand/wordmark-xianxia-v14.webp" in response.get_data(as_text=True)
    assert "brand/website-hero-v15.webp" in response.get_data(as_text=True)
    assert "static/v15.css" in response.get_data(as_text=True)
    assert "world-chapter-mark" in response.get_data(as_text=True)
    assert "續入下一卷" in response.get_data(as_text=True)
    assert response.get_data(as_text=True).count('fetchpriority="high"') >= 5
    assert response.get_data(as_text=True).count("idea-card") >= 6
    for role in ("破局劍修", "造境符師", "增長丹師", "機關偃師", "回聲樂修", "觀星策士"):
        assert role in response.get_data(as_text=True)


def test_home_hides_internal_tools_and_offers_human_transmission(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    for private_label in ("Logo 評估", "管理後台", "開啟本機模擬器", "LINE Bot"):
        assert private_label not in body
    assert "/logo-review" not in body
    assert "/dev/line" not in body
    assert "/admin" not in body
    assert "傳音給守閣者" in body
    assert "由守閣者本人親自接續" in body
    assert 'href="/transmission"' in body
    assert "line.me/R/ti/p" not in body


def test_transmission_landing_keeps_line_white_page_behind_branded_experience(client):
    response = client.get("/transmission")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "一印傳音" in body
    assert "一筆啟月門" in body
    assert "brand/transmission-title-xianxia-v14.webp" in body
    assert "brand/wordmark-xianxia-v14.webp" in body
    assert body.count('fetchpriority="high"') >= 4
    assert "守閣之誓" in body
    assert "守閣者本人親自接續" in body
    assert "不索取密碼與驗證碼" in body
    assert "brand/line-add-qr.svg" in body
    assert "https://line.me/R/ti/p/%40279plitu" in body
    assert "啟動傳音法陣" in body
    assert 'data-copy-line-id="@279plitu"' in body
    assert "fonts/tianwai-masa-regular.woff2" in body
    assert "fonts/tianwai-masa-bold.woff2" in body
    for private_label in ("Logo 評估", "管理後台", "開啟本機模擬器", "LINE Bot"):
        assert private_label not in body


def test_all_customer_pages_share_the_sitewide_brush_shell(client):
    for path in (
        "/",
        "/transmission",
        "/ideas/brand-world-forge",
        "/checkout/brand-world-forge",
        "/orders/not-a-real-token",
    ):
        body = client.get(path).get_data(as_text=True)
        assert 'class="public-site ' in body
        assert "fonts/tianwai-masa-regular.woff2" in body
        assert "fonts/tianwai-masa-bold.woff2" in body


def test_internal_line_simulator_does_not_use_public_brand_font_shell(client):
    body = client.get("/dev/line").get_data(as_text=True)

    assert 'class="internal-tool-site line-page"' in body
    assert "fonts/tianwai-masa" not in body


def test_public_site_self_hosts_vector_brush_fonts():
    project_root = Path(__file__).resolve().parents[1]
    font_paths = (
        project_root / "static" / "fonts" / "tianwai-masa-regular.woff2",
        project_root / "static" / "fonts" / "tianwai-masa-bold.woff2",
    )

    for font_path in font_paths:
        data = font_path.read_bytes()
        assert data[:4] == b"wOF2"
        assert 100_000 < len(data) < 350_000

    assert not (project_root / "static" / "fonts" / "tianwai-masa-medium.woff2").exists()

    stylesheet = (project_root / "static" / "styles.css").read_text(encoding="utf-8")
    assert 'font-family: "Tianwai Masa"' in stylesheet
    assert 'font-family: "Tianwai Masa Display"' in stylesheet
    assert "--title-page-size" in stylesheet
    assert "--title-section-size" in stylesheet
    assert "--title-card-size" in stylesheet
    assert "--body-readable-size: 18px" in stylesheet
    assert "--lead-readable-size: 19px" in stylesheet
    assert "--meta-readable-size: 13px" in stylesheet
    assert "-webkit-font-smoothing: auto" in stylesheet
    assert ".public-site .brand-copy small" in stylesheet
    assert "font-size: 12px" in stylesheet
    assert ".public-site .brand-wordmark" in stylesheet
    assert ".public-site .hero-title-image-heading" in stylesheet
    assert "-webkit-text-stroke" in stylesheet
    assert "tianwai-brush-display.woff2" not in stylesheet
    assert "tianwai-wenkai-body.woff2" not in stylesheet


def test_xianxia_title_art_is_web_optimized_and_versioned():
    project_root = Path(__file__).resolve().parents[1]
    assets = (
        project_root / "static" / "brand" / "wordmark-xianxia-v14.webp",
        project_root / "static" / "brand" / "home-title-xianxia-v14.webp",
        project_root / "static" / "brand" / "transmission-title-xianxia-v14.webp",
    )

    for asset in assets:
        data = asset.read_bytes()
        assert data[:4] == b"RIFF"
        assert data[8:12] == b"WEBP"
        assert len(data) < 650_000

    v15_hero = project_root / "static" / "brand" / "website-hero-v15.webp"
    hero_data = v15_hero.read_bytes()
    assert hero_data[:4] == b"RIFF"
    assert hero_data[8:12] == b"WEBP"
    assert len(hero_data) < 300_000

    v15_stylesheet = (project_root / "static" / "v15.css").read_text(encoding="utf-8")
    assert "One cinematic scene" in v15_stylesheet
    assert ".home-page .hero-art" in v15_stylesheet
    assert "grid-template-columns: repeat(12" in v15_stylesheet
    assert "@media (max-width: 480px)" in v15_stylesheet
    for creed_color in ("#a5433a", "#2f8177", "#685493", "#a5782f"):
        assert creed_color in v15_stylesheet


def test_logo_review_is_not_a_public_route(client):
    response = client.get("/logo-review")

    assert response.status_code == 404


def test_idea_detail_uses_global_price(client):
    response = client.get("/ideas/brand-world-forge")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "造境符師" in body
    assert "NT$199" in body
    assert "完整心法需解鎖" in body


def test_order_rejects_invalid_email(client):
    csrf = set_public_csrf(client)
    response = client.post(
        "/api/orders",
        json={"idea_slug": "brand-world-forge", "customer_name": "A", "customer_email": "bad"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "請輸入有效的 Email"


def test_order_requires_explicit_payment_and_digital_content_consents(client):
    csrf = set_public_csrf(client)
    response = client.post(
        "/api/orders",
        json={
            "idea_slug": "brand-world-forge",
            "customer_name": "測試旅人",
            "customer_email": "traveler@example.com",
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    assert "付款、開通與數位內容說明" in response.get_json()["error"]


def test_mock_payment_requires_one_time_activation_before_paid_content(client):
    order = create_order(client)
    payment_page = client.get(order["checkout_url"])
    assert payment_page.status_code == 200
    assert "本機模擬付款" in payment_page.get_data(as_text=True)

    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', payment_page.get_data(as_text=True))
    token_match = re.search(r'name="payment_token" value="([^"]+)"', payment_page.get_data(as_text=True))
    assert csrf_match and token_match

    paid = client.post(
        "/pay/mock/complete",
        data={"csrf_token": csrf_match.group(1), "payment_token": token_match.group(1)},
        follow_redirects=True,
    )

    assert paid.status_code == 200
    body = paid.get_data(as_text=True)
    assert "付款已確認" in body
    assert "七日品牌世界觀鍛造表" not in body
    code_match = re.search(r"本機測試開通碼.*?<strong>([^<]+)</strong>", body, re.S)
    link_match = re.search(r'href="(/activate/[^\"]+)"', body)
    assert code_match and link_match

    activation_page = client.get(link_match.group(1))
    assert activation_page.status_code == 200
    csrf = set_public_csrf(client, "activation-csrf")
    activated = client.post(
        link_match.group(1),
        data={"csrf_token": csrf, "activation_code": code_match.group(1)},
        follow_redirects=True,
    )

    assert activated.status_code == 200
    assert "七日品牌世界觀鍛造表" in activated.get_data(as_text=True)

    reused = client.post(
        link_match.group(1),
        data={"csrf_token": csrf, "activation_code": code_match.group(1)},
    )
    assert reused.status_code == 400


def test_paid_content_requires_customer_session(client):
    response = client.get("/library/orders/TWYBNOTREAL", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/customer/login")


def test_analytics_endpoint_accepts_allowlisted_event(client):
    csrf = set_public_csrf(client)
    response = client.post(
        "/api/events",
        json={"event_name": "view_idea", "idea_slug": "brand-world-forge", "source": "web"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 204
