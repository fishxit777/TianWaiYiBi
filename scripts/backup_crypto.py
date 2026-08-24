"""Streaming RSA-OAEP + AES-256-GCM encryption for PostgreSQL backup archives."""

import base64
import json
import os
import struct
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


MAGIC = b"TWYBPG01"
TAG_BYTES = 16
CHUNK_BYTES = 1024 * 1024
MAX_HEADER_BYTES = 64 * 1024
MIN_RSA_BITS = 4096


def _public_key_from_pem(pem):
    key = serialization.load_pem_public_key(bytes(pem))
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size < MIN_RSA_BITS:
        raise ValueError(f"Backup public key must be RSA with at least {MIN_RSA_BITS} bits")
    return key


def _private_key_from_pem(pem, password=None):
    key = serialization.load_pem_private_key(bytes(pem), password=password)
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < MIN_RSA_BITS:
        raise ValueError(f"Backup private key must be RSA with at least {MIN_RSA_BITS} bits")
    return key


def encrypt_file(source, destination, public_key_pem):
    source_path = Path(source)
    destination_path = Path(destination)
    if not source_path.is_file() or source_path.stat().st_size < 1:
        raise ValueError("Backup archive is missing or empty")
    public_key = _public_key_from_pem(public_key_pem)
    data_key = os.urandom(32)
    nonce = os.urandom(12)
    wrapped_key = public_key.encrypt(
        data_key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    header = json.dumps(
        {
            "cipher": "AES-256-GCM",
            "key_wrap": "RSA-OAEP-SHA256",
            "key_bits": public_key.key_size,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "wrapped_key": base64.b64encode(wrapped_key).decode("ascii"),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(header) > MAX_HEADER_BYTES:
        raise ValueError("Backup encryption header is unexpectedly large")
    prefix = MAGIC + struct.pack(">I", len(header)) + header
    temporary = destination_path.with_suffix(destination_path.suffix + ".part")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    encryptor = Cipher(algorithms.AES(data_key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(prefix)
    try:
        with source_path.open("rb") as reader, temporary.open("wb") as writer:
            writer.write(prefix)
            while chunk := reader.read(CHUNK_BYTES):
                writer.write(encryptor.update(chunk))
            writer.write(encryptor.finalize())
            writer.write(encryptor.tag)
        os.replace(temporary, destination_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination_path


def decrypt_file(source, destination, private_key_pem, password=None):
    source_path = Path(source)
    destination_path = Path(destination)
    private_key = _private_key_from_pem(private_key_pem, password=password)
    total_size = source_path.stat().st_size
    with source_path.open("rb") as reader:
        magic = reader.read(len(MAGIC))
        if magic != MAGIC:
            raise ValueError("Unsupported encrypted backup format")
        raw_length = reader.read(4)
        if len(raw_length) != 4:
            raise ValueError("Truncated encrypted backup")
        header_length = struct.unpack(">I", raw_length)[0]
        if header_length < 1 or header_length > MAX_HEADER_BYTES:
            raise ValueError("Invalid encrypted backup header")
        header_raw = reader.read(header_length)
        if len(header_raw) != header_length:
            raise ValueError("Truncated encrypted backup header")
        header = json.loads(header_raw.decode("utf-8"))
        if header.get("cipher") != "AES-256-GCM" or header.get("key_wrap") != "RSA-OAEP-SHA256":
            raise ValueError("Unsupported encrypted backup algorithms")
        nonce = base64.b64decode(header["nonce"], validate=True)
        wrapped_key = base64.b64decode(header["wrapped_key"], validate=True)
        data_key = private_key.decrypt(
            wrapped_key,
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )
        prefix = MAGIC + raw_length + header_raw
        ciphertext_start = len(prefix)
        ciphertext_length = total_size - ciphertext_start - TAG_BYTES
        if ciphertext_length < 1:
            raise ValueError("Encrypted backup has no ciphertext")
        reader.seek(total_size - TAG_BYTES)
        tag = reader.read(TAG_BYTES)
        reader.seek(ciphertext_start)
        decryptor = Cipher(algorithms.AES(data_key), modes.GCM(nonce, tag)).decryptor()
        decryptor.authenticate_additional_data(prefix)
        temporary = destination_path.with_suffix(destination_path.suffix + ".part")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        remaining = ciphertext_length
        try:
            with temporary.open("wb") as writer:
                while remaining:
                    chunk = reader.read(min(CHUNK_BYTES, remaining))
                    if not chunk:
                        raise ValueError("Truncated encrypted backup ciphertext")
                    remaining -= len(chunk)
                    writer.write(decryptor.update(chunk))
                writer.write(decryptor.finalize())
            os.replace(temporary, destination_path)
        finally:
            if temporary.exists():
                temporary.unlink()
    return destination_path
