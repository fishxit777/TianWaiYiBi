"""V33 shared storefront guards; browser geometry is recorded separately."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Tags(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.items = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.items.append((tag, dict(attrs)))


def test_shared_assets_load_after_historical_styles(client):
    html = client.get('/').get_data(as_text=True)
    assert html.index('v31.css') < html.index('v33-pages.css') < html.index('v33.css')
    assert 'flows.js' in html
    assert 'viewport-fit=cover' in html


def test_mobile_menu_has_every_existing_destination(client):
    html = client.get('/').get_data(as_text=True)
    menu = html.split('<details class="mobile-site-menu">')[1].split('</details>')[0]
    links = [attrs['href'] for tag, attrs in Tags(menu).items if tag == 'a']
    assert len(links) == 7
    assert {'/faq', '/policies', '/support', '/customer/login'} <= set(links)
    assert '/#ideas' in links and '/#veins' in links and '/#how' in links


def test_six_vein_links_have_real_filter_fallback_and_unique_names(client):
    html = client.get('/').get_data(as_text=True)
    links = [attrs for tag, attrs in Tags(html).items if tag == 'a' and 'data-vein-link' in attrs]
    expected = {'守護脈', '造物脈', '靈機脈', '破局脈', '人間脈', '傳音脈'}
    assert len(links) == 6
    assert {parse_qs(urlsplit(a['href']).query)['filter'][0] for a in links} == expected
    assert all(urlsplit(a['href']).fragment == 'ideas' for a in links)
    assert len({a['aria-label'] for a in links}) == 6


def test_brand_and_license_authentication_language_are_consistent(client):
    html = client.get('/').get_data(as_text=True)
    assert 'aria-label="天外一筆工作室首頁"' in html
    assert '<strong>個別驗證</strong>' in html
    assert '專屬權限' not in html
    assert 'aria-hidden="true">↗' not in html


def test_interest_never_promises_unavailable_notifications(client, monkeypatch):
    monkeypatch.setenv('ENABLE_DEV_TOOLS', 'false')
    monkeypatch.setenv('PAYMENT_PROVIDER', 'ecpay')
    monkeypatch.setenv('ECPAY_MODE', 'production')
    html = client.get('/ideas/sealed-twin-tire-safety').get_data(as_text=True)
    assert '登記開放意願' in html and '開放時通知我' not in html
    source = (ROOT / 'static/app.js').read_text(encoding='utf-8')
    assert '不會另行通知' in source
    assert 'interest_registered' in source  # Existing anonymous signal, not a person count.


def test_current_location_history_and_focus_recovery_guards():
    source = (ROOT / 'static/app.js').read_text(encoding='utf-8')
    assert "addEventListener('popstate'" in source
    assert 'history.pushState' in source
    assert "setAttribute('aria-current'" in source
    assert 'filterButtons[0]?.focus()' in source
    assert "event.key === 'Escape'" in source and 'closeMenu(true)' in source
    assert 'ResizeObserver' in source and '--navigation-clearance' in source


def test_companion_announcements_stay_local():
    source = (ROOT / 'static/companions.js').read_text(encoding='utf-8')
    assert "setAttribute('aria-live', 'polite')" in source
    assert 'announcement.textContent' in source
    assert not any(token in source for token in ('fetch(', 'localStorage', 'XMLHttpRequest', 'sendBeacon'))


def test_responsive_and_reduced_motion_guards():
    css = (ROOT / 'static/v33.css').read_text(encoding='utf-8')
    assert 'env(safe-area-inset-bottom)' in css
    assert '.home-page .blindbox-catalog .filters' in css and 'grid-template-columns: repeat(3, minmax(0, 1fr))' in css
    assert 'min-height: 44px' in css
    assert 'prefers-reduced-motion: reduce' in css
    assert 'max-height: 500px' in css
    assert '.companion-speech { color: #3b5a51' in css


def test_skip_navigation_and_filter_status_can_receive_focus(client):
    html = client.get('/').get_data(as_text=True)
    tags = Tags(html).items
    for identifier in ('main', 'idea-result-count'):
        assert any(attrs.get('id') == identifier and attrs.get('tabindex') == '-1' for _, attrs in tags)


def test_existing_commerce_and_retired_features_are_unchanged(client, monkeypatch):
    monkeypatch.setenv('ENABLE_DEV_TOOLS', 'false')
    monkeypatch.setenv('PAYMENT_PROVIDER', 'ecpay')
    monkeypatch.setenv('ECPAY_MODE', 'production')
    html = client.get('/').get_data(as_text=True)
    assert '公開收款仍關閉' in html
    assert 'serviceWorker.register' not in html
    assert '<form' not in html
    assert 'comment-form' not in html
