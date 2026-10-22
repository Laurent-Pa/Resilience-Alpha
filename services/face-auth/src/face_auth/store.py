"""Persistance : enrôlements (empreintes chiffrées), verrous, journal des tentatives.

`MemoryStore` pour les tests et le dev nu ; `PgStore` (schéma `biometrics`) sinon. Contrairement
au moteur de remédiation, pas d'écriture best-effort : une base en panne fait échouer la
vérification (fail-closed), on n'ouvre pas le back-office sans pouvoir compter les échecs.

shortcut: schéma créé par DDL idempotent au démarrage (pas d'Alembic), comme remediation-engine.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import asyncpg

from face_auth.lockout import LockState


@dataclass(frozen=True)
class Enrollment:
    username: str
    template: bytes  # empreinte chiffrée (crypto.TemplateCipher)
    enrolled_at: datetime
    enrolled_by: str


@dataclass(frozen=True)
class Attempt:
    username: str
    at: datetime
    outcome: str
    score: float | None


class Store(Protocol):
    async def open(self) -> None: ...
    async def close(self) -> None: ...
    async def ping(self) -> None: ...
    async def get_enrollment(self, username: str) -> Enrollment | None: ...
    async def save_enrollment(self, e: Enrollment) -> None: ...
    async def get_lock(self, username: str) -> LockState: ...
    async def set_lock(self, username: str, state: LockState) -> None: ...
    async def add_attempt(self, a: Attempt) -> None: ...


class MemoryStore:
    def __init__(self) -> None:
        self.enrollments: dict[str, Enrollment] = {}
        self.locks: dict[str, LockState] = {}
        self.attempts: list[Attempt] = []

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def ping(self) -> None:
        pass

    async def get_enrollment(self, username: str) -> Enrollment | None:
        return self.enrollments.get(username)

    async def save_enrollment(self, e: Enrollment) -> None:
        self.enrollments[e.username] = e

    async def get_lock(self, username: str) -> LockState:
        return self.locks.get(username, LockState())

    async def set_lock(self, username: str, state: LockState) -> None:
        self.locks[username] = state

    async def add_attempt(self, a: Attempt) -> None:
        self.attempts.append(a)


DDL = """
CREATE SCHEMA IF NOT EXISTS biometrics;
CREATE TABLE IF NOT EXISTS biometrics.enrollments (
    username text PRIMARY KEY, template bytea NOT NULL,
    enrolled_at timestamptz NOT NULL, enrolled_by text NOT NULL
);
CREATE TABLE IF NOT EXISTS biometrics.lockouts (
    username text PRIMARY KEY, failures int NOT NULL, locked_until timestamptz
);
CREATE TABLE IF NOT EXISTS biometrics.attempts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, username text NOT NULL,
    at timestamptz NOT NULL, outcome text NOT NULL, score double precision
);
CREATE INDEX IF NOT EXISTS attempts_at ON biometrics.attempts(at DESC);
"""


class PgStore:
    def __init__(self, connect: dict) -> None:
        self.connect = connect  # kwargs asyncpg.create_pool
        self._pool: asyncpg.Pool | None = None

    @property
    def pool(self) -> asyncpg.Pool:
        assert self._pool is not None, "PgStore.open() non appelé"
        return self._pool

    async def open(self) -> None:
        self._pool = await asyncpg.create_pool(min_size=1, max_size=3, **self.connect)
        async with self._pool.acquire() as c:
            await c.execute(DDL)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def ping(self) -> None:
        await self.pool.fetchval("SELECT 1")

    @staticmethod
    def _enrollment(r: asyncpg.Record) -> Enrollment:
        return Enrollment(r["username"], bytes(r["template"]), r["enrolled_at"], r["enrolled_by"])

    async def get_enrollment(self, username: str) -> Enrollment | None:
        r = await self.pool.fetchrow(
            "SELECT * FROM biometrics.enrollments WHERE username = $1", username
        )
        return self._enrollment(r) if r else None

    async def save_enrollment(self, e: Enrollment) -> None:
        await self.pool.execute(
            "INSERT INTO biometrics.enrollments (username, template, enrolled_at, enrolled_by)"
            " VALUES ($1, $2, $3, $4) ON CONFLICT (username) DO UPDATE"
            " SET template = $2, enrolled_at = $3, enrolled_by = $4",
            e.username,
            e.template,
            e.enrolled_at,
            e.enrolled_by,
        )

    async def get_lock(self, username: str) -> LockState:
        r = await self.pool.fetchrow(
            "SELECT failures, locked_until FROM biometrics.lockouts WHERE username = $1", username
        )
        return LockState(r["failures"], r["locked_until"]) if r else LockState()

    async def set_lock(self, username: str, state: LockState) -> None:
        await self.pool.execute(
            "INSERT INTO biometrics.lockouts (username, failures, locked_until) VALUES ($1, $2, $3)"
            " ON CONFLICT (username) DO UPDATE SET failures = $2, locked_until = $3",
            username,
            state.failures,
            state.locked_until,
        )

    async def add_attempt(self, a: Attempt) -> None:
        await self.pool.execute(
            "INSERT INTO biometrics.attempts (username, at, outcome, score)"
            " VALUES ($1, $2, $3, $4)",
            a.username,
            a.at,
            a.outcome,
            a.score,
        )


def now() -> datetime:
    return datetime.now(UTC)
