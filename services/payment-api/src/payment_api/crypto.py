"""Chiffrement hybride des coordonnées bénéficiaire et pseudonymisation des IBAN.

Protocole (compatible WebCrypto) :
  1. le front récupère la clé publique RSA (GET /payments/public-key) ;
  2. il génère une clé AES-256 et un IV de 12 octets, éphémères ;
  3. il chiffre le JSON {iban, bic, account_holder_name} en AES-GCM
     (WebCrypto renvoie ciphertext || tag de 16 octets : on attend exactement ça) ;
  4. il chiffre la clé AES brute (32 octets) en RSA-OAEP, hash SHA-256 ;
  5. il envoie encrypted_key, iv, ciphertext en base64 standard.

`seal()` (implémentation de référence côté client) vit dans `resilience_common.crypto`.

Les IBAN ne sont jamais stockés en clair : on garde un HMAC-SHA256 avec une clé secrète
(un simple SHA-256 se casserait par force brute, l'espace des IBAN étant petit) et une
version masquée.
"""

import base64
import binascii
import hashlib
import hmac

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from payment_api.domain.rules import UndecryptablePayload
from payment_api.settings import Settings
from resilience_common.crypto import IV_BYTES, OAEP

ALGORITHM = "RSA-OAEP-256"
CONTENT_ENCRYPTION = "A256GCM"
AES_KEY_BYTES = 32


class TransferCipher:
    def __init__(self, private_key: rsa.RSAPrivateKey) -> None:
        self._private_key = private_key
        spki = private_key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.public_pem = (
            private_key.public_key()
            .public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            )
            .decode()
        )
        self.key_id = hashlib.sha256(spki).hexdigest()[:16]

    @classmethod
    def from_pem(cls, pem: bytes) -> "TransferCipher":
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
            raise ValueError("Une clé privée RSA d'au moins 2048 bits est attendue.")
        return cls(key)

    @classmethod
    def generate(cls, key_size: int = 3072) -> "TransferCipher":
        return cls(rsa.generate_private_key(public_exponent=65537, key_size=key_size))

    def decrypt(self, encrypted_key: str, iv: str, ciphertext: str) -> bytes:
        """Toute erreur donne la même exception, sans détail : pas d'oracle de déchiffrement."""
        try:
            wrapped = base64.b64decode(encrypted_key, validate=True)
            nonce = base64.b64decode(iv, validate=True)
            data = base64.b64decode(ciphertext, validate=True)
            if len(nonce) != IV_BYTES:
                raise ValueError("iv")
            aes_key = self._private_key.decrypt(wrapped, OAEP)
            if len(aes_key) != AES_KEY_BYTES:
                raise ValueError("aes key")
            return AESGCM(aes_key).decrypt(nonce, data, None)
        except (ValueError, binascii.Error, InvalidTag) as exc:
            raise UndecryptablePayload() from exc


class Pseudonymizer:
    """HMAC-SHA256 à clé secrète : empreinte des IBAN et des requêtes (idempotence)."""

    def __init__(self, key: bytes) -> None:
        if len(key) < 16:
            raise ValueError("La clé HMAC doit faire au moins 16 octets.")
        self.key = key

    def iban_hash(self, iban: str) -> str:
        return hmac.new(self.key, b"iban:" + iban.encode(), hashlib.sha256).hexdigest()


def pseudonymizer_from(settings: Settings) -> Pseudonymizer:
    if settings.iban_hmac_key is None:
        raise RuntimeError("Secret manquant : $SECRETS_DIR/iban_hmac_key")
    return Pseudonymizer(settings.iban_hmac_key.get_secret_value().strip().encode())


def cipher_from(settings: Settings) -> tuple[TransferCipher, bool]:
    """Renvoie (cipher, éphémère?). Sans secret, une clé est générée au démarrage."""
    if settings.rsa_private_key is not None:
        return TransferCipher.from_pem(settings.rsa_private_key.get_secret_value().encode()), False
    return TransferCipher.generate(), True
