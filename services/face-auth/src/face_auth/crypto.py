"""Chiffrement des empreintes faciales au repos (donnée biométrique, RGPD art. 9).

AES-256-GCM, nonce aléatoire de 12 octets préfixé au chiffré. L'identifiant sert de
donnée authentifiée : une empreinte recopiée sur la ligne d'un autre utilisateur ne se
déchiffre pas.
"""

import os

import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_LEN = 12


class TemplateCipher:
    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("biometric_key : 32 octets attendus (64 caractères hex)")
        self._aead = AESGCM(key)

    @classmethod
    def from_hex(cls, value: str) -> "TemplateCipher":
        return cls(bytes.fromhex(value.strip()))

    def seal(self, username: str, embedding: np.ndarray) -> bytes:
        nonce = os.urandom(NONCE_LEN)
        data = embedding.astype(np.float32).tobytes()
        return nonce + self._aead.encrypt(nonce, data, username.encode())

    def open(self, username: str, blob: bytes) -> np.ndarray:
        nonce, ct = blob[:NONCE_LEN], blob[NONCE_LEN:]
        return np.frombuffer(self._aead.decrypt(nonce, ct, username.encode()), dtype=np.float32)
