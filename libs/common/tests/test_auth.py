import uuid

import httpx
import pytest
from fastapi import Depends, FastAPI

from resilience_common.auth import Claims, TokenVerifier, require_role
from resilience_common.testing import JwksServer, RsaKey, make_token

ISSUER = "https://test.local/auth/realms/resilience"
AUDIENCE = "payment-api"
USER = uuid.UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture(scope="module")
def key() -> RsaKey:
    return RsaKey()


@pytest.fixture(scope="module")
def jwks(key: RsaKey):
    with JwksServer([key]) as server:
        yield server


@pytest.fixture
async def client(jwks: JwksServer):
    app = FastAPI()
    app.state.token_verifier = TokenVerifier(ISSUER, jwks.url, AUDIENCE)

    @app.get("/me")
    async def me(claims: Claims = Depends(require_role("client"))) -> dict:
        return {"sub": str(claims.sub), "roles": sorted(claims.roles)}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def token(key: RsaKey, **overrides) -> str:
    params = {"sub": USER, "roles": ["client"], "issuer": ISSUER, "audience": AUDIENCE}
    params.update(overrides)
    return make_token(key, **params)


def bearer(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


async def test_valid_token_gives_claims(client, key):
    r = await client.get("/me", headers=bearer(token(key)))
    assert r.status_code == 200
    assert r.json() == {"sub": str(USER), "roles": ["client"]}


async def test_audience_list_is_accepted(client, key):
    r = await client.get("/me", headers=bearer(token(key, audience=["account", AUDIENCE])))
    assert r.status_code == 200


@pytest.mark.parametrize(
    "overrides",
    [
        {"issuer": "http://keycloak:8080/auth/realms/resilience"},
        {"audience": "other-api"},
        {"expires_in": -120},
        {"sub": "not-a-uuid"},
    ],
    ids=["bad_issuer", "bad_audience", "expired", "bad_sub"],
)
async def test_invalid_token_is_401(client, key, overrides):
    r = await client.get("/me", headers=bearer(token(key, **overrides)))
    assert r.status_code == 401


async def test_token_signed_by_unknown_key_is_401(client):
    r = await client.get("/me", headers=bearer(token(RsaKey())))
    assert r.status_code == 401


async def test_missing_token_is_401(client):
    r = await client.get("/me")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


async def test_missing_role_is_403(client, key):
    r = await client.get("/me", headers=bearer(token(key, roles=["ops"])))
    assert r.status_code == 403


async def test_jwks_unreachable_without_cache_is_503(key):
    app = FastAPI()
    app.state.token_verifier = TokenVerifier(ISSUER, "http://127.0.0.1:9/certs", AUDIENCE)

    @app.get("/me")
    async def me(claims: Claims = Depends(require_role("client"))) -> dict:
        return {}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.get("/me", headers=bearer(token(key)))
    assert r.status_code == 503
