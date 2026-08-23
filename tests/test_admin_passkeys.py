import base64
import json
from types import SimpleNamespace

import pytest

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
    with app.test_request_context("/admin/passkeys/authentication/options"):
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
    with app.test_request_context("/admin/passkeys/authentication/options"):
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


def test_authentication_options_include_only_active_credentials(app):
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
    with app.test_request_context("/admin/passkeys/authentication/options"):
        store_registration_result(verified, label="Phone", transports=["hybrid"])
        options, challenge = begin_authentication()
        payload = json.loads(options)

        assert len(challenge) == 32
        assert payload["rpId"] == "localhost"
        assert payload["userVerification"] == "required"
        assert len(payload["allowCredentials"]) == 1


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
    with app.test_request_context("/admin/passkeys/authentication/verify"):
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
    with app.test_request_context("/admin/passkeys/authentication/verify"):
        with pytest.raises(ValueError, match="無效的 Passkey"):
            verify_and_update_authentication(
                {"id": credential_b64, "rawId": credential_b64},
                expected_challenge=b"x" * 32,
            )
