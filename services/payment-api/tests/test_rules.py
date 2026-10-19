"""Règles pures, sans base de données."""

import uuid

import pytest

from payment_api.domain import bic, iban, rules
from payment_api.domain.rules import TransferRequest

OWNER = uuid.uuid4()
A, B = sorted([uuid.uuid4(), uuid.uuid4()])
IBAN_B = iban.make_fr(42)
KEY = b"k" * 32


def test_hash_is_stable_keyed_and_sensitive_to_every_field():
    req = TransferRequest(IBAN_B, None, 100)
    h = rules.hash_request(KEY, OWNER, req)
    assert h == rules.hash_request(KEY, OWNER, TransferRequest(IBAN_B, None, 100))
    assert h != rules.hash_request(b"x" * 32, OWNER, req)
    assert h != rules.hash_request(KEY, OWNER, TransferRequest(IBAN_B, None, 101))
    assert h != rules.hash_request(KEY, OWNER, TransferRequest(iban.make_fr(43), None, 100))
    assert h != rules.hash_request(KEY, OWNER, TransferRequest(IBAN_B, bic.DEFAULT_BIC, 100))
    assert h != rules.hash_request(KEY, uuid.uuid4(), req)


def test_invalid_iban_or_bic_is_rejected():
    rules.validate_transfer(TransferRequest(IBAN_B, None, 1))
    rules.validate_transfer(TransferRequest(IBAN_B, bic.DEFAULT_BIC, 1))
    with pytest.raises(rules.InvalidIban):
        rules.validate_transfer(TransferRequest("FR0012345", None, 1))
    with pytest.raises(rules.InvalidBic):
        rules.validate_transfer(TransferRequest(IBAN_B, "ABC", 1))


def test_bic_check():
    rules.check_bic(bic.DEFAULT_BIC, None)
    rules.check_bic(bic.DEFAULT_BIC, "RSALFRP0")
    with pytest.raises(rules.BicMismatch):
        rules.check_bic(bic.DEFAULT_BIC, "BNPAFRPPXXX")


@pytest.mark.parametrize(
    "a, b, same",
    [
        ("RSALFRP0XXX", "RSALFRP0", True),
        ("RSALFRP0XXX", "RSALFRP0123", True),
        ("RSALFRP0123", "RSALFRP0456", False),
        ("RSALFRP0XXX", "BNPAFRPPXXX", False),
    ],
)
def test_bic_same_institution(a, b, same):
    assert bic.same_institution(a, b) is same


def test_default_bic_is_valid_test_bic():
    assert bic.is_valid(bic.DEFAULT_BIC)
    assert bic.DEFAULT_BIC[7] == "0"  # BIC de test SWIFT : aucun établissement réel
    assert not bic.is_valid("RSAL")


def test_iban_mask_keeps_only_country_and_last_four():
    assert iban.mask("FR7699999000010012345678995") == "FR****8995"


def test_same_account_is_rejected():
    rules.check_distinct(A, B)
    with pytest.raises(rules.SameAccount):
        rules.check_distinct(A, A)


def test_funds():
    rules.check_funds(100, 100)
    with pytest.raises(rules.InsufficientFunds):
        rules.check_funds(99, 100)


def test_replay_conflict():
    rules.check_replay("h", "h")
    with pytest.raises(rules.IdempotencyConflict):
        rules.check_replay("h", "other")


def test_lock_order_is_independent_of_direction():
    assert rules.lock_order(B, A) == rules.lock_order(A, B) == [A, B]


# --- IBAN --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "FR1420041010050500013M02606",  # exemples publics ISO / ECBS
        "FR7630006000011234567890189",
        "GB82WEST12345698765432",
        "DE89370400440532013000",
    ],
)
def test_known_valid_ibans(value):
    assert iban.is_valid(value)


@pytest.mark.parametrize(
    "value",
    [
        "FR7630006000011234567890188",  # clé fausse
        "FR76",  # trop court
        "7630006000011234567890189FR",  # pays mal placé
        "FR76 3000 6000 0112 3456 7890 189",  # non normalisé
        "",
    ],
)
def test_invalid_ibans(value):
    assert not iban.is_valid(value)


def test_normalize():
    assert iban.normalize(" fr76 3000-6000 0112 ") == "FR76300060000112"


def test_generated_fr_ibans_are_valid_and_fake():
    for n in (0, 1, 123_456_789, 10**11 - 1, uuid.uuid4().int):
        value = iban.make_fr(n)
        assert iban.is_valid(value)
        assert len(value) == 27
        assert value[4:9] == iban.FAKE_BANK_CODE


def test_generated_rib_key_matches_known_example():
    # FR76 30006 00001 12345678901 89 : clé RIB 89
    assert iban.rib_key("30006", "00001", "12345678901") == "89"
