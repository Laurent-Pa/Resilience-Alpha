"""Étape 7 : verifier réel (jeton ops + ledger), AnsibleExecutor, persistance et reprise."""

import os
import sys
import types
from datetime import timedelta

os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

import httpx
import pytest
from testcontainers.community.postgres import PostgresContainer

from remediation_engine.bus import Bus
from remediation_engine.core.actions import BlockIpParams
from remediation_engine.core.models import RECOVERED, VERIFYING, Incident, now
from remediation_engine.core.orchestrator import Orchestrator
from remediation_engine.core.policy import Policy
from remediation_engine.core.verifier import FakeVerifier, Verifier
from remediation_engine.executors.ansible import AnsibleExecutor
from remediation_engine.executors.fake import FakeExecutor
from remediation_engine.store import Store

VERIFY = {"probe_ok_consecutive": 2, "ledger_check": True, "timeout_s": 1}


def _verifier(handler) -> Verifier:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return Verifier(
        client, "http://prober/status", "http://waf/ledger",
        token_url="http://kc/token", client_id="remediation-engine", client_secret="x",
        poll_s=0.01,
    )  # fmt: skip


def _routes(probes, ledger_ok=True, seen=None):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "kc":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 300})
        if req.url.host == "waf":
            if seen is not None:
                seen.append(req.headers.get("authorization"))
            return httpx.Response(200, json={"ok": ledger_ok})
        return httpx.Response(200, json=probes)

    return handler


async def test_verifier_probes_then_ledger_with_ops_token():
    since = now()
    probes = [{"at": (since + timedelta(seconds=i)).isoformat(), "ok": True} for i in (1, 2)]
    seen: list = []
    assert await _verifier(_routes(probes, seen=seen)).check(VERIFY, since)
    assert seen == ["Bearer tok"]


async def test_verifier_ledger_ko_and_old_probes_fail():
    since = now()
    fresh = [{"at": (since + timedelta(seconds=i)).isoformat(), "ok": True} for i in (1, 2)]
    assert not await _verifier(_routes(fresh, ledger_ok=False)).check(VERIFY, since)
    stale = [{"at": (since - timedelta(seconds=i)).isoformat(), "ok": True} for i in (1, 2)]
    assert not await _verifier(_routes(stale)).check(VERIFY, since)  # sondes d'avant : refus


async def test_verifier_prober_down_is_false_not_crash():
    def down(req):
        raise httpx.ConnectError("down")

    assert not await _verifier(down).check(VERIFY, now())


@pytest.fixture
def fake_runner(monkeypatch):
    calls = []

    def run(**kw):
        calls.append(kw)
        status = "timeout" if kw["extravars"].get("ip") == "10.0.0.9" else "successful"
        return types.SimpleNamespace(
            status=status,
            rc=0 if status == "successful" else 254,
            stdout=types.SimpleNamespace(read=lambda: "boom"),
        )

    monkeypatch.setitem(sys.modules, "ansible_runner", types.SimpleNamespace(run=run))
    return calls


async def test_ansible_executor_success_and_timeout(fake_runner, tmp_path):
    ex = AnsibleExecutor(str(tmp_path), timeout_s=5)
    ok = await ex.run("block_ip", BlockIpParams(ip="8.8.8.8"))
    assert ok.ok and fake_runner[0]["playbook"] == "block_ip.yml"
    assert fake_runner[0]["extravars"] == {"ip": "8.8.8.8"} and fake_runner[0]["timeout"] == 5
    ko = await ex.run("block_ip", BlockIpParams(ip="10.0.0.9"))
    assert not ko.ok and "timeout" in ko.output


def test_missing_playbooks(tmp_path):
    (tmp_path / "block_ip.yml").write_text("- hosts: all\n")
    ex = AnsibleExecutor(str(tmp_path))
    assert ex.missing_playbooks(["block_ip", "recycle_service"]) == ["recycle_service"]


@pytest.fixture(scope="module")
def pg_dsn():
    with PostgresContainer("postgres:16-alpine", driver=None) as pg:
        yield pg.get_connection_url()


async def test_restart_resumes_verifying_incident(pg_dsn):
    s1 = Store({"dsn": pg_dsn})
    await s1.open()
    inc = Incident(type="http_flood", target="payment-api", src_ip="8.8.8.8",
                   plan=Policy().plan_for("http_flood"), detected_at=now(), mttd_s=1.0,
                   state=VERIFYING)  # fmt: skip
    s1.add(inc)
    await s1.save(inc)
    await s1.close()  # « crash » du moteur en pleine vérification

    s2 = Store({"dsn": pg_dsn})
    resumable = await s2.open()
    assert [i.id for i in resumable] == [inc.id]
    ex = FakeExecutor()
    orch = Orchestrator(s2, Bus(), ex, FakeVerifier(), Policy())
    orch.resume(resumable[0])
    await orch.drain()
    assert s2.incidents[inc.id].state == RECOVERED
    assert ex.calls == []  # reprise en VERIFYING : aucune action rejouée
    await s2.close()

    s3 = Store({"dsn": pg_dsn})
    assert await s3.open() == []
    assert s3.incidents[inc.id].state == RECOVERED and s3.incidents[inc.id].mttr_s is not None
    assert [t["state"] for t in s3.transitions][-1] == RECOVERED
    assert "payment-api" in s3.last_terminal  # cooldown survit au redémarrage
    await s3.record_alert(inc.id, {"source": "ml", "type": "anomaly"})
    await s3.record_alert(None, {"source": "ml", "type": "ignored"})
    rows = await s3._pool.fetch("SELECT incident_id, raw FROM remediation.alerts ORDER BY id")
    assert [r["incident_id"] for r in rows] == [inc.id, None]
    await s3.close()


async def test_store_falls_back_to_memory_when_db_down():
    s = Store({"dsn": "postgresql://u:p@127.0.0.1:1/db"})
    assert await s.open() == []
    inc = Incident(type="t", target="x", src_ip=None, plan=Policy().plan_for("http_flood"),
                   detected_at=now(), mttd_s=0)  # fmt: skip
    s.add(inc)
    await s.save(inc)  # no-op, pas d'exception
