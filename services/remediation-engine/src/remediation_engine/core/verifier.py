"""Vérification de la reprise.

Un vrai Verifier interroge le prober (`/status`) jusqu'à N sondes consécutives OK
POSTÉRIEURES au début de la vérification, dans la limite de timeout_s, puis (optionnel)
le ledger avec un jeton ops. Un FakeVerifier configurable sert aux tests et au dev local.
Une erreur réseau compte comme « pas encore OK » : elle ne doit jamais faire planter l'incident.
"""

import asyncio
import time
from datetime import datetime

import httpx
import structlog

log = structlog.get_logger()
TOKEN_MARGIN_S = 30


class FakeVerifier:
    def __init__(self, *, ok: bool = True, delay_s: float = 0.02) -> None:
        self.ok = ok
        self.delay_s = delay_s

    async def check(self, verify_cfg: dict, since: datetime) -> bool:
        await asyncio.sleep(self.delay_s)
        return self.ok


class Verifier:
    def __init__(
        self,
        client: httpx.AsyncClient,
        prober_status_url: str,
        ledger_url: str,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        poll_s: float = 2,
    ) -> None:
        self.client = client
        self.prober_status_url = prober_status_url
        self.ledger_url = ledger_url
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.poll_s = poll_s
        self._token: str | None = None
        self._token_exp = 0.0

    async def check(self, verify_cfg: dict, since: datetime) -> bool:
        need = int(verify_cfg.get("probe_ok_consecutive", 0))
        deadline = time.monotonic() + float(verify_cfg.get("timeout_s", 60))
        while need and not await self._consecutive_ok(need, since):
            if time.monotonic() >= deadline:
                return False  # timeout sans N sondes consécutives
            await asyncio.sleep(self.poll_s)
        if verify_cfg.get("ledger_check"):
            return await self._ledger_ok()
        return True

    async def _consecutive_ok(self, need: int, since: datetime) -> bool:
        try:
            r = await self.client.get(self.prober_status_url)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("verifier.prober_unreachable", error=type(exc).__name__)
            return False
        # On ne compte que les sondes postérieures au début de la vérif (sinon fausse reprise).
        posterior = [s for s in r.json() if datetime.fromisoformat(s["at"]) > since]
        return len(posterior) >= need and all(s["ok"] for s in posterior[-need:])

    async def _get_token(self) -> str:
        if self._token and time.monotonic() < self._token_exp:
            return self._token
        r = await self.client.post(
            self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._token_exp = time.monotonic() + body["expires_in"] - TOKEN_MARGIN_S
        return self._token

    async def _ledger_ok(self) -> bool:
        try:
            token = await self._get_token()
            r = await self.client.get(self.ledger_url, headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as exc:
            log.warning("verifier.ledger_unreachable", error=type(exc).__name__)
            return False
        if r.status_code == 401:
            self._token = None  # jeton révoqué/clé tournée : on en redemandera un au prochain essai
        ok = r.status_code == 200 and r.json().get("ok") is True
        log.info("verifier.ledger_check", ok=ok, status=r.status_code)
        return ok
