"""Guard independently deployed project boundaries without reading other projects."""

import ast
from pathlib import Path
import re
import sys
import socket
import urllib.request
from urllib.parse import urlsplit

from flask import Flask
from markupsafe import escape
import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_HOST = "tianwai-yibi.onrender.com"
APPROVED_RUNTIME_PACKAGES = {"tianwai", "flask", "argon2", "psycopg", "webauthn"}
APPROVED_INTEGRATION_HOSTS = {
    APP_HOST, "localhost", "127.0.0.1",
    "api.line.me", "api.brevo.com", "challenges.cloudflare.com",
    "payment-stage.ecpay.com.tw", "payment.ecpay.com.tw",
}
CITATION_DATA_MODULES = {
    ROOT / "tianwai" / "release_packages_a.py": "PACKAGES_A",
    ROOT / "tianwai" / "release_packages_b.py": "PACKAGES_B",
}


def _attribute_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _attribute_name(node.value) + "." + node.attr
    return ""


def _citation_literal_nodes(tree, path):
    """Exempt only direct static label/url/note values at the exact data location."""
    expected_name = CITATION_DATA_MODULES.get(path)
    if expected_name is None:
        return set()
    literals = set()
    for statement in tree.body:
        if not (
            isinstance(statement, ast.Assign) and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name) and statement.targets[0].id == expected_name
            and isinstance(statement.value, ast.Dict)
        ):
            continue
        for package in statement.value.values:
            if not isinstance(package, ast.Dict):
                continue
            for key, entries in zip(package.keys, package.values):
                if not (isinstance(key, ast.Constant) and key.value == "sources" and isinstance(entries, (ast.List, ast.Tuple))):
                    continue
                for entry in entries.elts:
                    if not isinstance(entry, ast.Dict) or len(entry.keys) != 3:
                        continue
                    if not all(isinstance(key, ast.Constant) and isinstance(key.value, str) for key in entry.keys):
                        continue
                    fields = {key.value: value for key, value in zip(entry.keys, entry.values)}
                    if set(fields) != {"label", "url", "note"}:
                        continue
                    if not all(isinstance(value, ast.Constant) and isinstance(value.value, str) for value in fields.values()):
                        continue
                    try:
                        parsed = urlsplit(fields["url"].value)
                        valid_url = parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password
                    except ValueError:
                        valid_url = False
                    if valid_url:
                        literals.update(fields.values())
    return literals


def _assert_runtime_boundaries(path, source):
    approved_imports = sys.stdlib_module_names | APPROVED_RUNTIME_PACKAGES
    dynamic_loaders = {
        "__import__", "exec", "eval", "importlib.import_module",
        "importlib.util.spec_from_file_location", "runpy.run_path",
        "sys.path.append", "sys.path.insert", "sys.path.extend",
    }
    tree = ast.parse(source)
    citations = _citation_literal_nodes(tree, path)
    for node in ast.walk(tree):
        location = f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 0)}"
        if isinstance(node, ast.Import):
            assert path not in CITATION_DATA_MODULES, location
            assert all(item.name.split(".")[0] in approved_imports for item in node.names), location
        elif isinstance(node, ast.ImportFrom):
            assert path not in CITATION_DATA_MODULES, location
            if node.level:
                assert node.level == 1, location
            else:
                assert (node.module or "").split(".")[0] in approved_imports, location
        elif isinstance(node, ast.Call):
            assert _attribute_name(node.func) not in dynamic_loaders, location
            if path in CITATION_DATA_MODULES:
                # These two files are literal data plus the existing pure _items
                # formatter; they must never fetch a source, even via an alias.
                assert _attribute_name(node.func) in {"_items", "fields.split", "dict", "zip"}, location
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Citation handling does not relax absolute-path or runtime-host rules.
            assert not re.match(r"^(?:[A-Za-z]:[\\/]|\\\\)", node.value), location
            for url in re.findall(r"https?://[^\s\"'<>;]+", node.value):
                hostname = urlsplit(url).hostname
                if hostname and node not in citations:
                    assert hostname in APPROVED_INTEGRATION_HOSTS, location


def test_runtime_uses_only_local_project_code_and_explicit_integrations():
    # Inspect executable syntax, not handoff prose, comments or other repos.
    runtime = list((ROOT / "tianwai").rglob("*.py")) + [ROOT / "app.py"]
    for path in runtime:
        _assert_runtime_boundaries(path, path.read_text(encoding="utf-8-sig"))


def test_static_research_citations_are_exempt_only_at_the_exact_literal_location():
    source = "PACKAGES_A = {'sealed-twin-tire-safety': {'sources': [{'label': 'Research', 'url': 'https://research.example.invalid/paper', 'note': 'Citation only'}]}}"
    citation_path = ROOT / "tianwai" / "release_packages_a.py"
    _assert_runtime_boundaries(citation_path, source)
    for path, invalid in (
        (ROOT / "tianwai" / "other_module.py", source),
        (citation_path, source.replace("PACKAGES_A", "OTHER_DATA")),
        (citation_path, source.replace("'sources'", "'runtime_config'")),
        (citation_path, source.replace("'note'", "'token'")),
        (citation_path, source + "\nRUNTIME_URL = 'https://research.example.invalid/api'"),
        (citation_path, source.replace("'https://research.example.invalid/paper'", "urlopen('https://research.example.invalid/paper')")),
        (citation_path, source + "\nurlopen(PACKAGES_A['sealed-twin-tire-safety']['sources'][0]['url'])"),
    ):
        with pytest.raises(AssertionError):
            _assert_runtime_boundaries(path, invalid)
    # Approved runtime services retain the exact original host allowlist.
    _assert_runtime_boundaries(ROOT / "tianwai" / "sample_runtime.py", "urlopen('https://api.line.me/v2/bot/message/push')")
    assert "research.example.invalid" not in APPROVED_INTEGRATION_HOSTS


def test_rendering_research_sources_never_fetches_them(app, client, monkeypatch):
    from conftest import login_admin
    from tianwai.commerce import PRICING_BATCH_SLUGS
    from tianwai.release_packages import get_release_package

    def forbid_network(*_args, **_kwargs):
        pytest.fail("Research citations must render as links without network requests")

    monkeypatch.setattr(socket.socket, "connect", forbid_network)
    monkeypatch.setattr(socket.socket, "connect_ex", forbid_network)
    monkeypatch.setattr(socket, "create_connection", forbid_network)
    monkeypatch.setattr(urllib.request, "urlopen", forbid_network)
    monkeypatch.setattr(urllib.request, "urlretrieve", forbid_network)
    login_admin(client)
    inventory = client.get("/admin/api/release-packages")
    assert inventory.status_code == 200 and len(inventory.json["cards"]) == 13
    assert all(get_release_package(slug)["sources"] for slug in PRICING_BATCH_SLUGS)
    for card in inventory.json["cards"]:
        preview = client.get(card["preview_url"])
        assert preview.status_code == 200
        for citation in get_release_package(card["slug"])["sources"]:
            assert str(escape(citation["url"])) in preview.get_data(as_text=True)


def test_workflows_never_dispatch_to_or_load_another_project():
    approved_actions = {"actions/checkout", "actions/setup-python", "actions/upload-artifact"}
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        workflow = "\n".join(
            line.split(" #", 1)[0] for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        assert "repository_dispatch" not in workflow, path.name
        assert not re.search(r"/repos/[^\s]+/(?:dispatches|actions/workflows)", workflow), path.name
        assert not re.search(r"\bgh\s+(?:workflow\s+run|api)\b", workflow), path.name
        assert not re.search(r"^\s*repository\s*:", workflow, re.MULTILINE), path.name
        for target in re.findall(r"^\s*(?:-\s*)?uses:\s*([^\s]+)", workflow, re.MULTILINE):
            action, separator, revision = target.partition("@")
            assert separator and action in approved_actions, path.name
            assert re.fullmatch(r"[0-9a-f]{40}", revision), path.name


def test_daily_notification_workflow_targets_only_tianwai_host():
    workflow = (ROOT / ".github" / "workflows" / "daily-admin-summary.yml").read_text(encoding="utf-8")
    configured_urls = re.findall(r"^\s*BASE_URL:\s*(\S+)\s*$", workflow, re.MULTILINE)
    assert configured_urls == [f"https://{APP_HOST}"]
    assert '"$BASE_URL/internal/notifications/daily-summary"' in workflow
    assert "CRON_SECRET: ${{ secrets.NOTIFICATION_CRON_SECRET }}" in workflow
    assert "permissions:\n  contents: read" in workflow
    # No step may replace the fixed target or forward its private header to a
    # redirect destination. These assertions do not inspect credential values.
    assert not re.search(r"\b(?:export\s+)?BASE_URL\s*=", workflow)
    assert not re.search(r"(?:--location(?:-trusted)?|(?:^|\s)-L(?:\s|$))", workflow)


def test_complete_production_configuration_does_not_implicitly_open_sales(monkeypatch):
    from tianwai import payments

    monkeypatch.setenv("PAYMENT_PROVIDER", "ecpay")
    monkeypatch.setenv("BASE_URL", f"https://{APP_HOST}")
    monkeypatch.delenv("ECPAY_LIVE_CONFIRMED", raising=False)
    monkeypatch.delenv("ECPAY_VERIFICATION_ENABLED", raising=False)
    monkeypatch.delenv("PAYMENT_VERIFICATION_EMAIL", raising=False)
    monkeypatch.setattr(payments, "email_delivery_ready", lambda: True)
    monkeypatch.setattr(payments, "_ecpay_config", lambda: {
        "mode": "production", "merchant_id": "synthetic-merchant",
        "hash_key": "synthetic-key", "hash_iv": "synthetic-iv", "store_id": "TWYB",
    })
    application = Flask("isolated-payment-boundary-test")
    with application.app_context():
        public = payments.payment_checkout_status()
        verification = payments.payment_checkout_status(verification=True)

    for status in (public, verification):
        assert status["configuration_ready"] is True
        assert status["state"] == "closed"
        assert status["provider"] == "unavailable"
        assert status["ready"] is False
        assert status["public_sales_open"] is False
