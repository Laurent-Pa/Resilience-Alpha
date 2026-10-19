"""Sonde contre un faux Keycloak + faux WAF (httpx.MockTransport)."""

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from prober.probe import Prober
from prober.settings import Settings


def _pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )


PEM = _pem()


class FakeBackend:
    """Compte les appels ; `transfer_responses` est consommée dans l'ordre (la dernière reste)."""

    def __init__(self, token_status: int = 200, transfer_responses: list | None = None) -> None:
        self.token_status = token_status
        self.transfer_responses = transfer_responses or [(201, {"id": "x"})]
        self.calls: dict[str, int] = {"token": 0, "key": 0, "transfer": 0}
        self.idempotency_keys: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            self.calls["token"] += 1
            return httpx.Response(
                self.token_status, json={"access_token": "tok", "expires_in": 300}
            )
        if path == "/api/payments/public-key":
            self.calls["key"] += 1
            return httpx.Response(200, json={"public_key": PEM})
        if path == "/api/payments/transfer":
            self.calls["transfer"] += 1
            self.idempotency_keys.append(request.headers["Idempotency-Key"])
            assert request.headers["Authorization"] == "Bearer tok"
            status, body = self.transfer_responses[
                min(self.calls["transfer"] - 1, len(self.transfer_responses) - 1)
            ]
            return httpx.Response(status, json=body)
        return httpx.Response(404)


@pytest.fixture
async def make_prober():
    clients = []

    def _make(backend: FakeBackend) -> Prober:
        client = httpx.AsyncClient(transport=httpx.MockTransport(backend))
        clients.append(client)
        settings = Settings(target_url="https://waf.test", kc_token_url="http://kc.test/token")
        return Prober(settings, client)

    yield _make
    for c in clients:
        await c.aclose()


async def test_nominal_caches_token_and_key(make_prober):
    backend = FakeBackend()
    prober = make_prober(backend)

    r1, r2 = await prober.probe_once(), await prober.probe_once()

    assert r1["ok"] and r2["ok"] and r1["stage"] == "payment"
    assert backend.calls == {"token": 1, "key": 1, "transfer": 2}
    assert len(set(backend.idempotency_keys)) == 2  # une clé neuve par sonde
    assert list(prober.results) == [r1, r2]


async def test_token_failure(make_prober):
    prober = make_prober(FakeBackend(token_status=503))
    r = await prober.probe_once()
    assert (r["ok"], r["stage"]) == (False, "token")


async def test_payment_failure(make_prober):
    prober = make_prober(FakeBackend(transfer_responses=[(503, {})]))
    r = await prober.probe_once()
    assert (r["ok"], r["stage"]) == (False, "payment")


async def test_decryption_failed_reloads_key_and_retries_with_same_idempotency_key(make_prober):
    backend = FakeBackend(
        transfer_responses=[(400, {"detail": {"code": "decryption_failed"}}), (201, {"id": "x"})]
    )
    prober = make_prober(backend)

    r = await prober.probe_once()

    assert r["ok"]
    assert backend.calls == {"token": 1, "key": 2, "transfer": 2}
    assert backend.idempotency_keys[0] == backend.idempotency_keys[1]


async def test_401_drops_cached_token(make_prober):
    backend = FakeBackend(transfer_responses=[(401, {}), (201, {"id": "x"})])
    prober = make_prober(backend)

    assert not (await prober.probe_once())["ok"]
    assert (await prober.probe_once())["ok"]
    assert backend.calls["token"] == 2
