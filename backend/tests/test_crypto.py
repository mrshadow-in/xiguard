"""crypto encrypt/decrypt round-trip and nonce uniqueness."""
from __future__ import annotations

import pytest

from app.services import crypto


def test_round_trip():
    pt = "hunter2!@#"
    ct = crypto.encrypt(pt)
    assert isinstance(ct, bytes)
    assert ct != pt.encode()
    assert crypto.decrypt(ct) == pt


def test_nonce_uniqueness():
    a = crypto.encrypt("same-plaintext")
    b = crypto.encrypt("same-plaintext")
    assert a != b  # fresh nonce each time
    assert crypto.decrypt(a) == crypto.decrypt(b)


def test_decrypt_truncated_raises():
    with pytest.raises(ValueError):
        crypto.decrypt(b"")
    with pytest.raises(ValueError):
        crypto.decrypt(b"\x00" * 5)
