import re

from conftest import set_public_csrf


def create_order(client, slug="brand-world-forge"):
    csrf = set_public_csrf(client)
    response = client.post(
        "/api/orders",
        json={
            "idea_slug": slug,
            "customer_name": "測試旅人",
            "customer_email": "traveler@example.com",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201
    return response.get_json()


def test_home_lists_six_distinct_cultivators(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "仙策閣" in response.get_data(as_text=True)
    assert response.get_data(as_text=True).count("idea-card") >= 6
    for role in ("破局劍修", "造境符師", "增長丹師", "機關偃師", "回聲樂修", "觀星策士"):
        assert role in response.get_data(as_text=True)


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


def test_mock_payment_unlocks_paid_content(client):
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
    assert "心法已解鎖" in body
    assert "七日品牌世界觀鍛造表" in body


def test_analytics_endpoint_accepts_allowlisted_event(client):
    csrf = set_public_csrf(client)
    response = client.post(
        "/api/events",
        json={"event_name": "view_idea", "idea_slug": "brand-world-forge", "source": "web"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 204

