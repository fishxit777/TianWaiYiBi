"""V33 existing customer flows; isolated fixtures only, no real delivery/payment."""

import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from conftest import set_public_csrf
from test_customer_access import _pay_and_get_activation
from tianwai.db import get_db


ROOT = Path(__file__).resolve().parents[1]


class Elements(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def matching(self, tag=None, **attrs):
        return [item for kind, item in self.tags if (tag is None or tag == kind)
                and all(item.get(key) == value for key, value in attrs.items())]


def _activated_order(client):
    order, link, code = _pay_and_get_activation(client)
    csrf = set_public_csrf(client)
    result = client.post(link, data={"csrf_token": csrf, "activation_code": code}, follow_redirects=True)
    assert result.status_code == 200
    return order, link, result.get_data(as_text=True)


def test_login_has_progress_and_clear_retrieval_scope(client):
    body = client.get("/customer/login").get_data(as_text=True)
    elements = Elements(body)
    assert len(elements.matching("li", **{"aria-current": "step"})) == 1
    assert "不會建立新訂單或扣款" in body
    assert "第一次開通" in body
    email = elements.matching("input", id="customer-email")[0]
    assert email["autocomplete"] == "email"
    assert email["autocapitalize"] == "none"
    assert email["spellcheck"] == "false"
    assert email["aria-describedby"] == "email-help"
    assert elements.matching("p", id="email-help")


def test_verify_input_and_error_are_explicitly_associated(client):
    csrf = set_public_csrf(client)
    with client.session_transaction() as session:
        session["customer_login_email"] = "ux-fixture@example.invalid"
    response = client.post("/customer/login/verify", data={"csrf_token": csrf, "login_code": "INVALID"})
    assert response.status_code == 400
    elements = Elements(response.get_data(as_text=True))
    code = elements.matching("input", id="login-code")[0]
    assert code["aria-invalid"] == "true"
    assert code["aria-describedby"] == "login-code-help login-error"
    assert code["autocomplete"] == "one-time-code"
    assert code["spellcheck"] == "false"
    assert elements.matching("p", id="login-error", role="alert", tabindex="-1")
    assert elements.matching("details", **{"class": "flow-device-note"})


def test_activation_error_guidance_does_not_remove_server_validation(client):
    _, link, _ = _pay_and_get_activation(client)
    csrf = set_public_csrf(client)
    response = client.post(link, data={"csrf_token": csrf, "activation_code": "INVALID"})
    assert response.status_code == 400
    body = response.get_data(as_text=True)
    code = Elements(body).matching("input", id="activation-code")[0]
    assert code["aria-invalid"] == "true"
    assert code["aria-describedby"] == "activation-code-help activation-error"
    assert "開通碼過期不影響購買權限" in body
    assert "最多保留 2 台可信裝置" in body
    assert "舊工作階段會自動登出" in body


def test_auth_post_forms_expose_pending_feedback_and_keep_csrf(client):
    _, link, _ = _pay_and_get_activation(client)
    for path in ("/customer/login", link):
        body = client.get(path).get_data(as_text=True)
        assert "data-flow-form" in body
        assert 'name="csrf_token"' in body
        assert 'data-flow-submit-status role="status"' in body
    source = (ROOT / "static/flows.js").read_text(encoding="utf-8")
    assert "pending.has(form)" in source
    assert "event.preventDefault()" in source
    assert "addEventListener('pageshow'" in source
    assert "這不是完成通知" in source
    for forbidden in ("fetch(", "XMLHttpRequest", "localStorage", "sessionStorage", "navigator.sendBeacon"):
        assert forbidden not in source


def test_paid_result_is_inline_without_automatic_modal(client):
    _, link, _ = _pay_and_get_activation(client)
    response = client.get(link.replace("/activate/", "/payment/status/"))
    body = response.get_data(as_text=True)
    assert "付款成功，無須再次付款" in body
    assert "data-auto-modal" not in body
    assert '<dialog' not in body
    assert "前往專屬開通頁" in body
    assert "付款或寄信問題" in body


@pytest.mark.parametrize("state,expected", [("pending", "等待付款確認"), ("refunded", "訂單已退款"), ("cancelled", "需要確認訂單狀態")])
def test_nonpaid_states_are_not_all_misrepresented_as_pending(client, app, state, expected):
    order, link, _ = _pay_and_get_activation(client)
    with app.app_context():
        get_db().execute("UPDATE orders SET status = ? WHERE order_no = ?", (state, order["order_no"]))
        get_db().commit()
    response = client.get(link.replace("/activate/", "/payment/status/"))
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert expected in body
    assert "前往專屬開通頁" not in body
    if state != "pending":
        assert "等待付款確認" not in body
    else:
        assert "重新檢查只會讀取最新狀態，不會再次扣款" in body


def test_library_cards_have_identifiable_actions_and_session_exit(client):
    _activated_order(client)
    body = client.get("/customer/library").get_data(as_text=True)
    assert "卷可閱讀內容" in body
    assert "已付款但找不到內容" in body
    assert "登出此裝置" in body
    links = [attrs for attrs in Elements(body).matching("a") if attrs.get("href", "").startswith("/library/orders/")]
    assert links
    assert all(item["aria-label"].startswith("閱讀：") for item in links)


def test_library_empty_state_has_safe_recovery_choices(client, app):
    order, _, _ = _activated_order(client)
    with app.app_context():
        get_db().execute("UPDATE orders SET status = 'cancelled' WHERE order_no = ?", (order["order_no"],))
        get_db().commit()
    body = client.get("/customer/library").get_data(as_text=True)
    assert "目前沒有可閱讀的內容" in body
    assert "改用購買時的信箱登入" in body
    assert "不需要重新購買" in body
    assert "請私人客服協助確認" in body


def test_reader_has_valid_navigation_and_existing_authorized_image_routes(client):
    _, _, body = _activated_order(client)
    elements = Elements(body)
    for anchor in ("concept-overview", "concept-text", "concept-diagram", "concept-scene", "reading-boundary"):
        assert elements.matching("a", href=f"#{anchor}")
        assert elements.matching(id=anchor)
    zoom_links = [attrs for attrs in elements.matching("a") if "data-flow-image" in attrs]
    assert len(zoom_links) == 3
    for attrs in zoom_links:
        assert re.fullmatch(r"/library/assets/\d+/(?:hero|diagram|scene)", attrs["href"])
        assert attrs["target"] == "_blank"
        assert "noopener" in attrs["rel"]
        assert "download" not in attrs
    assert "access-watermark" in body
    assert "不是可直接投產的 CAD" in body
    assert elements.matching("dialog", **{"aria-labelledby": "flow-image-title"})
    assert any("data-flow-image-status" in attrs for attrs in elements.matching("p", role="status"))
    assert "/static/brand/blindbox-twin-tire" not in body


def test_reader_does_not_make_authorized_images_public(client, app):
    _, _, body = _activated_order(client)
    links = [attrs["href"] for attrs in Elements(body).matching("a") if "data-flow-image" in attrs]
    anonymous = app.test_client()
    for path in links:
        response = anonymous.get(path)
        assert response.status_code == 404
        assert response.headers["Cache-Control"].startswith("no-store")


def test_unavailable_and_not_found_pages_have_truthful_recovery_paths(client, monkeypatch):
    monkeypatch.setenv("PAYMENT_PROVIDER", "ecpay")
    body = client.get("/checkout/sealed-twin-tire-safety").get_data(as_text=True)
    assert "尚未開放建立訂單或扣款" in body
    assert "目前缺少正式金流或 Email 交付設定" not in body
    assert 'id="order-form"' not in body
    assert "返回本卷，繼續看線索" in body
    message = client.get("/payment/status/not-a-real-token").get_data(as_text=True)
    assert "如果你已經購買" in message
    assert 'href="/customer/login"' in message
    assert 'href="/support"' in message


def test_flow_styles_keep_narrow_layout_and_visible_focus():
    source = (ROOT / "static/v33-flows.css").read_text(encoding="utf-8")
    assert "max-width: 640px" in source
    assert "overflow-wrap: anywhere" in source
    assert ":focus-visible" in source
    assert "prefers-reduced-motion" in source
    assert "scroll-margin-top" in source
    assert "min-height: 44px" in source


def test_submit_feedback_prevents_duplicates_and_recovers_after_return():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is not available for the small DOM-free behavior fixture")
    harness = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const events = {}, pageEvents = {}, attrs = {};
const button = {disabled:false, textContent:'送出'};
const status = {textContent:''};
let timer;
const form = {
  dataset:{pendingLabel:'正在驗證…'},
  addEventListener:(name, callback)=>events[name]=callback,
  querySelector:(selector)=>selector.includes('data-flow-submit-status') ? status : button,
  setAttribute:(key,value)=>attrs[key]=value,
  removeAttribute:(key)=>delete attrs[key]
};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {
  document:{querySelectorAll:()=>[form], querySelector:()=>null},
  addEventListener:(name,callback)=>pageEvents[name]=callback,
  setTimeout:(callback)=>{timer=callback; return 1;}, clearTimeout:()=>{}
});
events.submit({defaultPrevented:false, submitter:button});
assert.equal(button.disabled,true);
assert.equal(button.textContent,'正在驗證…');
assert.equal(attrs['aria-busy'],'true');
let prevented = false;
events.submit({defaultPrevented:false, submitter:button, preventDefault:()=>prevented=true});
assert.equal(prevented,true);
timer();
assert.equal(button.disabled,false);
assert.equal(button.textContent,'送出');
assert.ok(status.textContent.includes('請先確認'));
events.submit({defaultPrevented:false, submitter:button});
pageEvents.pageshow();
assert.equal(button.disabled,false);
assert.equal(button.textContent,'送出');
assert.equal(status.textContent,'');
assert.equal(attrs['aria-busy'],undefined);
events.submit({defaultPrevented:true, submitter:button});
assert.equal(button.disabled,false);
process.stdout.write('flow_feedback_verified');
"""
    result = subprocess.run([node, "-e", harness, str(ROOT / "static/flows.js")], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, "DOM-free flow feedback regression failed"
    assert result.stdout == "flow_feedback_verified"
