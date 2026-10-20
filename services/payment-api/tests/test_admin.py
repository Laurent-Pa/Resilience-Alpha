import uuid

from payment_api.domain import iban
from payment_api.seed import SEED_ACCOUNTS, account_id, seed_account, seed_iban

ADMIN_PAYMENTS = "/api/admin/payments"
TRANSFER = "/api/payments/transfer"

OPENING_TXS = sum(1 for a in SEED_ACCOUNTS if a.opening_cents > 0)


def acct(name: str) -> uuid.UUID:
    return account_id(seed_account(name).owner)


def iban_of(name: str) -> str:
    return seed_iban(name)


def key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


# --- Contrôle d'accès ---------------------------------------------------------------


async def test_admin_payments_requires_auth(client):
    r = await client.get(ADMIN_PAYMENTS)
    assert r.status_code == 401


async def test_admin_payments_rejects_non_ops_role(client, auth):
    r = await client.get(ADMIN_PAYMENTS, headers=auth("alice"))
    assert r.status_code == 403


async def test_admin_payments_allows_ops_role(client, auth):
    r = await client.get(ADMIN_PAYMENTS, headers=auth("operator"))
    assert r.status_code == 200


# --- Contenu et confidentialité de l'IBAN --------------------------------------------


async def test_admin_payments_lists_transfers_from_any_user(client, auth, envelope):
    payload = envelope(iban_of("bob"), 1_000)
    r = await client.post(TRANSFER, json=payload, headers=auth("alice") | key())
    assert r.status_code == 201
    tx_id = r.json()["id"]

    r = await client.get(ADMIN_PAYMENTS, headers=auth("operator"))
    assert r.status_code == 200
    body = r.json()
    ids = [item["id"] for item in body["items"]]
    assert tx_id in ids


async def test_admin_payments_never_exposes_full_iban(client, auth, envelope):
    dst_iban = iban_of("bob")
    payload = envelope(dst_iban, 1_000)
    r = await client.post(TRANSFER, json=payload, headers=auth("alice") | key())
    assert r.status_code == 201

    r = await client.get(ADMIN_PAYMENTS, headers=auth("operator"))
    assert r.status_code == 200
    body = r.json()

    assert dst_iban not in r.text
    for item in body["items"]:
        assert item["dst_iban_masked"] == iban.mask(dst_iban) or item["dst_iban_masked"].startswith(
            dst_iban[:2]
        )
        assert "****" in item["dst_iban_masked"]
        assert "iban" not in item  # seule la forme masquée est présente


# --- Pagination -----------------------------------------------------------------------


async def test_admin_payments_pagination(client, auth, envelope):
    for _ in range(5):
        payload = envelope(iban_of("bob"), 100)
        r = await client.post(TRANSFER, json=payload, headers=auth("alice") | key())
        assert r.status_code == 201

    page1_params = {"page": 1, "page_size": 3}
    r = await client.get(ADMIN_PAYMENTS, params=page1_params, headers=auth("operator"))
    assert r.status_code == 200
    body = r.json()
    assert body["page"] == 1
    assert body["page_size"] == 3
    assert len(body["items"]) == 3
    assert body["total"] == OPENING_TXS + 5

    page2_params = {"page": 2, "page_size": 3}
    r2 = await client.get(ADMIN_PAYMENTS, params=page2_params, headers=auth("operator"))
    assert r2.status_code == 200
    body2 = r2.json()
    page1_ids = {item["id"] for item in body["items"]}
    page2_ids = {item["id"] for item in body2["items"]}
    assert page1_ids.isdisjoint(page2_ids)
