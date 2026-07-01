"""Encryption for secrets at rest (mailbox OAuth tokens).

Addresses the prior review finding that refresh tokens were stored in
plaintext. A Fernet key is derived from NEMO_TOKEN_KEY (preferred) or the
Django SECRET_KEY as a fallback. In production set a dedicated NEMO_TOKEN_KEY
(a 32-byte urlsafe-base64 value, e.g. `Fernet.generate_key()`).
"""
import base64
import hashlib
import json
import os

from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    raw = os.getenv("NEMO_TOKEN_KEY")
    if raw:
        return Fernet(raw.encode() if isinstance(raw, str) else raw)
    # Fallback: derive a stable key from the Django secret. Fine for dev;
    # set NEMO_TOKEN_KEY explicitly in production.
    from django.conf import settings

    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_tokens(tokens: dict) -> bytes:
    return _fernet().encrypt(json.dumps(tokens).encode())


def decrypt_tokens(blob: bytes | None) -> dict:
    if not blob:
        return {}
    return json.loads(_fernet().decrypt(bytes(blob)).decode())
