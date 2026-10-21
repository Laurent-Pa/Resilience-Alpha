"""API : signature HMAC de /alerts, alerte ignorée, et garde d'auth sur /incidents."""

import json

import httpx

from remediation_engine.core.models import now
from remediation_engine.main import create_app
from remediation_engine.settings import Settings
from resilience_common.hmac import sign

SECRET = b"s3cr3t-webhook"


def _app():
    return create_app(Settings(webhook_hmac_key="s3cr3t-webhook"))


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _body(**kw) -> bytes:
    base = {"source": "ml", "type": "anomaly", "target": "payment-api",
            "src_ip": "203.0.113.5", "at": now().isoformat()}
    return json.dumps({**base, **kw}).encode()


async def test_alerts_rejects_bad_signature():
    async with _client(_app()) as c:
        body = _body()
        r = await c.post("/alerts", content=body, headers={"X-Signature": "sha256=dead"})
        assert r.status_code == 401


async def test_alerts_accepts_signed_and_classifies():
    async with _client(_app()) as c:
        body = _body()
        r = await c.post("/alerts", content=body, headers={"X-Signature": sign(SECRET, body)})
        assert r.status_code == 202
        assert r.json()["type"] == "http_flood"


async def test_unknown_alert_ignored():
    async with _client(_app()) as c:
        body = _body(target="unknown-svc")
        r = await c.post("/alerts", content=body, headers={"X-Signature": sign(SECRET, body)})
        assert r.status_code == 202
        assert r.json()["status"] == "ignored"


async def test_incidents_requires_token():
    async with _client(_app()) as c:
        assert (await c.get("/incidents")).status_code == 401
