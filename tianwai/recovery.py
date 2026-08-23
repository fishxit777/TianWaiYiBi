"""One-time administrator break-glass codes; plaintext is never persisted."""

import base64
import secrets

from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .db import get_db, utc_now
from .security import ADMIN_PASSWORD_HASHER, get_client_ip


RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_BYTES = 16


def _compact_code(value):
    return "".join(character for character in str(value or "").upper() if character.isalnum())


def _display_code(raw):
    return "-".join(raw[index:index + 4] for index in range(0, len(raw), 4))


def generate_recovery_codes():
    """Rotate all available codes and return the new plaintext set exactly once."""
    codes = []
    hashes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = base64.b32encode(secrets.token_bytes(RECOVERY_CODE_BYTES)).decode("ascii").rstrip("=")
        display = _display_code(raw)
        codes.append(display)
        hashes.append(ADMIN_PASSWORD_HASHER.hash(raw))

    connection = get_db()
    now = utc_now()
    connection.execute(
        "UPDATE admin_recovery_codes SET revoked_at = ? WHERE used_at IS NULL AND revoked_at IS NULL",
        (now,),
    )
    for encoded in hashes:
        connection.execute(
            "INSERT INTO admin_recovery_codes (code_hash, created_at) VALUES (?, ?)",
            (encoded, now),
        )
    connection.commit()
    return codes


def available_recovery_code_count():
    row = get_db().execute(
        "SELECT COUNT(*) AS count FROM admin_recovery_codes WHERE used_at IS NULL AND revoked_at IS NULL"
    ).fetchone()
    return int(row["count"])


def consume_recovery_code(code):
    """Verify one code and atomically mark it used; concurrent reuse loses."""
    candidate = _compact_code(code)
    if len(candidate) != 26:
        return False
    connection = get_db()
    rows = connection.execute(
        "SELECT id, code_hash FROM admin_recovery_codes WHERE used_at IS NULL AND revoked_at IS NULL ORDER BY id"
    ).fetchall()
    matched_id = None
    for row in rows:
        try:
            if ADMIN_PASSWORD_HASHER.verify(row["code_hash"], candidate):
                matched_id = row["id"]
                break
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            continue
    if matched_id is None:
        return False
    cursor = connection.execute(
        """
        UPDATE admin_recovery_codes SET used_at = ?, used_ip = ?
        WHERE id = ? AND used_at IS NULL AND revoked_at IS NULL
        """,
        (utc_now(), get_client_ip(), matched_id),
    )
    connection.commit()
    return cursor.rowcount == 1


def revoke_all_passkeys(reason="emergency_recovery"):
    connection = get_db()
    cursor = connection.execute(
        """
        UPDATE admin_webauthn_credentials SET revoked_at = ?, revoked_reason = ?
        WHERE revoked_at IS NULL
        """,
        (utc_now(), str(reason)[:120]),
    )
    connection.commit()
    return cursor.rowcount
