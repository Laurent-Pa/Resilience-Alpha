# Test de la signature HMAC (stdlib seule, pas de deps ML : tourne dans n'importe quel venv).
#   (depuis detection/)  python -m pytest test_signing.py
import hashlib
import hmac

from signing import PREFIX, signer


def test_signature_matches_reference_algo():
    secret, corps = b"s3cr3t", b'{"source":"ml"}'
    attendu = PREFIX + hmac.new(secret, corps, hashlib.sha256).hexdigest()
    assert signer(secret, corps) == attendu
    assert signer(secret, corps).startswith("sha256=")


def test_signature_depends_on_body_and_secret():
    assert signer(b"k", b"a") != signer(b"k", b"b")  # corps différent
    assert signer(b"k1", b"a") != signer(b"k2", b"a")  # secret différent
