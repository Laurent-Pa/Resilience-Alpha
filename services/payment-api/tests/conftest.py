"""Fixtures : Postgres réel (testcontainers), JWKS local, client HTTP ASGI."""

import os
import uuid

# Ryuk échoue sous Docker Desktop Windows ; le conteneur est arrêté par le `with` ci-dessous.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

import httpx
import pytest
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer

from payment_api.bootstrap import run_migrations
from payment_api.main import create_app
from payment_api.seed import USERS, seed
from payment_api.settings import Settings
from resilience_common.crypto import seal
from resilience_common.testing import JwksServer, RsaKey, make_token

ISSUER = "https://test.local/auth/realms/resilience"


@pytest.fixture(scope="session")
def rsa_key() -> RsaKey:
    return RsaKey()


@pytest.fixture(scope="session")
def jwks(rsa_key):
    with JwksServer([rsa_key]) as server:
        yield server


@pytest.fixture(scope="session")
def pg_url():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def settings(pg_url, jwks) -> Settings:
    s = Settings(
        database_url=pg_url,
        oidc_issuer=ISSUER,
        oidc_jwks_url=jwks.url,
        iban_hmac_key="test-hmac-key-0123456789abcdef",
        # Le défaut de 2 s est un choix de production : échouer vite quand le pool est
        # saturé. `test_50_concurrent_crossed_transfers` le sature délibérément — ses 50
        # virements portent sur les deux mêmes comptes, donc ils se sérialisent sur les
        # mêmes verrous de ligne pendant que les suivants attendent une connexion. Le pool
        # étant partagé par toute la session de tests, la marge se réduit en fin de suite.
        db_pool_timeout_s=10.0,
    )
    run_migrations(s)
    return s


@pytest.fixture(scope="session")
async def app(settings):
    app = create_app(settings)
    yield app
    await app.state.rag_client.aclose()
    await app.state.engine.dispose()


@pytest.fixture
async def db(app):
    """Base remise à zéro puis seedée avant chaque test."""
    sm = app.state.sessionmaker
    async with sm() as s, s.begin():
        await s.execute(
            text("TRUNCATE payments.ledger_entries, payments.transactions, payments.accounts")
        )
    async with sm() as s:
        await seed(s, app.state.pseudonymizer)
    return sm


@pytest.fixture
async def client(app, db):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
def auth(rsa_key):
    """auth("alice") -> headers Authorization pour cet utilisateur du seed.
    Un UUID quelconque donne un client sans compte."""

    def _auth(user: str | uuid.UUID, roles: tuple[str, ...] | None = None) -> dict[str, str]:
        default_roles = {"prober": ("prober",), "operator": ("ops",)}.get(user, ("client",))
        tok = make_token(
            rsa_key,
            sub=USERS[user] if isinstance(user, str) else user,
            roles=roles or default_roles,
            issuer=ISSUER,
            audience="payment-api",
        )
        return {"Authorization": f"Bearer {tok}"}

    return _auth


@pytest.fixture
def envelope(app):
    """Construit le corps de POST /payments/transfer en chiffrant comme le front."""

    def _envelope(
        dst_iban: str, amount: str, *, bic: str | None = None, name: str = "Jean Dupont"
    ) -> dict:
        beneficiary = {"iban": dst_iban, "account_holder_name": name}
        if bic is not None:
            beneficiary["bic"] = bic
        return {
            "amount": amount,  # euros, ex. "50.05"
            **seal(app.state.transfer_cipher.public_pem, beneficiary),
        }

    return _envelope
