"""Generate a one-time 256-bit admin password and its Argon2id verifier."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tianwai.security import (  # noqa: E402
    ADMIN_PASSWORD_ENTROPY_BITS,
    generate_admin_password,
    hash_admin_password,
)


def main() -> None:
    password = generate_admin_password()
    encoded_hash = hash_admin_password(password)
    print("Save ADMIN_PASSWORD in a password manager now; it will not be written to disk.")
    print(f"length={len(password)} entropy_bits={ADMIN_PASSWORD_ENTROPY_BITS}")
    print(f"ADMIN_PASSWORD={password}")
    print(f"ADMIN_PASSWORD_HASH={encoded_hash}")
    print("After testing the hash, remove the legacy ADMIN_PASSWORD from production.")


if __name__ == "__main__":
    main()
