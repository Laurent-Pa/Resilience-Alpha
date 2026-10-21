"""Boucle de remédiation : recovery, retries/escalade, dédoublonnage, cooldown, flapping, garde."""

from remediation_engine.bus import Bus
from remediation_engine.core.models import ESCALATED, RECOVERED, Alert, now
from remediation_engine.core.orchestrator import Orchestrator
from remediation_engine.core.policy import Policy
from remediation_engine.core.verifier import FakeVerifier
from remediation_engine.executors.fake import FakeExecutor
from remediation_engine.store import Store


def _orch(executor=None, verifier=None, **kw) -> Orchestrator:
    return Orchestrator(
        Store(), Bus(), executor or FakeExecutor(), verifier or FakeVerifier(), Policy(), **kw
    )


# src_ip routable (is_global) pour que block_ip l'accepte
def _alert(src_ip="8.8.8.8", **kw) -> Alert:
    base = {"source": "ml", "type": "anomaly", "target": "payment-api", "src_ip": src_ip}
    return Alert(**{**base, "at": now(), **kw})


async def test_alert_reaches_recovered():
    orch = _orch()
    inc = await orch.submit(_alert(), "http_flood")
    await orch.drain()
    assert orch.store.incidents[inc.id].state == RECOVERED
    assert [a for a, _ in orch.executor.calls] == ["block_ip", "recycle_service", "kill_db_conns"]


async def test_verify_fails_thrice_escalates():
    orch = _orch(verifier=FakeVerifier(ok=False))
    inc = await orch.submit(_alert(), "http_flood")
    await orch.drain()
    assert orch.store.incidents[inc.id].state == ESCALATED
    assert inc.attempt == 2  # 3 tentatives (0, 1, 2)


async def test_duplicate_alert_single_incident():
    orch = _orch(verifier=FakeVerifier(delay_s=0.2))  # garde l'incident ouvert
    a = _alert()
    i1 = await orch.submit(a, "http_flood")
    i2 = await orch.submit(a, "http_flood")
    assert i1.id == i2.id
    await orch.drain()
    assert len(orch.store.incidents) == 1


async def test_loopback_ip_rejected_without_execution():
    orch = _orch()
    inc = await orch.submit(_alert(src_ip="127.0.0.1"), "http_flood")
    await orch.drain()
    assert orch.store.incidents[inc.id].state == ESCALATED
    assert orch.executor.calls == []  # block_ip refusé en amont -> aucune action exécutée


async def test_cooldown_escalates_second_incident():
    orch = _orch()  # cooldown 120 s par défaut
    i1 = await orch.submit(_alert(), "http_flood")
    await orch.drain()
    assert orch.store.incidents[i1.id].state == RECOVERED
    i2 = await orch.submit(_alert(), "http_flood")
    await orch.drain()
    assert orch.store.incidents[i2.id].state == ESCALATED


async def test_flapping_escalates():
    orch = _orch(cooldown_s=0, flapping_max=2)  # cooldown off pour isoler le flapping
    last = None
    for _ in range(3):
        last = await orch.submit(_alert(), "http_flood")
        await orch.drain()
    assert orch.store.incidents[last.id].state == ESCALATED  # le 3e dépasse flapping_max=2


async def test_events_published_to_bus():
    orch = _orch()
    queue = orch.bus.subscribe()
    await orch.submit(_alert(), "http_flood")
    await orch.drain()
    states = []
    while not queue.empty():
        states.append(queue.get_nowait()["state"])
    assert states[0] == "TRIAGED" and states[-1] == RECOVERED
    assert any(s == "EXECUTING" for s in states)
