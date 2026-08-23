"""Owner-only offline backup decryption; the passphrase is prompted, never a CLI argument."""

import argparse
import getpass
from pathlib import Path

from backup_crypto import decrypt_file


def main():
    parser = argparse.ArgumentParser(description="Decrypt a TianWaiYiBi PostgreSQL backup offline")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--private-key-file", required=True, type=Path)
    args = parser.parse_args()
    password = getpass.getpass("Backup private-key passphrase: ").encode("utf-8")
    decrypt_file(args.input, args.output, args.private_key_file.read_bytes(), password=password)
    print(f"Decrypted archive created at {args.output}")


if __name__ == "__main__":
    main()
