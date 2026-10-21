import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from payment_api.domain import iban
from payment_api.models import Transaction
from payment_api.seed import SEED_ACCOUNTS, account_id, seed_account, seed_iban

ADMIN_PAYMENTS = "/api/admin/payments"
PROBER_RATE = "/api/admin/prober/success-rate"
TRANSFER = "/api/payments/transfer"

OPENING_TXS = sum(1 for a in SEED_ACCOUNTS if a.opening > 0)


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


# --- Trafic de la sonde dans la liste ------------------------------------------------


async def transfer(client, auth, envelope, user: str, dst: str) -> str:
    r = await client.post(TRANSFER, json=envelope(iban_of(dst), "0.01"), headers=auth(user) | key())
    assert r.status_code == 201
    return r.json()["id"]


async def test_admin_payments_hides_prober_traffic_by_default(client, auth, envelope):
    user_tx = await transfer(client, auth, envelope, "alice", "bob")
    prober_tx = await transfer(client, auth, envelope, "prober", "probe_sink")

    body = (await client.get(ADMIN_PAYMENTS, headers=auth("operator"))).json()
    ids = {item["id"] for item in body["items"]}
    assert user_tx in ids
    assert prober_tx not in ids
    assert body["total"] == OPENING_TXS + 1  # le total suit le même filtre que la liste
    assert {item["initiated_by"] for item in body["items"]} == {"user"}


async def test_admin_payments_include_prober_shows_and_labels_it(client, auth, envelope):
    await transfer(client, auth, envelope, "alice", "bob")
    prober_tx = await transfer(client, auth, envelope, "prober", "probe_sink")

    r = await client.get(
        ADMIN_PAYMENTS, params={"include_prober": "true"}, headers=auth("operator")
    )
    body = r.json()
    origins = {item["id"]: item["initiated_by"] for item in body["items"]}
    assert origins[prober_tx] == "prober"
    assert body["total"] == OPENING_TXS + 2


# --- SLI de la sonde ------------------------------------------------------------------


async def test_prober_success_rate_requires_ops_role(client, auth):
    r = await client.get(PROBER_RATE, headers=auth("alice"))
    assert r.status_code == 403


async def test_prober_success_rate_is_zero_without_prober_history(client, auth):
    body = (await client.get(PROBER_RATE, headers=auth("operator"))).json()
    assert (body["interval_s"], body["window_minutes"], len(body["points"])) == (5.0, 60, 60)
    assert all(p["success_count"] == 0 and p["success_pct"] == 0 for p in body["points"])
    assert {p["expected_count"] for p in body["points"]} == {12.0}


async def test_prober_success_rate_counts_only_prober_transfers(client, auth, envelope, db):
    prober_txs = [await transfer(client, auth, envelope, "prober", "probe_sink") for _ in range(3)]
    user_tx = await transfer(client, auth, envelope, "alice", "bob")

    # Créés à l'instant, donc dans la minute en cours, que la fenêtre exclut : on les
    # recule dans une minute complète.
    minute = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=5)
    async with db() as s, s.begin():
        await s.execute(
            update(Transaction)
            .where(Transaction.id.in_([uuid.UUID(t) for t in [*prober_txs, user_tx]]))
            .values(created_at=minute + timedelta(seconds=30))
        )

    body = (await client.get(PROBER_RATE, headers=auth("operator"))).json()
    by_minute = {datetime.fromisoformat(p["minute"]): p for p in body["points"]}
    assert (by_minute[minute]["success_count"], by_minute[minute]["success_pct"]) == (3, 25.0)
    # Le virement d'alice, reculé dans la même minute, n'est pas compté.
    assert sum(p["success_count"] for p in body["points"]) == 3
