import re
from pathlib import Path

from conftest import set_public_csrf


def create_order(client, slug="sealed-twin-tire-safety"):
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


def test_home_presents_the_sealed_blind_strategy_catalog(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "天外盲策" in body
    assert "只在拆封後現世的" in body
    assert "static/v18.css" in body
    assert "static/v20.css" in body
    assert "static/v21.css" in body
    assert "static/v22.css" in body
    assert "static/v23.css" in body
    assert "static/v24.css" in body
    assert "static/v25.css" in body
    assert "static/companions.js" in body
    assert "brand/sealed-scroll-casket-v20.webp" in body
    assert "封印未解" in body
    assert 'class="sealed-scroll"' not in body
    assert "blindbox-twin-tire-hero-v1.webp" in body
    assert 'id="idea-result-count"' in body
    assert 'aria-pressed="true">全部' in body
    assert body.count('class="idea-card sealed-card') == 1
    for vein in ("守護脈", "造物脈", "靈機脈", "破局脈", "人間脈", "傳音脈"):
        assert vein in body
    assert body.count("vein-scroll-mark") == 6
    assert body.count('class="vein-card ') == 6
    assert body.count("data-companion-button") == 8
    for companion in ("guardian", "crafter", "oracle", "strategist", "healer", "musician"):
        assert f"brand/companions/chibi-{companion}-v23.webp" in body
    assert "concept-scroll-card" in body
    assert "封印盲策・第壹卷" in body
    assert "雙生續行輪" not in body
    assert "不設公開留言區" in body


def test_home_hides_internal_tools_and_offers_human_transmission(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    for private_label in ("Logo 評估", "管理後台", "開啟本機模擬器", "LINE Bot"):
        assert private_label not in body
    assert "/logo-review" not in body
    assert "/dev/line" not in body
    assert "/admin" not in body
    assert "私人訂單協助" in body
    assert 'href="/transmission"' in body
    assert "line.me/R/ti/p" not in body


def test_transmission_landing_keeps_line_white_page_behind_branded_experience(client):
    response = client.get("/transmission")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "私人協助・只處理交易問題" in body
    assert "一筆啟月門" in body
    assert "brand/transmission-title-xianxia-v14.webp" in body
    assert "brand/wordmark-xianxia-v14.webp" in body
    assert body.count('fetchpriority="high"') >= 4
    assert "守閣之誓" in body
    assert "不設公開留言或買家討論" in body
    assert "不索取密碼與驗證碼" in body
    assert "brand/line-add-qr.svg" in body
    assert "https://line.me/R/ti/p/%40279plitu" in body
    assert "啟動傳音法陣" in body
    assert 'data-copy-line-id="@279plitu"' in body
    assert "static/v19.css" in body
    assert "fonts/tianwai-masa-regular.woff2" not in body
    assert "fonts/tianwai-masa-bold.woff2" not in body
    for private_label in ("Logo 評估", "管理後台", "開啟本機模擬器", "LINE Bot"):
        assert private_label not in body


def test_all_customer_pages_share_the_sitewide_readable_type_shell(client):
    for path in (
        "/",
        "/transmission",
        "/ideas/sealed-twin-tire-safety",
        "/checkout/sealed-twin-tire-safety",
        "/orders/not-a-real-token",
    ):
        body = client.get(path).get_data(as_text=True)
        assert 'class="public-site ' in body
        assert "static/v19.css" in body
        assert "static/v20.css" in body
        assert "static/v21.css" in body
        assert "static/v22.css" in body
        assert "static/v23.css" in body
        assert "static/v24.css" in body
        assert "static/v25.css" in body
        assert "fonts/tianwai-masa-regular.woff2" not in body
        assert "fonts/tianwai-masa-bold.woff2" not in body


def test_internal_line_simulator_does_not_use_public_brand_font_shell(client):
    body = client.get("/dev/line").get_data(as_text=True)

    assert 'class="internal-tool-site line-page"' in body
    assert "fonts/tianwai-masa" not in body


def test_readable_typography_layer_covers_public_and_admin_interfaces():
    project_root = Path(__file__).resolve().parents[1]
    stylesheet = (project_root / "static" / "v19.css").read_text(encoding="utf-8")
    assert "--readable-ui" in stylesheet
    assert '"Microsoft JhengHei UI"' in stylesheet
    assert ".public-site" in stylesheet
    assert ".admin-page" in stylesheet
    assert ".admin-login-page" in stylesheet
    assert "font-size: 18px" in stylesheet
    assert "font-size: 14px" in stylesheet
    assert "font-size: 16px !important" in stylesheet
    assert "Tianwai Masa" not in stylesheet


def test_v20_hero_uses_an_optimized_xianxia_casket_asset():
    project_root = Path(__file__).resolve().parents[1]
    asset = project_root / "static" / "brand" / "sealed-scroll-casket-v20.webp"
    data = asset.read_bytes()
    stylesheet = (project_root / "static" / "v20.css").read_text(encoding="utf-8")

    assert data[:4] == b"RIFF"
    assert data[8:12] == b"WEBP"
    assert len(data) < 400_000
    for selector in (".celestial-casket", ".casket-artifact", ".casket-orbit", ".casket-status"):
        assert selector in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet


def test_v21_talisman_layer_remains_available_as_historical_css():
    project_root = Path(__file__).resolve().parents[1]
    stylesheet = (project_root / "static" / "v21.css").read_text(encoding="utf-8")

    for selector in (
        ".vein-sigil",
        ".sealed-talisman",
        ".blind-preview-seal",
        ".checkout-seal",
        ".casket-status > i",
        ".unseal-rules li > span",
    ):
        assert selector in stylesheet
    assert "clip-path: polygon" in stylesheet


def test_v22_moves_public_storefront_into_a_sunlit_celestial_palette(client):
    project_root = Path(__file__).resolve().parents[1]
    stylesheet = (project_root / "static" / "v22.css").read_text(encoding="utf-8")
    home = client.get("/").get_data(as_text=True)

    assert "sunlit-celestial-realm-v22" in home
    assert '<meta name="theme-color" content="#edf5ec">' in home
    for token in (
        "--day-sky",
        "--day-cloud",
        "--day-ink",
        "--day-jade",
        "--day-gold",
    ):
        assert token in stylesheet
    for selector in (
        ".blindbox-home",
        ".blind-hero",
        ".vein-grid .vein-card",
        ".home-page .idea-card",
        ".unseal-rules",
        ".blind-preview",
        ".checkout-card",
        ".payment-card",
    ):
        assert selector in stylesheet
    assert ".public-site:not(.transmission-v2-page)" in stylesheet


def test_v23_adds_optimized_interactive_chibi_immortal_companions(client):
    project_root = Path(__file__).resolve().parents[1]
    stylesheet = (project_root / "static" / "v23.css").read_text(encoding="utf-8")
    script = (project_root / "static" / "companions.js").read_text(encoding="utf-8")
    home = client.get("/").get_data(as_text=True)
    companion_root = project_root / "static" / "brand" / "companions"

    assert "chibi-immortal-companions-v23" in home
    assert home.count("data-companion-button") == 8
    assert home.count('class="companion-card"') == 0
    assert home.count("companion-card") == 6
    assert "不設公開留言區" in home
    assert 'href="/checkout/sealed-twin-tire-safety"' not in home

    for name in ("guardian", "crafter", "oracle", "strategist", "healer", "musician"):
        asset = companion_root / f"chibi-{name}-v23.webp"
        data = asset.read_bytes()
        assert data[:4] == b"RIFF"
        assert data[8:12] == b"WEBP"
        assert len(data) < 180_000

    for selector in (
        ".immortal-companion",
        ".companion-hero",
        ".companion-card",
        ".companion-cameo",
        ".rule-companion",
        ".companion-footer",
    ):
        assert selector in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert "data-companion-button" in script
    assert "fetch(" not in script


def test_v24_replaces_rendered_polygons_with_content_specific_scroll_illustrations(client):
    project_root = Path(__file__).resolve().parents[1]
    stylesheet = (project_root / "static" / "v24.css").read_text(encoding="utf-8")
    macros = (project_root / "templates" / "_celestial_scrolls.html").read_text(encoding="utf-8")
    home = client.get("/").get_data(as_text=True)
    detail = client.get("/ideas/sealed-twin-tire-safety").get_data(as_text=True)
    checkout = client.get("/checkout/sealed-twin-tire-safety").get_data(as_text=True)

    assert "illustrated-celestial-scrolls-v24" in home
    assert home.count("vein-scroll-mark") == 6
    for kind in ("guardian", "forge", "oracle", "strategist", "healer", "musician"):
        assert f"vein-scroll-{kind}" in home
    for label in ("鎮守結界", "仙工鑄器", "星盤推演", "展扇落子", "桃花濟世", "玉笛傳聲"):
        assert label in home
    for kind, label in (("observe", "觀卷"), ("reveal", "解印"), ("decide", "自決")):
        assert f"rule-scroll-{kind}" in home
        assert label in home

    assert "concept-scroll-card" in home
    assert "concept-scroll-preview" in detail
    assert "concept-scroll-checkout" in checkout
    assert "雙輪護陣" in home and "雙輪護陣" in detail and "雙輪護陣" in checkout
    assert "casket-volume-scroll" in home

    for rendered in (home, detail, checkout):
        for old_class in ("vein-sigil", "sealed-talisman", "blind-preview-seal", "checkout-seal"):
            assert re.search(rf'class="[^"]*\b{re.escape(old_class)}\b', rendered) is None
    assert home.count("rule-scroll-mark") == 3
    assert "clip-path: polygon" not in stylesheet
    for selector in (".celestial-scroll-mark", ".vein-scroll-mark", ".concept-scroll-mark", ".rule-scroll-mark"):
        assert selector in stylesheet
    for phrase in ("kind == 'guardian'", "kind == 'forge'", "kind == 'oracle'", "kind == 'strategist'", "kind == 'healer'"):
        assert phrase in macros
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet


def test_v24_strengthens_the_existing_logo_on_daylight_headers(client):
    project_root = Path(__file__).resolve().parents[1]
    stylesheet = (project_root / "static" / "v24.css").read_text(encoding="utf-8")
    home = client.get("/").get_data(as_text=True)

    assert "website-nav-logo-256.png" in home
    assert "wordmark-xianxia-v14.webp" in home
    assert ".public-site:not(.transmission-v2-page) .brand-mark" in stylesheet
    assert ".public-site:not(.transmission-v2-page) .brand-wordmark" in stylesheet
    assert "contrast(1.22)" in stylesheet
    assert "font-weight: 800" in stylesheet


def test_v25_moves_scroll_explanations_below_the_art_and_adds_safe_celestial_scenes(client):
    project_root = Path(__file__).resolve().parents[1]
    stylesheet = (project_root / "static" / "v25.css").read_text(encoding="utf-8")
    macros = (project_root / "templates" / "_celestial_scrolls.html").read_text(encoding="utf-8")
    scene = project_root / "static" / "brand" / "chibi-celestial-gate-bg-v25.webp"
    home = client.get("/").get_data(as_text=True)

    assert "celestial-scroll-scenes-v25" in home
    assert home.count("vein-scroll-figure") == 6
    assert home.count("rule-scroll-figure") == 3
    assert home.count("<figcaption>") == 9
    assert '<span class="scroll-copy"><b>{{ glyph }}</b></span>' in macros
    assert '<span class="scroll-copy"><b>{{ step }}</b></span>' in macros
    assert "<small>{{ action }}</small>" not in macros
    assert "<small>{{ label }}</small>" not in macros

    scene_data = scene.read_bytes()
    assert scene_data[:4] == b"RIFF"
    assert scene_data[8:12] == b"WEBP"
    assert len(scene_data) < 100_000
    assert "chibi-celestial-gate-bg-v25.webp" in stylesheet
    for selector in (
        ".vein-scroll-figure",
        ".rule-scroll-figure",
        ".vein-grid .vein-card::before",
        ".companion-card .companion-speech",
    ):
        assert selector in stylesheet
    assert "z-index: 10" in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert "不設公開留言區" in home
    assert 'href="/checkout/sealed-twin-tire-safety"' not in home


def test_all_management_templates_load_the_readable_typography_layer():
    template_root = Path(__file__).resolve().parents[1] / "templates"

    for template_name in (
        "admin_dashboard.html",
        "admin_login.html",
        "admin_passkeys.html",
        "admin_recovery.html",
    ):
        template = (template_root / template_name).read_text(encoding="utf-8")
        assert "static', filename='v19.css'" in template
        assert "readable-typography-v19" in template


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

    v16_stylesheet = (project_root / "static" / "v16.css").read_text(encoding="utf-8")
    assert "V16 professional refinement" in v16_stylesheet
    assert ".home-page .idea-fit" in v16_stylesheet
    assert ".home-page .filter-console" in v16_stylesheet
    assert ".public-site .footer-trust" in v16_stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in v16_stylesheet


def test_logo_review_is_not_a_public_route(client):
    response = client.get("/logo-review")

    assert response.status_code == 404


def test_idea_detail_uses_global_price(client):
    response = client.get("/ideas/sealed-twin-tire-safety")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "守護脈" in body
    assert "NT$199" in body
    assert "完整視覺已封印" in body
    assert "購買取得非專屬閱讀權" in body
    assert "雙生續行輪" not in body


def test_unavailable_payment_state_never_pushes_visitors_into_checkout(client, monkeypatch):
    monkeypatch.setattr(
        "tianwai.payments.payment_checkout_status",
        lambda: {"provider": "unavailable", "label": "正式付款尚未開放", "ready": False},
    )

    home = client.get("/").get_data(as_text=True)
    detail = client.get("/ideas/sealed-twin-tire-safety").get_data(as_text=True)

    assert "公開收款仍關閉，不會建立扣款" in home
    assert home.count("查看封印線索") >= 1
    assert "公開收款未開放" in detail
    assert "開放時通知我" in detail
    assert 'href="/checkout/sealed-twin-tire-safety"' not in detail


def test_v18_public_layer_contains_sealed_catalog_and_motion_guards():
    stylesheet = (
        Path(__file__).resolve().parents[1] / "static" / "v18.css"
    ).read_text(encoding="utf-8")
    script = (
        Path(__file__).resolve().parents[1] / "static" / "app.js"
    ).read_text(encoding="utf-8")

    for selector in (".blind-hero", ".sealed-card", ".maturity-chip", ".blind-preview"):
        assert selector in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert "applyIdeaFilter" in script
    assert "searchParams.set('filter'" in script
    assert "data-interest-cta" in script


def test_order_rejects_invalid_email(client):
    csrf = set_public_csrf(client)
    response = client.post(
        "/api/orders",
        json={"idea_slug": "sealed-twin-tire-safety", "customer_name": "A", "customer_email": "bad"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "請輸入有效的 Email"


def test_order_requires_explicit_payment_and_digital_content_consents(client):
    csrf = set_public_csrf(client)
    response = client.post(
        "/api/orders",
        json={
            "idea_slug": "sealed-twin-tire-safety",
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
    assert "雙生續行輪" not in body
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
    activated_body = activated.get_data(as_text=True)
    assert "雙生續行輪" in activated_body
    assert "blindbox-twin-tire-cutaway-v1.webp" in activated_body
    assert "概念視覺・不代表已完成工程驗證" in activated_body

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
        json={"event_name": "view_idea", "idea_slug": "sealed-twin-tire-safety", "source": "web"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 204
