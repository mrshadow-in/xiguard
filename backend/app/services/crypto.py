"""AES-256-GCM credential encryption.

Encryption key comes from settings.encryption_key (base64-encoded 32 bytes).
Each ciphertext is prefixed with a fresh 12-byte nonce: ``nonce || ct || tag``.
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


def _load_key() -> bytes:
    raw = settings.encryption_key.strip()
    if not raw:
        raise RuntimeError(
            "ENCRYPTION_KEY env var is not set. Generate one with: "
            'python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"'
        )
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise RuntimeError(f"ENCRYPTION_KEY must decode to 32 bytes, got {len(key)}")
    return key


_KEY: bytes | None = None


def _key() -> bytes:
    global _KEY
    if _KEY is None:
        _KEY = _load_key()
    return _KEY


def encrypt(plaintext: str) -> bytes:
    if plaintext is None:
        raise ValueError("plaintext must not be None")
    aes = AESGCM(_key())
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return nonce + ct


def decrypt(blob: bytes) -> str:
    if blob is None or len(blob) < 13:
        raise ValueError("ciphertext is empty or truncated")
    nonce, ct = blob[:12], blob[12:]
    aes = AESGCM(_key())
    pt = aes.decrypt(nonce, ct, associated_data=None)
    return pt.decode("utf-8")
