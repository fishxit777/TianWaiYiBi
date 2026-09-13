"""Guard independently deployed project boundaries without reading other projects."""

import ast
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
APP_HOST = "tianwai-yibi.onrender.com"
APPROVED_RUNTIME_PACKAGES = {"tianwai", "flask", "argon2", "psycopg", "webauthn"}
APPROVED_INTEGRATION_HOSTS = {
    APP_HOST, "localhost", "127.0.0.1",
    "api.line.me", "api.brevo.com", "challenges.cloudflare.com",
    "payment-stage.ecpay.com.tw", "payment.ecpay.com.tw",
}


def _attribute_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _attribute_name(node.value) + "." + node.attr
    return ""


def test_runtime_uses_only_local_project_code_and_explicit_integrations():
    # Inspect executable syntax, not handoff prose, comments or other repos.
    runtime = list((ROOT / "tianwai").rglob("*.py")) + [ROOT / "app.py"]
    approved_imports = sys.stdlib_module_names | APPROVED_RUNTIME_PACKAGES
    dynamic_loaders = {
        "__import__", "exec", "eval", "importlib.import_module",
        "importlib.util.spec_from_file_location", "runpy.run_path",
        "sys.path.append", "sys.path.insert", "sys.path.extend",
    }
    for path in runtime:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            location = f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, ast.Import):
                assert all(item.name.split(".")[0] in approved_imports for item in node.names), location
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    assert node.level == 1, location
                else:
                    assert (node.module or "").split(".")[0] in approved_imports, location
            elif isinstance(node, ast.Call):
                assert _attribute_name(node.func) not in dynamic_loaders, location
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # A runtime mount must be configured for this deployment, never
                # hard-coded to an absolute sibling checkout or network share.
                assert not re.match(r"^(?:[A-Za-z]:[\\/]|\\\\)", node.value), location
                for url in re.findall(r"https?://[^\s\"'<>;]+", node.value):
                    hostname = urlsplit(url).hostname
                    if hostname:
                        assert hostname in APPROVED_INTEGRATION_HOSTS, location


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
