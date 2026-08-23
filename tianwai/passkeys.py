"""WebAuthn ceremonies and durable administrator Passkey records."""

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from flask import current_app, request
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .db import get_db, utc_now


CHALLENGE_BYTES = 32
CHALLENGE_TTL_MINUTES = 5


def _client_ip():
    if os.environ.get("TRUST_PROXY", "").strip().lower() in {"1", "true", "yes", "on"}:
        forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if forwarded:
            return forwarded[:64]
    return (request.remote_addr or "unknown")[:64]


def _user_agent():
    return request.headers.get("User-Agent", "")[:240]


def webauthn_origin():
    configured = (
        current_app.config.get("WEBAUTHN_ORIGIN")
        or os.environ.get("WEBAUTHN_ORIGIN")
        or os.environ.get("BASE_URL")
        or request.host_url.rstrip("/")
    )
    return str(configured).strip().rstrip("/")


def webauthn_rp_id():
    configured = current_app.config.get("WEBAUTHN_RP_ID") or os.environ.get("WEBAUTHN_RP_ID")
    if configured:
        return str(configured).strip().lower()
    return str(urlparse(webauthn_origin()).hostname or "").lower()


def _challenge_hash(purpose, challenge):
    secret = str(current_app.config["SECRET_KEY"]).encode("utf-8")
    return hmac.new(
        secret,
        str(purpose).encode("utf-8") + b":" + bytes(challenge),
        hashlib.sha256,
    ).hexdigest()


def create_challenge(purpose):
    if purpose not in {"registration", "authentication"}:
        raise ValueError("Unsupported WebAuthn challenge purpose")
    challenge = secrets.token_bytes(CHALLENGE_BYTES)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=CHALLENGE_TTL_MINUTES)
    connection = get_db()
    connection.execute(
        """
        INSERT INTO admin_webauthn_challenges
            (challenge_hash, purpose, ip, user_agent, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            _challenge_hash(purpose, challenge),
            purpose,
            _client_ip(),
            _user_agent(),
            now.isoformat(timespec="seconds"),
            expires.isoformat(timespec="seconds"),
        ),
    )
    connection.commit()
    return challenge


def consume_challenge(purpose, challenge):
    connection = get_db()
    cursor = connection.execute(
        """
        UPDATE admin_webauthn_challenges
        SET used_at = ?
        WHERE challenge_hash = ? AND purpose = ? AND used_at IS NULL
          AND expires_at > ? AND ip = ? AND user_agent = ?
        """,
        (
            utc_now(),
            _challenge_hash(purpose, challenge),
            purpose,
            utc_now(),
            _client_ip(),
            _user_agent(),
        ),
    )
    connection.commit()
    return cursor.rowcount == 1


def _transport_values(transports):
    allowed = {item.value for item in AuthenticatorTransport}
    return sorted({str(item) for item in (transports or []) if str(item) in allowed})


def _transport_enums(transports_json):
    try:
        values = json.loads(transports_json or "[]")
    except (TypeError, ValueError):
        values = []
    allowed = {item.value: item for item in AuthenticatorTransport}
    return [allowed[value] for value in values if value in allowed]


def active_credentials():
    return get_db().execute(
        """
        SELECT * FROM admin_webauthn_credentials
        WHERE revoked_at IS NULL
        ORDER BY created_at, id
        """
    ).fetchall()


def active_credential_count():
    row = get_db().execute(
        "SELECT COUNT(*) AS count FROM admin_webauthn_credentials WHERE revoked_at IS NULL"
    ).fetchone()
    return int(row["count"])


def passkey_only_enabled():
    row = get_db().execute(
        "SELECT value FROM settings WHERE key = 'admin_auth_mode'"
    ).fetchone()
    return bool(row and row["value"] == "passkey")


def activate_passkey_only():
    if active_credential_count() < 2:
        return False
    connection = get_db()
    connection.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES ('admin_auth_mode', 'passkey', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (utc_now(),),
    )
    connection.commit()
    return True


def get_credential(credential_id):
    return get_db().execute(
        """
        SELECT * FROM admin_webauthn_credentials
        WHERE credential_id = ? AND revoked_at IS NULL
        LIMIT 1
        """,
        (bytes(credential_id),),
    ).fetchone()


def begin_registration():
    challenge = create_challenge("registration")
    username = os.environ.get("ADMIN_USERNAME", "keeper")
    secret = str(current_app.config["SECRET_KEY"]).encode("utf-8")
    user_handle = hmac.new(secret, f"admin:{username}".encode("utf-8"), hashlib.sha256).digest()
    exclude = [
        PublicKeyCredentialDescriptor(
            id=bytes(row["credential_id"]),
            transports=_transport_enums(row["transports_json"]),
        )
        for row in active_credentials()
    ]
    options = generate_registration_options(
        rp_id=webauthn_rp_id(),
        rp_name="天外一筆・仙策閣",
        user_name=username,
        user_id=user_handle,
        user_display_name="天外一筆管理員",
        challenge=challenge,
        timeout=300_000,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=exclude,
        supported_pub_key_algs=[
            COSEAlgorithmIdentifier.ECDSA_SHA_256,
            COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
        ],
    )
    return options_to_json(options), challenge


def begin_authentication():
    challenge = create_challenge("authentication")
    allow = [
        PublicKeyCredentialDescriptor(
            id=bytes(row["credential_id"]),
            transports=_transport_enums(row["transports_json"]),
        )
        for row in active_credentials()
    ]
    options = generate_authentication_options(
        rp_id=webauthn_rp_id(),
        challenge=challenge,
        timeout=300_000,
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return options_to_json(options), challenge


def store_registration_result(verified, label, transports=None):
    if not getattr(verified, "user_verified", False):
        raise ValueError("Passkey registration did not verify the administrator")
    clean_label = str(label or "Passkey").strip()[:80] or "Passkey"
    transport_values = _transport_values(transports)
    connection = get_db()
    cursor = connection.execute(
        """
        INSERT INTO admin_webauthn_credentials
            (credential_id, public_key, sign_count, transports_json, device_type,
             backed_up, aaguid, label, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            bytes(verified.credential_id),
            bytes(verified.credential_public_key),
            int(verified.sign_count),
            json.dumps(transport_values, separators=(",", ":")),
            str(verified.credential_device_type.value),
            1 if verified.credential_backed_up else 0,
            str(verified.aaguid)[:80],
            clean_label,
            utc_now(),
        ),
    )
    connection.commit()
    return cursor.lastrowid


def verify_and_store_registration(credential, expected_challenge, label, transports=None):
    verified = verify_registration_response(
        credential=credential,
        expected_challenge=bytes(expected_challenge),
        expected_rp_id=webauthn_rp_id(),
        expected_origin=webauthn_origin(),
        require_user_verification=True,
        supported_pub_key_algs=[
            COSEAlgorithmIdentifier.ECDSA_SHA_256,
            COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
        ],
    )
    return store_registration_result(
        verified,
        label=label,
        transports=transports,
    )


def revoke_credential(credential_id, reason="owner_revoked"):
    connection = get_db()
    cursor = connection.execute(
        """
        UPDATE admin_webauthn_credentials
        SET revoked_at = ?, revoked_reason = ?
        WHERE id = ? AND revoked_at IS NULL
        """,
        (utc_now(), str(reason)[:120], int(credential_id)),
    )
    connection.commit()
    return cursor.rowcount == 1


def verify_and_update_authentication(credential, expected_challenge):
    try:
        credential_id = base64url_to_bytes(str(credential.get("id", "")))
    except Exception as error:
        raise ValueError("無效的 Passkey") from error
    stored = get_credential(credential_id)
    if stored is None:
        raise ValueError("無效的 Passkey")
    verified = verify_authentication_response(
        credential=credential,
        expected_challenge=bytes(expected_challenge),
        expected_rp_id=webauthn_rp_id(),
        expected_origin=webauthn_origin(),
        credential_public_key=bytes(stored["public_key"]),
        credential_current_sign_count=int(stored["sign_count"]),
        require_user_verification=True,
    )
    connection = get_db()
    connection.execute(
        """
        UPDATE admin_webauthn_credentials
        SET sign_count = ?, device_type = ?, backed_up = ?, last_used_at = ?
        WHERE id = ? AND revoked_at IS NULL
        """,
        (
            int(verified.new_sign_count),
            str(verified.credential_device_type.value),
            1 if verified.credential_backed_up else 0,
            utc_now(),
            stored["id"],
        ),
    )
    connection.commit()
    return verified
