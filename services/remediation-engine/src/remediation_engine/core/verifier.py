"""Vérification de la reprise.

Un vrai Verifier interroge le prober (`/status`) jusqu'à N sondes consécutives OK
POSTÉRIEURES au début de la vérification, dans la limite de timeout_s, puis (optionnel)
le ledger. Un FakeVerifier configurable sert aux tests et à la démo locale sans prober.
"""

import asyncio
import time
from datetime import datetime

import httpx


class FakeVerifier:
    def __init__(self, *, ok: bool = True, delay_s: float = 0.02) -> None:
        self.ok = ok
        self.delay_s = delay_s

    async def check(self, verify_cfg: dict, since: datetime) -> bool:
        await asyncio.sleep(self.delay_s)
        return self.ok


class Verifier:
    """shortcut: le ledger_check exige un jeton ops (client `remediation-engine`) non câblé ici ;
    brancher le token provider à l'étape 7. Les sondes, elles, suffisent au FakeExecutor local."""

    def __init__(self, client: httpx.AsyncClient, prober_status_url: str, ledger_url: str) -> None:
        self.client = client
        self.prober_status_url = prober_status_url
        self.ledger_url = ledger_url

    async def check(self, verify_cfg: dict, since: datetime) -> bool:
        need = int(verify_cfg.get("probe_ok_consecutive", 0))
        timeout_s = float(verify_cfg.get("timeout_s", 60))
        deadline = time.monotonic() + timeout_s
        while need and time.monotonic() < deadline:
            if await self._consecutive_ok(need, since):
                break
            await asyncio.sleep(2)
        else:
            if need:
                return False  # timeout sans N sondes consécutives
        if verify_cfg.get("ledger_check"):
            return await self._ledger_ok()
        return True

    async def _consecutive_ok(self, need: int, since: datetime) -> bool:
        r = await self.client.get(self.prober_status_url)
        r.raise_for_status()
        # On ne compte que les sondes postérieures au début de la vérif (sinon fausse reprise).
        posterior = [s for s in r.json() if datetime.fromisoformat(s["at"]) > since]
        return len(posterior) >= need and all(s["ok"] for s in posterior[-need:])

    async def _ledger_ok(self) -> bool:
        raise NotImplementedError("ledger_check: jeton ops à câbler à l'étape 7")
