"""Chiffrement hybride et pseudonymisation, sans base de données."""

import json

import pytest

from payment_api.crypto import Pseudonymizer, TransferCipher, seal
from payment_api.domain.rules import UndecryptablePayload


@pytest.fixture(scope="module")
def cipher() -> TransferCipher:
    return TransferCipher.generate(key_size=2048)


def test_seal_then_decrypt_roundtrip(cipher):
    payload = {"iban": "FR7630006000011234567890189", "account_holder_name": "Émile Zola"}
    env = seal(cipher.public_pem, payload)
    assert json.loads(cipher.decrypt(env["encrypted_key"], env["iv"], env["ciphertext"])) == payload


def test_each_seal_is_different(cipher):
    a, b = seal(cipher.public_pem, {"x": 1}), seal(cipher.public_pem, {"x": 1})
    assert a["encrypted_key"] != b["encrypted_key"]
    assert a["ciphertext"] != b["ciphertext"]


def test_other_key_cannot_decrypt(cipher):
    env = seal(TransferCipher.generate(key_size=2048).public_pem, {"x": 1})
    with pytest.raises(UndecryptablePayload):
        cipher.decrypt(env["encrypted_key"], env["iv"], env["ciphertext"])


def test_pem_roundtrip_keeps_key_id(cipher):
    from cryptography.hazmat.primitives import serialization

    pem = cipher._private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    assert TransferCipher.from_pem(pem).key_id == cipher.key_id


def test_iban_hash_is_deterministic_and_keyed():
    iban = "FR7630006000011234567890189"
    p1, p2 = Pseudonymizer(b"a" * 32), Pseudonymizer(b"b" * 32)
    assert p1.iban_hash(iban) == p1.iban_hash(iban)
    assert p1.iban_hash(iban) != p2.iban_hash(iban)
    assert iban not in p1.iban_hash(iban)


def test_hmac_key_too_short_is_refused():
    with pytest.raises(ValueError):
        Pseudonymizer(b"short")
