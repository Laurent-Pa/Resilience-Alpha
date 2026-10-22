"""Chiffrement hybride côté client (RSA-OAEP SHA-256 + AES-256-GCM), compatible WebCrypto.

`seal()` est l'implémentation de référence du front : utilisée par le prober et les tests
de payment-api, qui déchiffre avec `payment_api.crypto.TransferCipher`.
"""

import base64
import json
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

IV_BYTES = 12
OAEP = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


def seal(public_pem: str, payload: dict) -> dict[str, str]:
    """Chiffre `payload` comme le fait le front. Renvoie {encrypted_key, iv, ciphertext}."""
    public_key = serialization.load_pem_public_key(public_pem.encode())
    assert isinstance(public_key, rsa.RSAPublicKey)
    aes_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(IV_BYTES)
    ciphertext = AESGCM(aes_key).encrypt(nonce, json.dumps(payload).encode(), None)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return {
        "encrypted_key": b64(public_key.encrypt(aes_key, OAEP)),
        "iv": b64(nonce),
        "ciphertext": b64(ciphertext),
    }
