from pathlib import Path
import subprocess
import sys

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from scripts.backup_crypto import MAGIC, decrypt_file, encrypt_file


@pytest.fixture(scope="module")
def rsa_material():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def test_backup_encryption_round_trip_and_no_plaintext(tmp_path, rsa_material):
    private_pem, public_pem = rsa_material
    plaintext = (b"CUSTOM-PG-DUMP\x00owner@example.com\x00secret-row\n" * 50000)
    source = tmp_path / "database.dump"
    encrypted = tmp_path / "database.twybenc"
    restored = tmp_path / "restored.dump"
    source.write_bytes(plaintext)

    encrypt_file(source, encrypted, public_pem)
    ciphertext = encrypted.read_bytes()
    assert ciphertext.startswith(MAGIC)
    assert b"owner@example.com" not in ciphertext
    assert b"secret-row" not in ciphertext

    decrypt_file(encrypted, restored, private_pem)
    assert restored.read_bytes() == plaintext


def test_tampered_backup_fails_authentication(tmp_path, rsa_material):
    private_pem, public_pem = rsa_material
    source = tmp_path / "source.dump"
    encrypted = tmp_path / "encrypted.twybenc"
    restored = tmp_path / "restored.dump"
    source.write_bytes(b"database backup content")
    encrypt_file(source, encrypted, public_pem)
    payload = bytearray(encrypted.read_bytes())
    payload[-20] ^= 0x01
    encrypted.write_bytes(payload)

    with pytest.raises(InvalidTag):
        decrypt_file(encrypted, restored, private_pem)
    assert not restored.exists()


def test_backup_encryption_rejects_weak_rsa_key(tmp_path):
    weak = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    weak_public = weak.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    source = tmp_path / "source.dump"
    source.write_bytes(b"content")
    with pytest.raises(ValueError, match="at least 4096 bits"):
        encrypt_file(source, tmp_path / "output.twybenc", weak_public)


def test_explicit_offline_passwordless_generator_creates_matching_rsa4096_pair(tmp_path):
    root = Path(__file__).resolve().parents[1]
    private_path = tmp_path / "backup-private.pem"
    public_path = tmp_path / "backup-public.pem"

    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "generate_backup_keypair.py"),
            "--private-key",
            str(private_path),
            "--public-key",
            str(public_path),
            "--offline-passwordless",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "PRIVATE KEY" not in result.stdout
    private_key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    public_key = serialization.load_pem_public_key(public_path.read_bytes())
    assert isinstance(private_key, rsa.RSAPrivateKey)
    assert isinstance(public_key, rsa.RSAPublicKey)
    assert private_key.key_size == 4096
    assert public_key.key_size == 4096
    assert private_key.public_key().public_numbers() == public_key.public_numbers()


def test_workflow_uploads_only_validated_encrypted_artifact_with_free_limits():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "postgres-backup.yml").read_text(encoding="utf-8")
    upload_block = workflow.split("- name: Upload encrypted artifact only", 1)[1]

    assert "permissions:\n  contents: read" in workflow
    assert "timeout-minutes: 10" in workflow
    assert "pg_dump --format=custom" in workflow
    assert workflow.index("pg_restore --list") < workflow.index("encrypt_backup.py")
    assert workflow.index("encrypt_backup.py") < workflow.index("Upload encrypted artifact only")
    assert "retention-days: 14" in upload_block
    assert "compression-level: 0" in upload_block
    assert "steps.encrypt.outputs.artifact_path" in upload_block
    assert "database.dump" not in upload_block
    assert "MAX_ENCRYPTED_BYTES: \"25000000\"" in workflow
    assert "contents: write" not in workflow
    assert "pull-requests: write" not in workflow
    assert "echo \"$DATABASE_URL\"" not in workflow
    assert "BACKUP_PRIVATE" not in workflow


def test_repository_ignores_plain_backups_private_keys_and_recovery_exports():
    ignore = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8")
    assert "*.dump" in ignore
    assert "*.twybenc" in ignore
    assert "*backup-private*.pem" in ignore
    assert "*recovery-codes*.txt" in ignore
