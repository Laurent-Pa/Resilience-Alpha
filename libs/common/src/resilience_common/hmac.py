"""Signature HMAC-SHA256 des webhooks (`X-Signature: sha256=<hex>` sur le corps brut)."""

import hashlib
import hmac as _hmac

PREFIX = "sha256="


def sign(secret: bytes, body: bytes) -> str:
    return PREFIX + _hmac.new(secret, body, hashlib.sha256).hexdigest()


def verify(secret: bytes, body: bytes, signature: str | None) -> bool:
    if not signature or not signature.startswith(PREFIX):
        return False
    return _hmac.compare_digest(sign(secret, body), signature)
