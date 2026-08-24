import base64
import json
from types import SimpleNamespace

import pytest

from conftest import login_admin, set_public_csrf
from tianwai.db import get_db, utc_now
from tianwai.passkeys import (
    active_credential_count,
    begin_authentication,
    begin_registration,
    consume_challenge,
    create_challenge,
    get_credential,
    revoke_credential,
    store_registration_result,
    verify_and_store_registration,
    verify_and_update_authentication,
)


def test_webauthn_challenge_is_hashed_at_rest_and_single_use(app):
    with app.test_request_context("/admin/identity/options"):
        challenge = create_challenge("authentication")
        encoded = base64.urlsafe_b64encode(challenge).decode("ascii").rstrip("=")
        row = get_db().execute(
            "SELECT * FROM admin_webauthn_challenges ORDER BY id DESC LIMIT 1"
        ).fetchone()

        assert len(challenge) == 32
        assert row["challenge_hash"] != encoded
        assert encoded not in " ".join(str(value) for value in dict(row).values())
        assert consume_challenge("authentication", challenge) is True
        assert consume_challenge("authentication", challenge) is False


def test_expired_webauthn_challenge_is_rejected(app):
    with app.test_request_context("/admin/identity/options"):
        challenge = create_challenge("authentication")
        get_db().execute(
            "UPDATE admin_webauthn_challenges SET expires_at = ?",
            ("2000-01-01T00:00:00+00:00",),
        )
        get_db().commit()
        assert consume_challenge("authentication", challenge) is False


def test_registration_options_require_resident_key_and_user_verification(app):
    app.config.update(
        WEBAUTHN_RP_ID="localhost",
        WEBAUTHN_ORIGIN="http://localhost",
    )
    with app.test_request_context("/admin/passkeys/registration/options"):
        options, challenge = begin_registration()
        payload = json.loads(options)

        assert len(challenge) == 32
        assert payload["rp"]["id"] == "localhost"
        assert payload["authenticatorSelection"]["residentKey"] == "required"
        assert payload["authenticatorSelection"]["userVerification"] == "required"
        assert payload["attestation"] == "none"


def test_store_and_revoke_registration_without_private_key(app):
    verified = SimpleNamespace(
        credential_id=b"credential-id",
        credential_public_key=b"public-cose-key",
        sign_count=1,
        aaguid="00000000-0000-0000-0000-000000000000",
        credential_device_type=SimpleNamespace(value="single_device"),
        credential_backed_up=False,
        user_verified=True,
    )
    with app.test_request_context("/admin/passkeys/registration/verify"):
        credential_id = store_registration_result(
            verified,
            label="Windows Hello",
            transports=["internal", "hybrid"],
        )
        row = get_credential(b"credential-id")

        assert credential_id == row["id"]
        assert row["public_key"] == b"public-cose-key"
        assert row["label"] == "Windows Hello"
        assert "private" not in " ".join(row.keys()).lower()
        assert active_credential_count() == 1
        assert revoke_credential(credential_id, "owner_revoked") is True
        assert active_credential_count() == 0
        assert get_credential(b"credential-id") is None


def test_registration_uses_exact_origin_rp_and_user_verification(app, monkeypatch):
    app.config.update(
        WEBAUTHN_RP_ID="tianwai-yibi.onrender.com",
        WEBAUTHN_ORIGIN="https://tianwai-yibi.onrender.com",
    )
    captured = {}

    def fake_verify(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            credential_id=b"registered-id",
            credential_public_key=b"registered-public-key",
            sign_count=0,
            aaguid="aaguid",
            credential_device_type=SimpleNamespace(value="multi_device"),
            credential_backed_up=True,
            user_verified=True,
        )

    monkeypatch.setattr("tianwai.passkeys.verify_registration_response", fake_verify)
    with app.test_request_context("/admin/passkeys/registration/verify"):
        credential_id = verify_and_store_registration(
            {"id": "ignored-by-fake"},
            expected_challenge=b"r" * 32,
            label="iPhone Passkey",
            transports=["hybrid"],
        )

        assert credential_id > 0
        assert captured["expected_rp_id"] == "tianwai-yibi.onrender.com"
        assert captured["expected_origin"] == "https://tianwai-yibi.onrender.com"
        assert captured["require_user_verification"] is True


def test_authentication_options_do_not_disclose_registered_credentials(app):
    verified = SimpleNamespace(
        credential_id=b"active-id",
        credential_public_key=b"public-key",
        sign_count=0,
        aaguid="aaguid",
        credential_device_type=SimpleNamespace(value="multi_device"),
        credential_backed_up=True,
        user_verified=True,
    )
    app.config.update(WEBAUTHN_RP_ID="localhost", WEBAUTHN_ORIGIN="http://localhost")
    with app.test_request_context("/admin/identity/options"):
        store_registration_result(verified, label="Phone", transports=["hybrid"])
        options, challenge = begin_authentication()
        payload = json.loads(options)

        assert len(challenge) == 32
        assert payload["rpId"] == "localhost"
        assert payload["userVerification"] == "required"
        assert payload.get("allowCredentials", []) == []
        encoded_credential_id = base64.urlsafe_b64encode(b"active-id").decode("ascii").rstrip("=")
        assert encoded_credential_id not in options


def test_authentication_uses_exact_origin_and_updates_counter(app, monkeypatch):
    verified = SimpleNamespace(
        credential_id=b"credential-id",
        credential_public_key=b"public-key",
        sign_count=3,
        aaguid="aaguid",
        credential_device_type=SimpleNamespace(value="single_device"),
        credential_backed_up=False,
        user_verified=True,
    )
    app.config.update(
        WEBAUTHN_RP_ID="tianwai-yibi.onrender.com",
        WEBAUTHN_ORIGIN="https://tianwai-yibi.onrender.com",
    )
    captured = {}

    def fake_verify(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            credential_id=b"credential-id",
            new_sign_count=4,
            credential_device_type=SimpleNamespace(value="single_device"),
            credential_backed_up=False,
            user_verified=True,
        )

    monkeypatch.setattr("tianwai.passkeys.verify_authentication_response", fake_verify)
    credential_b64 = base64.urlsafe_b64encode(b"credential-id").decode("ascii").rstrip("=")
    with app.test_request_context("/admin/identity/verify"):
        store_registration_result(verified, label="Windows Hello", transports=["internal"])
        result = verify_and_update_authentication(
            {"id": credential_b64, "rawId": credential_b64},
            expected_challenge=b"x" * 32,
        )
        row = get_credential(b"credential-id")

        assert result.user_verified is True
        assert captured["expected_rp_id"] == "tianwai-yibi.onrender.com"
        assert captured["expected_origin"] == "https://tianwai-yibi.onrender.com"
        assert captured["require_user_verification"] is True
        assert row["sign_count"] == 4
        assert row["last_used_at"] >= utc_now()[:10]


def test_unknown_or_revoked_credential_is_rejected(app):
    credential_b64 = base64.urlsafe_b64encode(b"missing").decode("ascii").rstrip("=")
    with app.test_request_context("/admin/identity/verify"):
        with pytest.raises(ValueError, match="無效的 Passkey"):
            verify_and_update_authentication(
                {"id": credential_b64, "rawId": credential_b64},
                expected_challenge=b"x" * 32,
            )


def _insert_passkey(app, credential_id, label):
    with app.test_request_context("/admin/passkeys/setup"):
        verified = SimpleNamespace(
            credential_id=credential_id,
            credential_public_key=b"public-key-" + credential_id,
            sign_count=0,
            aaguid="aaguid",
            credential_device_type=SimpleNamespace(value="multi_device"),
            credential_backed_up=True,
            user_verified=True,
        )
        return store_registration_result(
            verified,
            label=label,
            transports=["hybrid"],
        )


def test_registration_api_requires_admin_and_csrf(app, client):
    unauthenticated = client.post("/admin/api/passkeys/registration/options")
    assert unauthenticated.status_code == 401

    csrf = login_admin(client)
    missing_csrf = client.post("/admin/api/passkeys/registration/options")
    accepted = client.post(
        "/admin/api/passkeys/registration/options",
        headers={"X-CSRF-Token": csrf},
    )
    assert missing_csrf.status_code == 403
    assert accepted.status_code == 200
    assert accepted.get_json()["publicKey"]["rp"]["id"] == "localhost"


def test_registration_api_stores_verified_passkey(app, client, monkeypatch):
    csrf = login_admin(client)
    options = client.post(
        "/admin/api/passkeys/registration/options",
        headers={"X-CSRF-Token": csrf},
    )
    assert options.status_code == 200

    monkeypatch.setattr(
        "tianwai.admin.verify_and_store_registration",
        lambda credential, expected_challenge, label, transports: 42,
    )
    verified = client.post(
        "/admin/api/passkeys/registration/verify",
        json={"credential": {"id": "test"}, "label": "Windows Hello", "transports": ["internal"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert verified.status_code == 200
    assert verified.get_json()["credential_id"] == 42


def test_passkey_login_creates_admin_session(app, client, monkeypatch):
    _insert_passkey(app, b"login-credential", "Windows Hello")
    csrf = set_public_csrf(client, "passkey-login-csrf")
    options = client.post(
        "/admin/identity/options",
        headers={"X-CSRF-Token": csrf},
    )
    assert options.status_code == 200

    monkeypatch.setattr(
        "tianwai.admin.verify_and_update_authentication",
        lambda credential, expected_challenge: SimpleNamespace(user_verified=True),
    )
    verified = client.post(
        "/admin/identity/verify",
        json={"credential": {"id": "test"}},
        headers={"X-CSRF-Token": csrf},
    )
    assert verified.status_code == 200
    assert verified.get_json()["redirect"] == "/admin"
    assert client.get_cookie("twyb_admin", path="/admin") is not None
    assert client.get("/admin").status_code == 200


def test_passkey_only_mode_requires_two_credentials_and_disables_password(app, client):
    csrf = login_admin(client)
    _insert_passkey(app, b"first", "Windows Hello")
    rejected = client.post(
        "/admin/api/passkeys/activate",
        headers={"X-CSRF-Token": csrf},
    )
    assert rejected.status_code == 409

    _insert_passkey(app, b"second", "iPhone Passkey")
    activated = client.post(
        "/admin/api/passkeys/activate",
        headers={"X-CSRF-Token": csrf},
    )
    assert activated.status_code == 200
    client.post("/admin/logout", data={"csrf_token": csrf})

    login_page = client.get("/admin/login").get_data(as_text=True)
    assert "驗證身分" in login_page
    assert 'name="password"' not in login_page
    assert "static/admin-identity.js" in login_page
    assert "static/admin-passkey.js" not in login_page
    assert 'href="/admin/recovery"' not in login_page
    assert "passkey" not in login_page.lower()
    assert "訂單" not in login_page
    assert "營運數據" not in login_page
    for disclosure in (
        "Passkey",
        "Windows Hello",
        "手機",
        "硬體金鑰",
        "兩把",
        "一般密碼登入",
        "緊急復原",
    ):
        assert disclosure not in login_page
    blocked_password = client.post(
        "/admin/login",
        data={"username": "keeper", "password": "correct-horse-battery-staple"},
    )
    assert blocked_password.status_code == 404


def test_public_identity_script_and_errors_use_neutral_language(app, client):
    csrf = set_public_csrf(client, "neutral-identity-csrf")
    unavailable = client.post(
        "/admin/identity/options",
        headers={"X-CSRF-Token": csrf},
    )
    _insert_passkey(app, b"login-credential", "Windows Hello")

    expired = client.post(
        "/admin/identity/verify",
        json={"credential": {"id": "test"}},
        headers={"X-CSRF-Token": csrf},
    )
    script = client.get("/static/admin-identity.js").get_data(as_text=True)
    old_options = client.post(
        "/admin/passkeys/authentication/options",
        headers={"X-CSRF-Token": csrf},
    )
    old_verify = client.post(
        "/admin/passkeys/authentication/verify",
        json={"credential": {"id": "test"}},
        headers={"X-CSRF-Token": csrf},
    )

    assert unavailable.status_code == 403
    assert unavailable.get_json()["error"] == "無法完成身分驗證。"
    assert expired.status_code == 400
    assert expired.get_json()["error"] == "驗證已過期，請重新操作。"
    assert old_options.status_code == 404
    assert old_verify.status_code == 404
    for disclosure in ("Passkey", "Windows Hello", "兩把", "緊急復原", "/passkeys/"):
        assert disclosure not in script
        assert disclosure not in expired.get_data(as_text=True)


def test_public_identity_challenge_issuance_is_rate_limited(app, client):
    _insert_passkey(app, b"login-credential", "Windows Hello")
    csrf = set_public_csrf(client, "rate-limit-identity-csrf")

    for _ in range(10):
        response = client.post(
            "/admin/identity/options",
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200

    limited = client.post(
        "/admin/identity/options",
        headers={"X-CSRF-Token": csrf},
    )
    assert limited.status_code == 429
    assert limited.get_json()["error"] == "請求過於頻繁，請稍後再試。"


def test_passkey_setup_lists_credentials_and_never_public_keys(app, client):
    _insert_passkey(app, b"secret-credential-id", "Windows Hello")
    login_admin(client)
    response = client.get("/admin/passkeys/setup")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Windows Hello" in body
    assert "secret-credential-id" not in body
    assert "public-key-secret-credential-id" not in body
