"""Minimal server-side Cloudflare Turnstile validation for sensitive public flows."""

import json
import os
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlparse

from flask import current_app


SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
RECOVERY_ACTION = "admin-recovery"


def turnstile_site_key():
    return os.environ.get("TURNSTILE_SITE_KEY", "").strip()


def turnstile_configured():
    return bool(turnstile_site_key() and os.environ.get("TURNSTILE_SECRET_KEY", "").strip())


def _expected_hostname():
    configured = current_app.config.get("WEBAUTHN_RP_ID") or os.environ.get("WEBAUTHN_RP_ID", "")
    if configured:
        return str(configured).strip().lower()
    return str(urlparse(os.environ.get("BASE_URL", "")).hostname or "").lower()


def verify_turnstile(token, remote_ip, expected_action=RECOVERY_ACTION):
    """Fail closed: validate a short-lived, single-use token with Cloudflare."""
    value = str(token or "")
    if not value or len(value) > 2048 or not turnstile_configured():
        return False
    payload = json.dumps(
        {
            "secret": os.environ["TURNSTILE_SECRET_KEY"].strip(),
            "response": value,
            "remoteip": str(remote_ip or "")[:64],
            "idempotency_key": str(uuid.uuid4()),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        SITEVERIFY_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return False
    action = str(expected_action or "")
    if action != RECOVERY_ACTION:
        return False
    if result.get("success") is not True or result.get("action") != action:
        return False
    expected = _expected_hostname()
    hostname = str(result.get("hostname", "")).strip().lower()
    return bool(expected and hostname == expected)
