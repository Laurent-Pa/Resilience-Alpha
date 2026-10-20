import asyncio
import base64
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text

from payment_api.domain import iban
from payment_api.domain.bic import DEFAULT_BIC
from payment_api.models import LedgerEntry, Transaction
from payment_api.seed import (
    BANK_RESERVE_ID,
    SEED_ACCOUNTS,
    account_id,
    seed,
    seed_account,
    seed_iban,
)
from resilience_common.crypto import seal

OPENING_TXS = sum(1 for a in SEED_ACCOUNTS if a.opening > 0)

TRANSFER = "/api/payments/transfer"


def acct(name: str) -> uuid.UUID:
    return account_id(seed_account(name).owner)


def iban_of(name: str) -> str:
    return seed_iban(name)


def key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


async def balance(client, auth, user: str) -> Decimal:
    r = await client.get("/api/accounts/me", headers=auth(user))
    assert r.status_code == 200
    return Decimal(r.json()["balance"])


async def ledger_check(client, auth) -> dict:
    r = await client.get("/api/admin/ledger/check", headers=auth("operator"))
    assert r.status_code == 200
    return r.json()


def code(r) -> str:
    return r.json()["detail"]["code"]


# --- Clé publique et chiffrement ---------------------------------------------------


async def test_public_key_is_served_without_auth(client):
    r = await client.get("/api/payments/public-key")
    assert r.status_code == 200
    body = r.json()
    assert body["public_key"].startswith("-----BEGIN PUBLIC KEY-----")
    assert body["algorithm"] == "RSA-OAEP-256"
    assert body["content_encryption"] == "A256GCM"
    assert len(body["key_id"]) == 16


async def test_tampered_ciphertext_is_400_and_writes_nothing(client, auth, envelope, db):
    payload = envelope(iban_of("bob"), "1.00")
    raw = bytearray(base64.b64decode(payload["ciphertext"]))
    raw[0] ^= 0x01
    payload["ciphertext"] = base64.b64encode(raw).decode()

    r = await client.post(TRANSFER, json=payload, headers=auth("alice") | key())
    assert r.status_code == 400
    assert code(r) == "decryption_failed"
    async with db() as s:
        assert await s.scalar(select(func.count()).select_from(Transaction)) == OPENING_TXS


@pytest.mark.parametrize(
    "field, value",
    [
        ("encrypted_key", "pas du base64 !"),
        ("encrypted_key", base64.b64encode(b"x" * 384).decode()),
        ("iv", base64.b64encode(b"short").decode()),
    ],
)
async def test_undecryptable_envelope_is_400(client, auth, envelope, field, value):
    payload = envelope(iban_of("bob"), "1.00") | {field: value}
    r = await client.post(TRANSFER, json=payload, headers=auth("alice") | key())
    assert r.status_code == 400
    assert code(r) == "decryption_failed"


async def test_incomplete_beneficiary_is_422_without_echo(client, auth, app):
    payload = {
        "amount": "1.00",
        **seal(app.state.transfer_cipher.public_pem, {"iban": iban_of("bob")}),  # nom absent
    }
    r = await client.post(TRANSFER, json=payload, headers=auth("alice") | key())
    assert r.status_code == 422
    assert code(r) == "invalid_payload"
    assert iban_of("bob") not in r.text


# --- Nominal -----------------------------------------------------------------------


async def test_accounts_me_returns_the_single_account(client, auth):
    assert await balance(client, auth, "alice") == Decimal("1500")
    assert await balance(client, auth, "prober") == Decimal("10000")
    bob = (await client.get("/api/accounts/me", headers=auth("bob"))).json()
    assert bob["id"] == str(acct("bob"))
    assert bob["iban_masked"] == iban.mask(iban_of("bob"))
    assert bob["iban_masked"].startswith("FR****")
    assert bob["bic"] == DEFAULT_BIC
    assert "iban" not in bob


async def test_nominal_transfer(client, auth, envelope):
    r = await client.post(
        TRANSFER,
        json=envelope(iban_of("bob"), "123.45"),
        headers=auth("alice") | key(),
    )
    assert r.status_code == 201
    tx = r.json()
    assert tx["status"] == "COMPLETED"
    assert tx["amount"] == "123.45"
    assert tx["dst_account"] == str(acct("bob"))
    assert tx["dst_iban_masked"] == iban.mask(iban_of("bob"))

    assert await balance(client, auth, "alice") == Decimal("1500") - Decimal("123.45")
    assert await balance(client, auth, "bob") == Decimal("800") + Decimal("123.45")

    # Visible par l'émetteur et le destinataire, invisible pour un tiers.
    assert (await client.get(f"/api/payments/{tx['id']}", headers=auth("alice"))).status_code == 200
    assert (await client.get(f"/api/payments/{tx['id']}", headers=auth("bob"))).status_code == 200
    assert (await client.get(f"/api/payments/{tx['id']}", headers=auth("carol"))).status_code == 404

    # Historique du destinataire : le virement reçu, puis le crédit d'ouverture du seed.
    history = (await client.get("/api/payments?limit=10", headers=auth("bob"))).json()
    assert history[0]["id"] == tx["id"]
    assert len(history) == 2

    assert (await ledger_check(client, auth))["ok"] is True


async def test_iban_with_spaces_and_lowercase_is_accepted(client, auth, envelope):
    typed = iban.format_groups(iban_of("bob")).lower()
    r = await client.post(TRANSFER, json=envelope(typed, "1.00"), headers=auth("alice") | key())
    assert r.status_code == 201
    assert r.json()["dst_account"] == str(acct("bob"))


async def test_prober_transfer_between_probe_accounts(client, auth, envelope):
    r = await client.post(
        TRANSFER,
        json=envelope(iban_of("probe_sink"), "0.01"),
        headers=auth("prober") | key(),
    )
    assert r.status_code == 201


async def test_unknown_payment_is_404(client, auth):
    r = await client.get(f"/api/payments/{uuid.uuid4()}", headers=auth("alice"))
    assert r.status_code == 404


# --- BIC ---------------------------------------------------------------------------


@pytest.mark.parametrize("given", [DEFAULT_BIC, DEFAULT_BIC[:8], "rsal frp0 xxx", ""])
async def test_matching_or_absent_bic_is_accepted(client, auth, envelope, given):
    r = await client.post(
        TRANSFER,
        json=envelope(iban_of("bob"), "1.00", bic=given),
        headers=auth("alice") | key(),
    )
    assert r.status_code == 201


@pytest.mark.parametrize(
    "given, expected", [("BNPAFRPPXXX", "bic_mismatch"), ("NOT-A-BIC", "invalid_bic")]
)
async def test_wrong_bic_is_422(client, auth, envelope, given, expected):
    r = await client.post(
        TRANSFER,
        json=envelope(iban_of("bob"), "1.00", bic=given),
        headers=auth("alice") | key(),
    )
    assert r.status_code == 422
    assert code(r) == expected


# --- Refus métier ------------------------------------------------------------------


async def test_invalid_iban_is_422(client, auth, envelope):
    good = iban_of("bob")
    bad = good[:-1] + str((int(good[-1]) + 1) % 10)  # clé fausse
    r = await client.post(TRANSFER, json=envelope(bad, "1.00"), headers=auth("alice") | key())
    assert r.status_code == 422
    assert code(r) == "invalid_iban"


async def test_insufficient_funds_is_422(client, auth, envelope):
    r = await client.post(
        TRANSFER, json=envelope(iban_of("alice"), "800.01"), headers=auth("bob") | key()
    )
    assert r.status_code == 422
    assert code(r) == "insufficient_funds"
    assert await balance(client, auth, "bob") == Decimal("800")


async def test_client_without_account_is_403_and_404(client, auth, envelope):
    stranger = auth(uuid.uuid4())  # rôle client valide, aucun compte
    r = await client.post(TRANSFER, json=envelope(iban_of("bob"), "0.01"), headers=stranger | key())
    assert r.status_code == 403
    assert code(r) == "no_account"
    assert (await client.get("/api/accounts/me", headers=stranger)).status_code == 404


async def test_debited_account_comes_from_token(client, auth, envelope):
    r = await client.post(
        TRANSFER, json=envelope(iban_of("carol"), "1.00"), headers=auth("bob") | key()
    )
    assert r.status_code == 201
    assert r.json()["src_account"] == str(acct("bob"))
    assert await balance(client, auth, "bob") == Decimal("800") - Decimal("1.00")


async def test_src_account_field_is_rejected(client, auth, envelope):
    payload = envelope(iban_of("bob"), "0.01") | {"src_account": str(acct("carol"))}
    r = await client.post(TRANSFER, json=payload, headers=auth("alice") | key())
    assert r.status_code == 422


async def test_unknown_iban_is_422(client, auth, envelope):
    unknown = iban.make_fr(55_555_555_555)
    r = await client.post(TRANSFER, json=envelope(unknown, "0.01"), headers=auth("alice") | key())
    assert r.status_code == 422
    assert code(r) == "unknown_account"


async def test_same_account_is_422(client, auth, envelope):
    r = await client.post(
        TRANSFER, json=envelope(iban_of("alice"), "0.01"), headers=auth("alice") | key()
    )
    assert r.status_code == 422
    assert code(r) == "same_account"


async def test_validation_errors_are_422(client, auth, envelope):
    for amount in ("0", "-0.05", "1000000.01", "1.001"):
        r = await client.post(
            TRANSFER,
            json=envelope(iban_of("bob"), amount),
            headers=auth("alice") | key(),
        )
        assert r.status_code == 422, amount
    # Header Idempotency-Key absent.
    r = await client.post(TRANSFER, json=envelope(iban_of("bob"), "0.01"), headers=auth("alice"))
    assert r.status_code == 422


async def test_auth_is_enforced(client, auth, envelope):
    payload = envelope(iban_of("bob"), "0.01")
    assert (await client.post(TRANSFER, json=payload, headers=key())).status_code == 401
    r = await client.post(TRANSFER, json=payload, headers=auth("operator") | key())
    assert r.status_code == 403
    assert (await client.get("/api/admin/ledger/check", headers=auth("alice"))).status_code == 403


# --- Confidentialité de l'IBAN -----------------------------------------------------


async def test_no_plaintext_iban_in_database(client, auth, envelope, db):
    await client.post(
        TRANSFER, json=envelope(iban_of("bob"), "1.00"), headers=auth("alice") | key()
    )
    async with db() as s:
        dump = " ".join(
            await s.scalars(
                text(
                    "SELECT row_to_json(a)::text FROM payments.accounts a "
                    "UNION ALL SELECT row_to_json(t)::text FROM payments.transactions t"
                )
            )
        )
    for a in SEED_ACCOUNTS:
        value = a.iban
        assert value not in dump
        assert value[4:-4] not in dump  # pas même la partie centrale
    assert iban.mask(iban_of("bob")) in dump


async def test_iban_and_holder_name_never_logged(client, auth, envelope, capsys):
    capsys.readouterr()
    name = "Zébulon Témoin"
    await client.post(
        TRANSFER,
        json=envelope(iban_of("bob"), "1.00", name=name),
        headers=auth("alice") | key(),
    )
    good = iban_of("carol")
    bad = good[:-1] + str((int(good[-1]) + 1) % 10)  # clé fausse : refusé
    await client.post(
        TRANSFER, json=envelope(bad, "1.00", name=name), headers=auth("alice") | key()
    )
    logs = capsys.readouterr().out
    assert "payment.created" in logs and "payment.rejected" in logs
    for secret in (iban_of("bob"), bad, name):
        assert secret not in logs


# --- Idempotence -------------------------------------------------------------------


async def test_replay_returns_200_and_writes_once(client, auth, envelope, db):
    headers = auth("alice") | key()
    first = await client.post(TRANSFER, json=envelope(iban_of("bob"), "5.00"), headers=headers)
    # Le front rechiffre à chaque envoi (nouvelle clé AES) : c'est toujours un rejeu.
    replay = await client.post(TRANSFER, json=envelope(iban_of("bob"), "5.00"), headers=headers)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json() == first.json()

    async with db() as s:
        n = await s.scalar(
            select(func.count()).where(LedgerEntry.tx_id == uuid.UUID(first.json()["id"]))
        )
    assert n == 2
    assert await balance(client, auth, "alice") == Decimal("1500") - Decimal("5.00")


async def test_same_key_different_body_is_409(client, auth, envelope):
    headers = auth("alice") | key()
    r1 = await client.post(TRANSFER, json=envelope(iban_of("bob"), "5.00"), headers=headers)
    r2 = await client.post(TRANSFER, json=envelope(iban_of("carol"), "5.00"), headers=headers)
    assert r1.status_code == 201
    assert r2.status_code == 409
    assert code(r2) == "idempotency_conflict"


async def test_same_key_reused_by_another_user_is_409(client, auth, envelope):
    k = key()
    r1 = await client.post(
        TRANSFER, json=envelope(iban_of("bob"), "5.00"), headers=auth("alice") | k
    )
    r2 = await client.post(TRANSFER, json=envelope(iban_of("bob"), "5.00"), headers=auth("bob") | k)
    assert r1.status_code == 201
    assert r2.status_code == 409


async def test_concurrent_requests_with_same_key_create_one_transaction(client, auth, envelope, db):
    headers = auth("alice") | key()
    payload = envelope(iban_of("bob"), "7.00")
    responses = await asyncio.gather(
        *(client.post(TRANSFER, json=payload, headers=headers) for _ in range(10))
    )
    codes = sorted(r.status_code for r in responses)
    assert codes == [200] * 9 + [201]
    assert len({r.json()["id"] for r in responses}) == 1

    async with db() as s:
        n = await s.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.idempotency_key == headers["Idempotency-Key"])
        )
    assert n == 1
    assert await balance(client, auth, "alice") == Decimal("1500") - Decimal("7.00")


# --- Concurrence et invariant ------------------------------------------------------


async def test_50_concurrent_crossed_transfers(client, auth, envelope):
    a_to_b, b_to_a = Decimal("1.00"), Decimal("0.37")

    async def send(i: int):
        if i % 2 == 0:
            return await client.post(
                TRANSFER,
                json=envelope(iban_of("bob"), str(a_to_b)),
                headers=auth("alice") | key(),
            )
        return await client.post(
            TRANSFER,
            json=envelope(iban_of("alice"), str(b_to_a)),
            headers=auth("bob") | key(),
        )

    responses = await asyncio.gather(*(send(i) for i in range(50)))
    assert [r.status_code for r in responses] == [201] * 50

    delta = 25 * a_to_b - 25 * b_to_a
    assert await balance(client, auth, "alice") == Decimal("1500") - delta
    assert await balance(client, auth, "bob") == Decimal("800") + delta
    assert (await ledger_check(client, auth))["ok"] is True


async def test_ledger_check_detects_unbalanced_entry(client, auth, envelope, db):
    r = await client.post(
        TRANSFER, json=envelope(iban_of("bob"), "1.00"), headers=auth("alice") | key()
    )
    tx_id = r.json()["id"]
    async with db() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO payments.ledger_entries (tx_id, account_id, amount) "
                "VALUES (:tx, :acct, -999999.99)"
            ),
            {"tx": tx_id, "acct": acct("carol")},
        )

    check = await ledger_check(client, auth)
    assert check["ok"] is False
    assert check["unbalanced_tx"] == [tx_id]
    assert check["incomplete_tx"] == [tx_id]
    assert check["negative_accounts"] == [str(acct("carol"))]


async def test_seed_is_idempotent(client, auth, app, db):
    async with db() as s:
        await seed(s, app.state.pseudonymizer)
        await seed(s, app.state.pseudonymizer)
    assert await balance(client, auth, "alice") == Decimal("1500")
    check = await ledger_check(client, auth)
    assert check["ok"] is True
    assert str(BANK_RESERVE_ID) not in check["negative_accounts"]


# --- Observabilité -----------------------------------------------------------------


async def test_health_and_metrics(client, auth, envelope):
    assert (await client.get("/health/live")).status_code == 200
    ready = await client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"] == {"db": "ok"}

    await client.post(
        TRANSFER, json=envelope(iban_of("bob"), "0.01"), headers=auth("alice") | key()
    )
    metrics = (await client.get("/metrics")).text
    assert 'payments_total{status="completed"}' in metrics
    assert "payment_duration_seconds_bucket" in metrics
