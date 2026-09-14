"""V33 admin presentation checks; synthetic sessions only, no production requests."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from html.parser import HTMLParser

import pytest
from flask import render_template

from conftest import login_admin


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "static/admin.js").read_text(encoding="utf-8")
STYLE = (ROOT / "static/v33-admin.css").read_text(encoding="utf-8")


class Markup(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.elements = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def find_id(self, element_id):
        return next(attrs for _, attrs in self.elements if attrs.get("id") == element_id)


@pytest.fixture
def dashboard_markup(client):
    login_admin(client)
    response = client.get("/admin")
    assert response.status_code == 200
    return Markup(response.get_data(as_text=True))


@pytest.mark.parametrize("template", ["admin_dashboard.html", "admin_login.html", "admin_passkeys.html", "admin_recovery.html"])
def test_admin_pages_share_scoped_readable_light_theme(template):
    source = (ROOT / "templates" / template).read_text(encoding="utf-8")
    assert source.count("v33-admin.css") == 1
    assert source.index("v33-admin.css") > source.index("v19.css")
    assert "font-family:" not in STYLE  # Retain the user's V19 JhengHei stack.
    assert ".public-site" not in STYLE


def test_all_admin_tables_have_keyboard_regions_and_captions(dashboard_markup):
    tables = [attrs for tag, attrs in dashboard_markup.elements if tag == "table"]
    captions = [attrs for tag, attrs in dashboard_markup.elements if tag == "caption"]
    regions = [attrs for _, attrs in dashboard_markup.elements if attrs.get("class") == "table-scroll"]
    assert len(tables) == len(captions) == len(regions) == 3
    assert all(region.get("tabindex") == "0" and region.get("role") == "region" and region.get("aria-label") for region in regions)
    assert all(attrs.get("scope") == "col" for tag, attrs in dashboard_markup.elements if tag == "th")


def test_global_price_has_explicit_label_and_scope_help(dashboard_markup):
    assert any(tag == "label" and attrs.get("for") == "global-price" for tag, attrs in dashboard_markup.elements)
    assert dashboard_markup.find_id("global-price").get("aria-describedby") == "global-price-help"
    assert dashboard_markup.find_id("global-price").get("max") == "100000"


def test_editor_has_accessible_name_and_instructions(dashboard_markup):
    dialog = dashboard_markup.find_id("idea-editor")
    assert dialog.get("aria-labelledby") == "idea-editor-title"
    assert dialog.get("aria-describedby") == "idea-editor-help"
    assert dashboard_markup.find_id("idea-editor-title")
    assert dashboard_markup.find_id("idea-editor-help")


def test_editor_groups_public_paid_and_internal_without_losing_fields(dashboard_markup):
    # This contract belongs to the content editor, not the separate V37
    # commerce dialog, which legitimately has its own fieldsets and legends.
    elements = dashboard_markup.elements
    editor_start = next(index for index, (_, attrs) in enumerate(elements) if attrs.get("id") == "idea-editor")
    editor_end = next(index for index in range(editor_start + 1, len(elements)) if elements[index][0] == "dialog")
    editor_elements = elements[editor_start:editor_end]
    groups = [attrs.get("data-editor-scope") for tag, attrs in editor_elements if tag == "fieldset"]
    assert groups == ["public", "paid", "internal"]
    ids = [attrs.get("id") for _, attrs in dashboard_markup.elements if attrs.get("id")]
    assert len(ids) == len(set(ids))
    editor_ids = {attrs.get("id") for _, attrs in editor_elements if attrs.get("id")}
    expected_fields = {
        "id", "public-title", "title", "role", "seal", "accent", "sort-order", "price-override",
        "discipline", "primary-vein", "secondary-vein", "topic", "maturity", "workflow-status",
        "raw-idea", "summary", "teaser", "paid-content", "deliverables", "tags", "hero-image",
        "diagram-image", "scene-image",
    }
    assert all("idea-" + field in editor_ids for field in expected_fields)
    assert len([tag for tag, _ in editor_elements if tag == "legend"]) == 3
    assert '.catalog-card { grid-column: 1 / -1; min-width: 0; }' in STYLE


def test_confirmation_focus_defaults_to_existing_cancel(dashboard_markup):
    assert dashboard_markup.find_id("admin-confirm-cancel").get("type") == "button"
    assert "document.querySelector('#admin-confirm-cancel').focus()" in SCRIPT
    assert "document.querySelector('#admin-confirm-submit').focus()" not in SCRIPT
    assert "confirmForm.addEventListener('submit', (event) => { event.preventDefault(); closeConfirm(true); });" in SCRIPT


def test_manual_snapshot_not_mislabelled_realtime():
    assert "tone === 'attention' ? '需處理' : '同步快照'" in SCRIPT
    assert "const stale = seconds >= 300" in SCRIPT
    assert "target.classList.toggle('is-stale', stale)" in SCRIPT
    assert ".last-sync.is-stale" in STYLE
    assert "window.setInterval(updateSyncFreshness, 15000)" in SCRIPT


def test_notification_and_workflow_labels_are_human_readable():
    for label_group in ("notificationLabels", "workflowLabels", "incidentLabels", "severityLabels", "eventLabels", "actionLabels"):
        assert f"const {label_group} =" in SCRIPT
        assert f"statusLabel({label_group}," in SCRIPT
    assert "sent: '服務已接受'" in SCRIPT
    assert "事件代碼：${item.event_type}" in SCRIPT
    assert "innerHTML" not in SCRIPT


def test_taipei_time_helpers_are_independent_of_host_timezone():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to execute date-format helpers")
    start = SCRIPT.index("  const dateText =")
    end = SCRIPT.index("  const setBadge =", start)
    js = SCRIPT[start:end] + "\nconsole.log(JSON.stringify({date: dateText('2026-09-13T17:05:00Z'), invalid: dateText('invalid'), known: statusLabel({sent:'accepted'}, 'sent'), unknown: statusLabel({}, 'unmapped')}));"
    environment = {**os.environ, "TZ": "America/Los_Angeles"}
    result = subprocess.run([node, "-e", js], capture_output=True, text=True, encoding="utf-8", env=environment, check=False)
    assert result.returncode == 0, "Date helper execution failed"
    data = json.loads(result.stdout)
    assert "1:05" in data["date"] and "9/14" in data["date"]
    assert data["invalid"] == "—"
    assert data["known"] == "accepted" and "unmapped" in data["unknown"]
    assert "const key = day.toISOString().slice(0, 10)" in SCRIPT
    assert "營收日彙總沿用 UTC 日界" in SCRIPT


def test_load_errors_distinguish_unknown_from_last_good_data(dashboard_markup):
    assert dashboard_markup.find_id("admin-root").get("data-load-state") == "loading"
    assert dashboard_markup.find_id("admin-data-note")
    assert "root.dataset.loadState = dashboard ? 'stale' : 'error'" in SCRIPT
    assert "目前保留上次成功讀取的資料，不代表最新狀態" in SCRIPT
    assert "不要將空白視為零筆或正常" in SCRIPT
    assert "if (!dashboard) return;" in SCRIPT
    assert "目前未取得完整營運資料" in SCRIPT
    assert '.admin-main[data-load-state="error"] .metric-skeleton { display: none; }' in STYLE


def test_load_state_transitions_execute_without_wiping_last_good_snapshot():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to execute dashboard state transitions")
    start = SCRIPT.index("  async function loadDashboard(message = '')")
    end = SCRIPT.index("  document.querySelectorAll('[data-admin-view]')", start)
    function_source = SCRIPT[start:end]
    js = r"""
const vm = require('node:vm');
async function scenario(existing, response, shouldFail) {
  const note = {textContent: ''};
  const noop = () => {};
  const context = {
    dashboard: existing ? {metrics: {}, marker: 'previous'} : null,
    analyticsDays: 30,
    setStatus: noop, showError: noop, updateSyncFreshness: noop,
    root: {dataset: {}, classList: {add: noop, remove: noop}, setAttribute: noop, removeAttribute: noop},
    document: {querySelector: () => note},
    refreshDashboard: {disabled: false, setAttribute: noop, removeAttribute: noop},
    api: async () => { if (shouldFail) throw new Error('synthetic failure'); return response; },
    render: (data) => { context.dashboard = data; }
  };
  await vm.runInNewContext(FUNCTION_SOURCE + '\nloadDashboard()', context);
  return {state: context.root.dataset.loadState, retained: context.dashboard?.marker === 'previous', disabled: context.refreshDashboard.disabled, note: note.textContent};
}
(async () => {
  const outputs = await Promise.all([
    scenario(false, {metrics: {}}, false),
    scenario(false, null, true),
    scenario(true, null, true),
    scenario(false, {metrics: null}, false)
  ]);
  console.log(JSON.stringify(outputs));
})();
""".replace("FUNCTION_SOURCE", json.dumps(function_source))
    result = subprocess.run([node, "-e", js], capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 0, "Dashboard state transition execution failed"
    outputs = json.loads(result.stdout)
    assert [row["state"] for row in outputs] == ["ready", "error", "stale", "error"]
    assert outputs[2]["retained"] is True
    assert all(row["disabled"] is False for row in outputs)
    assert "不要將空白視為零筆或正常" in outputs[1]["note"]
    assert "不代表最新狀態" in outputs[2]["note"]


def test_confirmation_really_focuses_cancel_on_open():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to execute confirmation focus")
    start = SCRIPT.index("  const confirmAction =")
    end = SCRIPT.index("  const closeConfirm =", start)
    function_source = SCRIPT[start:end]
    js = """
let focusTarget = '';
let opened = 0;
let confirmResolver = null;
const confirmDialog = {dataset: {}, showModal: () => { opened += 1; }};
const document = {querySelector: (selector) => ({textContent: '', focus: () => {focusTarget = selector;}})};
""" + function_source + """
confirmAction({title: 'Synthetic title', message: 'Synthetic message', impact: 'Synthetic impact', tone: 'danger'});
console.log(JSON.stringify({focusTarget, opened}));
"""
    result = subprocess.run([node, "-e", js], capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 0, "Confirmation focus execution failed"
    data = json.loads(result.stdout)
    assert data == {"focusTarget": "#admin-confirm-cancel", "opened": 1}


def test_admin_security_templates_keep_existing_entry_points(app):
    with app.test_request_context("/"):
        recovery = render_template("admin_recovery.html", error=None, turnstile_site_key="")
    markup = Markup(recovery)
    forms = [attrs for tag, attrs in markup.elements if tag == "form"]
    assert len(forms) == 1 and forms[0].get("method") == "post"
    assert forms[0].get("action") == "/admin/recovery"
    assert any(attrs.get("name") == "csrf_token" for _, attrs in markup.elements)
    assert any(attrs.get("data-action") == "admin-recovery" and attrs.get("data-theme") == "light" for _, attrs in markup.elements)
    assert re.search(r"/admin/api/security/notifications/retry", SCRIPT)
    assert "新增測試推播" not in SCRIPT


def test_mobile_retains_existing_logout_and_safe_area_clearance(dashboard_markup):
    assert '.admin-sidebar { display: flex; height: auto;' in STYLE
    assert 'grid-template-columns: repeat(6, minmax(0, 1fr))' in STYLE
    assert len([attrs for _, attrs in dashboard_markup.elements if "data-admin-view" in attrs]) == 6
    assert '.admin-ops-page .admin-sidebar-footer { display: flex;' in STYLE
    assert '.admin-sidebar-footer :is(.admin-preview-link, form) { display: block;' in STYLE
    assert 'padding-bottom: calc(174px + env(safe-area-inset-bottom))' in STYLE
    logout_forms = [attrs for tag, attrs in dashboard_markup.elements if tag == "form" and attrs.get("action") == "/admin/logout"]
    assert len(logout_forms) == 1 and logout_forms[0].get("method") == "post"
