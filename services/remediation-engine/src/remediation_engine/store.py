"""Stockage des incidents et transitions, avec fenêtre récente pour cooldown/flapping.

La mémoire reste la vue de travail (lectures synchrones, API inchangée). Si une connexion
Postgres est fournie, chaque écriture y est répercutée (schéma `remediation`) et `open()`
recharge tout au démarrage : le moteur survit à son propre redémarrage. Sans connexion :
mémoire seule (tests, dev nu).

shortcut: schéma créé par DDL idempotent au démarrage (pas d'Alembic) ; passer à des
migrations si le schéma doit évoluer sur une base vivante.
"""

import json
from collections import deque
from datetime import datetime
from ipaddress import IPv4Address

import asyncpg
import structlog

from remediation_engine.core.models import TERMINAL, Incident, Plan

log = structlog.get_logger()

DDL = """
CREATE SCHEMA IF NOT EXISTS remediation;
CREATE TABLE IF NOT EXISTS remediation.incidents (
    id text PRIMARY KEY, type text NOT NULL, target text NOT NULL, state text NOT NULL,
    src_ip text, detected_at timestamptz NOT NULL, recovered_at timestamptz,
    mttd_s double precision NOT NULL, mttr_s double precision,
    attempt int NOT NULL, plan jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS remediation.transitions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    incident_id text NOT NULL REFERENCES remediation.incidents(id),
    at timestamptz NOT NULL, from_state text, to_state text NOT NULL,
    action text, params jsonb, result text, detail text
);
CREATE TABLE IF NOT EXISTS remediation.alerts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    incident_id text,  -- pas de FK : l'incident est écrit en tâche de fond, parfois après
    raw jsonb NOT NULL, received_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS transitions_incident ON remediation.transitions(incident_id, id);
"""

UPSERT = """
INSERT INTO remediation.incidents
    (id, type, target, state, src_ip, detected_at, recovered_at, mttd_s, mttr_s, attempt, plan)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)
ON CONFLICT (id) DO UPDATE SET state = $4, recovered_at = $7, mttr_s = $9, attempt = $10
"""


class Store:
    def __init__(self, connect: dict | None = None) -> None:
        self.connect = connect  # kwargs asyncpg.create_pool ; None = mémoire seule
        self._pool: asyncpg.Pool | None = None
        self.incidents: dict[str, Incident] = {}
        self.transitions: list[dict] = []
        self.alerts: deque[dict] = deque(maxlen=500)  # audit récent ; l'historique est en base
        self.last_terminal: dict[str, datetime] = {}  # target -> fin du dernier incident (cooldown)
        self._recent: deque[tuple[str, datetime]] = deque(maxlen=500)  # (target, detected_at)

    async def open(self) -> list[Incident]:
        """Crée le schéma, recharge l'historique, renvoie les incidents à reprendre."""
        if self.connect is None:
            return []
        try:
            self._pool = await asyncpg.create_pool(min_size=1, max_size=3, **self.connect)
            async with self._pool.acquire() as c:
                await c.execute(DDL)
                incs = await c.fetch("SELECT * FROM remediation.incidents ORDER BY detected_at")
                trs = await c.fetch("SELECT * FROM remediation.transitions ORDER BY id")
        except (asyncpg.PostgresError, OSError) as exc:
            # Mieux vaut remédier sans journal que ne pas démarrer : mode mémoire.
            log.error("store.unavailable", error=type(exc).__name__)
            self._pool = None
            return []
        for r in incs:
            plan = json.loads(r["plan"])
            self.add(
                Incident(
                    id=r["id"],
                    type=r["type"],
                    target=r["target"],
                    state=r["state"],
                    src_ip=IPv4Address(r["src_ip"]) if r["src_ip"] else None,
                    plan=Plan(plan["actions"], plan["verify"]),
                    detected_at=r["detected_at"],
                    recovered_at=r["recovered_at"],
                    mttd_s=r["mttd_s"],
                    mttr_s=r["mttr_s"],
                    attempt=r["attempt"],
                )
            )
        for r in trs:
            inc = self.incidents[r["incident_id"]]
            self.transitions.append(
                {
                    "incident_id": inc.id,
                    "at": r["at"].isoformat(),
                    "state": r["to_state"],
                    "type": inc.type,
                    "target": inc.target,
                    "action": r["action"],
                    "params": json.loads(r["params"]) if r["params"] else None,
                    "result": r["result"],
                    "detail": r["detail"],
                    "from_state": r["from_state"],
                }
            )
            if r["to_state"] in TERMINAL:
                self.last_terminal[inc.target] = r["at"]
        return [i for i in self.incidents.values() if i.state not in TERMINAL]

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    def add(self, inc: Incident) -> None:
        self.incidents[inc.id] = inc
        self._recent.append((inc.target, inc.detected_at))

    async def save(self, inc: Incident) -> None:
        if self._pool is None:
            return
        plan = json.dumps({"actions": inc.plan.actions, "verify": inc.plan.verify})
        await self._execute(
            UPSERT,
            inc.id,
            inc.type,
            inc.target,
            inc.state,
            str(inc.src_ip) if inc.src_ip else None,
            inc.detected_at,
            inc.recovered_at,
            inc.mttd_s,
            inc.mttr_s,
            inc.attempt,
            plan,
        )

    def open_for(self, type_: str, target: str) -> Incident | None:
        for inc in self.incidents.values():
            if inc.type == type_ and inc.target == target and inc.state not in TERMINAL:
                return inc
        return None

    async def record_transition(self, row: dict) -> None:
        self.transitions.append(row)
        if self._pool is None:
            return
        await self._execute(
            "INSERT INTO remediation.transitions (incident_id, at, from_state, to_state, action,"
            " params, result, detail) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)",
            row["incident_id"],
            datetime.fromisoformat(row["at"]),
            row["from_state"],
            row["state"],
            row["action"],
            json.dumps(row["params"]) if row["params"] is not None else None,
            row["result"],
            row["detail"],
        )

    async def _execute(self, sql: str, *args) -> None:
        """Écriture best-effort : la mémoire fait foi, un journal en panne ne bloque pas la
        remédiation. Un retry couvre la connexion tuée par kill_db_conns (même rôle Postgres)."""
        assert self._pool is not None
        for attempt in (1, 2):
            try:
                await self._pool.execute(sql, *args)
                return
            except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError) as exc:
                if attempt == 2:
                    log.error("store.write_failed", error=type(exc).__name__)

    async def record_alert(self, incident_id: str | None, raw: dict) -> None:
        """Audit : alerte brute reçue (incident_id None = ignorée). Écrite, jamais relue."""
        self.alerts.append({"incident_id": incident_id, "raw": raw})
        if self._pool is not None:
            await self._execute(
                "INSERT INTO remediation.alerts (incident_id, raw) VALUES ($1, $2::jsonb)",
                incident_id,
                json.dumps(raw),
            )

    def recent_count(self, target: str, since: datetime) -> int:
        return sum(1 for tg, at in self._recent if tg == target and at >= since)
