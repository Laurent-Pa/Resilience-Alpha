"""Orchestrateur : d'une alerte classée à RECOVERED ou ESCALATED, sans intervention humaine.

Dédoublonnage par (type, target). Traitement en tâche de fond (POST /alerts répond tout de
suite). Sérialisé par cible (un verrou par target). Cooldown et flapping -> ESCALATED. Retries
bornés. Chaque transition et chaque action sont persistées, journalisées et publiées sur le bus.
"""

import asyncio
from datetime import timedelta

import structlog
from pydantic import BaseModel

from remediation_engine import metrics
from remediation_engine.bus import Bus
from remediation_engine.core import models as m
from remediation_engine.core.actions import build_params
from remediation_engine.core.models import Alert, Incident
from remediation_engine.core.policy import Policy
from remediation_engine.core.state_machine import assert_transition
from remediation_engine.store import Store

log = structlog.get_logger()


class Orchestrator:
    def __init__(
        self,
        store: Store,
        bus: Bus,
        executor,
        verifier,
        policy: Policy,
        *,
        cooldown_s: float = 120,
        flapping_max: int = 3,
        flapping_window_s: float = 600,
        max_attempts: int = 3,
    ) -> None:
        self.store = store
        self.bus = bus
        self.executor = executor
        self.verifier = verifier
        self.policy = policy
        self.cooldown_s = cooldown_s
        self.flapping_max = flapping_max
        self.flapping_window_s = flapping_window_s
        self.max_attempts = max_attempts
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: set[asyncio.Task] = set()

    def _lock(self, target: str) -> asyncio.Lock:
        return self._locks.setdefault(target, asyncio.Lock())

    async def submit(self, alert: Alert, inc_type: str) -> Incident:
        """Crée l'incident (ou rattache à un incident ouvert) et lance son traitement.

        open_for + add sont synchrones (aucun await entre eux) : atomiques en asyncio, donc le
        dédoublonnage ne prend pas le verrou de cible (que _run garde pendant tout le traitement).
        """
        if existing := self.store.open_for(inc_type, alert.target):
            return existing  # dédoublonnage : même (type, target) non terminal
        detected = m.now()
        inc = Incident(
            type=inc_type,
            target=alert.target,
            src_ip=alert.src_ip,
            plan=self.policy.plan_for(inc_type),
            detected_at=detected,
            mttd_s=max((detected - alert.at).total_seconds(), 0.0),
        )
        self.store.add(inc)
        metrics.MTTD.observe(inc.mttd_s)
        metrics.OPEN.inc()
        task = asyncio.create_task(self._run(inc))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return inc

    async def drain(self) -> None:
        """Attend la fin de tous les traitements en cours (tests)."""
        await asyncio.gather(*list(self._tasks))

    async def _run(self, inc: Incident) -> None:
        try:
            async with self._lock(inc.target):
                await self._drive(inc)
        except Exception:  # un incident qui plante ne doit pas tuer le moteur
            log.exception("remediation.crash", incident_id=inc.id)
        finally:
            metrics.OPEN.dec()

    async def _drive(self, inc: Incident) -> None:
        window_start = m.now() - timedelta(seconds=self.flapping_window_s)
        if self._cooldown_active(inc.target) or self.store.recent_count(
            inc.target, window_start
        ) > self.flapping_max:
            return await self._escalate(inc, "cooldown_or_flapping")

        await self._transition(inc, m.TRIAGED)
        for attempt in range(self.max_attempts):
            inc.attempt = attempt
            await self._transition(inc, m.EXECUTING)
            try:
                for action in inc.plan.actions:
                    params = build_params(action, inc)  # lève si hors liste -> aucune exécution
                    res = await self.executor.run(action, params)
                    await self._record_action(inc, action, params, res)
            except Exception as exc:
                return await self._escalate(inc, f"invalid_action:{type(exc).__name__}")
            await self._transition(inc, m.VERIFYING)
            if await self.verifier.check(inc.plan.verify, m.now()):
                return await self._recover(inc)
        await self._escalate(inc, "verification_failed")

    def _cooldown_active(self, target: str) -> bool:
        last = self.store.last_terminal.get(target)
        return last is not None and (m.now() - last).total_seconds() < self.cooldown_s

    async def _transition(self, inc: Incident, to: str, detail: str = "") -> None:
        assert_transition(inc.state, to)
        frm, inc.state = inc.state, to
        await self._emit(inc, frm, action=None, params=None, result=None, detail=detail)

    async def _record_action(self, inc: Incident, action: str, params: BaseModel, res) -> None:
        result = "ok" if res.ok else "fail"
        metrics.ACTIONS.labels(action, result).inc()
        await self._emit(inc, inc.state, action, params.model_dump(mode="json"), result, res.output)

    async def _emit(self, inc, from_state, action, params, result, detail) -> None:
        event = {
            "incident_id": inc.id,
            "at": m.now().isoformat(),
            "state": inc.state,
            "type": inc.type,
            "target": inc.target,
            "action": action,
            "params": params,
            "result": result,
            "detail": detail,
        }
        self.store.record_transition({**event, "from_state": from_state})
        (log.info if result != "fail" else log.warning)("remediation.transition", **event)
        await self.bus.publish(event)

    async def _recover(self, inc: Incident) -> None:
        inc.recovered_at = m.now()
        inc.mttr_s = (inc.recovered_at - inc.detected_at).total_seconds()
        self.store.last_terminal[inc.target] = inc.recovered_at
        metrics.MTTR.observe(inc.mttr_s)
        metrics.INCIDENTS.labels(inc.type, "recovered").inc()
        await self._transition(inc, m.RECOVERED, detail=f"mttr_s={inc.mttr_s:.1f}")

    async def _escalate(self, inc: Incident, reason: str) -> None:
        self.store.last_terminal[inc.target] = m.now()
        metrics.INCIDENTS.labels(inc.type, "escalated").inc()
        await self._transition(inc, m.ESCALATED, detail=reason)
