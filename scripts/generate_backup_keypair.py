"""Generate an encrypted offline 4096-bit RSA backup key pair."""

import argparse
import getpass
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _write_new(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def main():
    parser = argparse.ArgumentParser(description="Generate TianWaiYiBi backup encryption keys")
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--public-key", required=True, type=Path)
    parser.add_argument(
        "--offline-passwordless",
        action="store_true",
        help="create an unencrypted private key for physically offline removable media",
    )
    args = parser.parse_args()
    if args.private_key.exists() or args.public_key.exists():
        raise SystemExit("Refusing to overwrite an existing key file")
    if args.offline_passwordless:
        private_encryption = serialization.NoEncryption()
    else:
        first = getpass.getpass("New offline private-key passphrase: ").encode("utf-8")
        second = getpass.getpass("Confirm passphrase: ").encode("utf-8")
        if first != second or len(first) < 16:
            raise SystemExit("Passphrases must match and contain at least 16 characters")
        private_encryption = serialization.BestAvailableEncryption(first)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        private_encryption,
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    _write_new(args.private_key, private_pem)
    _write_new(args.public_key, public_pem)
    if args.offline_passwordless:
        print("Passwordless offline key pair created. Disconnect and physically secure the removable drive.")
    else:
        print("Key pair created. Keep the private key and passphrase offline; only upload the public key.")


if __name__ == "__main__":
    main()
