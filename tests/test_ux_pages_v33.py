"""Public reading-room usability checks; no real customer data or services."""

import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


class PageOutline(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.tags = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


@pytest.mark.parametrize("path", ["/faq", "/policies", "/support", "/ideas/sealed-twin-tire-safety"])
def test_pages_have_current_location_and_valid_local_targets(client, path):
    response = client.get(path)
    assert response.status_code == 200
    page = PageOutline(response.get_data(as_text=True))
    assert sum(tag == "h1" for tag, _ in page.tags) == 1
    assert any(attrs.get("aria-current") == "page" for _, attrs in page.tags)
    ids = [attrs["id"] for _, attrs in page.tags if "id" in attrs]
    assert len(ids) == len(set(ids))
    for tag, attrs in page.tags:
        href = attrs.get("href", "")
        if tag == "a" and href.startswith("#"):
            assert href[1:] in ids


def test_faq_keeps_eight_independent_native_disclosures_and_group_routes(client):
    body = client.get("/faq").get_data(as_text=True)
    page = PageOutline(body)
    details = [attrs for tag, attrs in page.tags if tag == "details" and "faq-item" in attrs.get("class", "").split()]
    assert len(details) == 8
    assert all("open" not in attrs and "name" not in attrs for attrs in details)
    assert all(attrs.get("class") == "policy-disclosure faq-item" for attrs in details)
    for group in ("fit", "use", "help"):
        assert f'id="faq-{group}"' in body
        assert f'href="#faq-{group}"' in body
    assert "不把兩頁寫成同一份內容" not in body
    answer = body.split("買過之後怎麼取回？", 1)[1].split("</details>", 1)[0]
    assert "前往已購取回" in answer
    assert 'class="page-inline-action"' in answer


def test_policy_substantive_sections_and_version_remain_unchanged(client):
    source = (ROOT / "templates" / "policies.html").read_text(encoding="utf-8")
    sections = re.findall(r"<section><h3>.*?</section>", source)
    assert len(sections) == 21
    # Baseline HEAD before V33: all legal prose remains byte-for-byte identical.
    assert hashlib.sha256("\n".join(sections).encode()).hexdigest() == (
        "8beb0bcefa9ce166653f9b4b0be2077c759f90ecb757d07a047481ca547a4f51"
    )
    body = client.get("/policies").get_data(as_text=True)
    assert '<strong>2026-08-30-v29</strong>' in body
    assert body.count('class="policy-chapter-footer"') == 4
    assert body.count('href="#policy-directory"') == 4


def test_unconfigured_support_offers_existing_self_help_not_data_collection(client):
    body = client.get("/support").get_data(as_text=True)
    assert 'class="support-self-help"' in body
    assert "目前可使用的自助服務" in body
    assert 'href="/faq#faq-help"' in body
    assert "可以先自行記下" in body
    assert "訂購時使用的 Email</li>" not in body
    assert "mailto:" not in body
    assert not any(tag in {"form", "input", "textarea"} for tag, _ in PageOutline(body).tags)
    assert "先遮住上述資料及完整付費圖文" in body


def test_configured_support_keeps_existing_validated_contact_paths(app, client):
    app.config.update(
        SUPPORT_EMAIL="support@example.test",
        SUPPORT_FORM_URL="https://docs.google.com/forms/d/e/tianwai-support/viewform",
    )
    body = client.get("/support").get_data(as_text=True)
    assert 'href="mailto:support@example.test"' in body
    assert "訂購時使用的 Email</li>" in body
    assert "可以提供" in body
    assert "support-self-help" not in body


def test_detail_introduces_the_concept_before_decoration_and_keeps_payment_closed(client, monkeypatch):
    monkeypatch.setattr(
        "tianwai.payments.payment_checkout_status",
        lambda: {"provider": "unavailable", "label": "公開付款尚未開放", "ready": False},
    )
    body = client.get("/ideas/sealed-twin-tire-safety").get_data(as_text=True)
    assert body.index('<header class="detail-introduction') < body.index('<div class="blind-preview')
    assert body.count('class="detail-information-section"') == 3
    assert "先看問題，再判斷價值" in body
    assert "拆封後取得" in body
    assert "data-analytics-idea" in body
    assert "data-interest-cta" in body
    assert "登記開放意願" in body
    assert "也不會另行通知" in body
    assert "開放時通知我" not in body
    assert "售價已公開，尚未開放購買" in body
    assert "NT$199" in body
    assert 'href="/checkout/' not in body


def test_pages_styles_preserve_clear_single_column_prose_and_focus_states():
    css = (ROOT / "static" / "v33-pages.css").read_text(encoding="utf-8")
    assert ".policies-page .policy-prose { display: block; }" in css
    assert ".faq-page .policy-disclosure summary:focus-visible" in css
    assert ".policy-chapter-footer a:focus-visible" in css
    assert "min-height: 44px" in css
    assert ".blind-detail .blind-preview { min-height: 245px; }" in css
    assert "font-family:" not in css


def test_all_thirteen_public_volumes_share_the_readable_section_structure(client):
    home = PageOutline(client.get("/").get_data(as_text=True))
    paths = {
        attrs["href"]
        for tag, attrs in home.tags
        if tag == "a" and attrs.get("href", "").startswith("/ideas/")
    }
    assert len(paths) == 14
    for path in sorted(paths):
        response = client.get(path)
        assert response.status_code == 200
        page = PageOutline(response.get_data(as_text=True))
        assert sum(tag == "h1" for tag, _ in page.tags) == 1
        for section_id in ("concept-clues", "concept-deliverables", "concept-next-step"):
            assert any(tag == "section" and attrs.get("id") == section_id for tag, attrs in page.tags)
