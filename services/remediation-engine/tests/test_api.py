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
    base = {
        "source": "ml",
        "type": "anomaly",
        "target": "payment-api",
        "src_ip": "203.0.113.5",
        "at": now().isoformat(),
    }
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


async def test_alertmanager_group_firing_only_and_audited():
    app = _app()
    at = now().isoformat()
    body = json.dumps({"alerts": [
        {"status": "resolved", "labels": {"alertname": "High5xx", "service": "payment-api"},
         "startsAt": at},
        {"status": "firing", "labels": {"alertname": "ServiceDown", "service": "payment-api"},
         "startsAt": at},
        {"status": "firing", "labels": {"alertname": "ProbeTokenFailures", "service": "prober"},
         "startsAt": at},
    ]}).encode()  # fmt: skip
    async with _client(app) as c:
        r = await c.post("/alerts", content=body, headers={"X-Signature": sign(SECRET, body)})
    assert r.status_code == 202
    incs = r.json()["incidents"]
    assert [i["type"] for i in incs] == ["service_down", "idp_down"]  # le resolved est ignoré
    store = app.state.store
    assert store.incidents[incs[1]["incident_id"]].target == "keycloak"  # recyclage de l'IdP
    assert [a["raw"]["labels"]["alertname"] for a in store.alerts] == [
        "ServiceDown",
        "ProbeTokenFailures",
    ]


async def test_ignored_alert_still_audited():
    app = _app()
    async with _client(app) as c:
        body = _body(target="unknown-svc")
        await c.post("/alerts", content=body, headers={"X-Signature": sign(SECRET, body)})
    assert [a["incident_id"] for a in app.state.store.alerts] == [None]


async def test_alerts_bearer_token_for_alertmanager():
    app = create_app(Settings(webhook_hmac_key="s3cr3t-webhook", alertmanager_token="am-token"))
    body = _body()
    async with _client(app) as c:
        ok = await c.post("/alerts", content=body, headers={"Authorization": "Bearer am-token"})
        bad = await c.post("/alerts", content=body, headers={"Authorization": "Bearer nope"})
    assert ok.status_code == 202 and bad.status_code == 401


async def test_alerts_bearer_refused_when_token_not_configured():
    async with _client(_app()) as c:  # pas d'alertmanager_token
        r = await c.post("/alerts", content=_body(), headers={"Authorization": "Bearer "})
        assert r.status_code == 401
