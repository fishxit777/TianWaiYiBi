"""Encrypt one pg_dump archive; public key may come from a file or environment."""

import argparse
import os
from pathlib import Path

from backup_crypto import encrypt_file


def main():
    parser = argparse.ArgumentParser(description="Encrypt a TianWaiYiBi PostgreSQL backup")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--public-key-file", type=Path)
    args = parser.parse_args()
    if args.public_key_file:
        public_pem = args.public_key_file.read_bytes()
    else:
        public_pem = os.environ.get("BACKUP_PUBLIC_KEY_PEM", "").encode("utf-8")
    if not public_pem:
        raise SystemExit("Backup public key is not configured")
    encrypt_file(args.input, args.output, public_pem)
    print(f"Encrypted backup created ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
