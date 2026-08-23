from datetime import datetime, timedelta, timezone

import pytest

from scripts.admin_credential_handoff import HandoffError, create_handoff
from tianwai.security import verify_admin_password


def test_local_handoff_generates_verified_credential_without_repr_leak():
    handoff = create_handoff()

    assert len(handoff.password) == 43
    assert verify_admin_password(handoff.password, handoff.encoded_hash) is True
    assert handoff.password not in repr(handoff)
    assert handoff.encoded_hash not in repr(handoff)
    assert handoff.password not in str(handoff.public_status())
    assert handoff.encoded_hash not in str(handoff.public_status())


def test_local_handoff_requires_copy_and_explicit_saved_confirmation():
    handoff = create_handoff()

    with pytest.raises(HandoffError, match="password_not_copied"):
        handoff.mark_hash_copied(True)

    handoff.mark_password_copied()
    with pytest.raises(HandoffError, match="password_not_saved"):
        handoff.mark_hash_copied(False)

    handoff.mark_hash_copied(True)
    assert handoff.public_status() == {
        "status": "ready_for_render",
        "length": 43,
        "entropy_bits": 256,
        "argon2id": True,
    }

    handoff.mark_completed()
    assert handoff.public_status()["status"] == "completed"


def test_local_handoff_expires_after_thirty_minutes():
    created_at = datetime(2026, 8, 23, 0, 0, tzinfo=timezone.utc)
    handoff = create_handoff(created_at)
    expired_at = created_at + timedelta(minutes=30)

    assert handoff.is_expired(expired_at) is True
    with pytest.raises(HandoffError, match="handoff_expired"):
        handoff.mark_password_copied(expired_at)


def test_local_handoff_cannot_complete_before_render_hash_is_copied():
    handoff = create_handoff()

    with pytest.raises(HandoffError, match="render_hash_not_copied"):
        handoff.mark_completed()
