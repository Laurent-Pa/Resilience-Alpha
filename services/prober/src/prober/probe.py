"""Une sonde = jeton client_credentials → clé publique → virement de 1 centime via le WAF.

Succès si et seulement si le virement répond 201. `stage` indique l'étape atteinte
(celle qui a échoué en cas d'échec) : token, key ou payment.
"""

import asyncio
import time
import uuid
from collections import deque
from datetime import UTC, datetime

import httpx
import structlog
from prometheus_client import Counter, Gauge, Histogram
from structlog.contextvars import bind_contextvars, clear_contextvars

from prober.settings import Settings
from resilience_common.crypto import seal
from resilience_common.logging import propagation_headers

log = structlog.get_logger()

STAGES = ("token", "key", "payment")
PROBE_SUCCESS = Gauge("probe_success", "1 si la dernière sonde a réussi")
PROBE_LATENCY = Histogram("probe_latency_seconds", "Durée d'une sonde complète")
PROBE_FAILURES = Counter("probe_failures_total", "Sondes en échec", ["stage"])
for _stage in STAGES:
    PROBE_FAILURES.labels(_stage)  # séries à 0 dès le démarrage, pour rate() côté Prometheus

TOKEN_MARGIN_S = 30


class Prober:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client
        self.results: deque[dict] = deque(maxlen=60)
        self._token: str | None = None
        self._token_exp = 0.0
        self._public_key: str | None = None

    async def _get_token(self) -> str:
        if self._token and time.monotonic() < self._token_exp:
            return self._token
        s = self.settings
        secret = s.prober_client_secret.get_secret_value().strip() if s.prober_client_secret else ""
        r = await self.client.post(
            s.kc_token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": s.client_id,
                "client_secret": secret,
            },
        )
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._token_exp = time.monotonic() + body["expires_in"] - TOKEN_MARGIN_S
        return self._token

    async def _get_public_key(self, refresh: bool = False) -> str:
        if refresh or self._public_key is None:
            r = await self.client.get(
                f"{self.settings.target_url}/api/payments/public-key", headers=propagation_headers()
            )
            r.raise_for_status()
            self._public_key = r.json()["public_key"]
        return self._public_key

    async def _transfer(self, token: str, pem: str, idempotency_key: str) -> httpx.Response:
        beneficiary = {
            "iban": self.settings.probe_dst_iban,
            "account_holder_name": self.settings.probe_dst_name,
        }
        return await self.client.post(
            f"{self.settings.target_url}/api/payments/transfer",
            json={"amount_cents": 1, **seal(pem, beneficiary)},
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": idempotency_key,
                **propagation_headers(),
            },
        )

    async def probe_once(self) -> dict:
        clear_contextvars()
        bind_contextvars(trace_id=uuid.uuid4().hex)
        start = time.perf_counter()
        stage, status, error = "token", None, None
        try:
            token = await self._get_token()
            stage = "key"
            pem = await self._get_public_key()
            stage = "payment"
            idempotency_key = str(uuid.uuid4())
            r = await self._transfer(token, pem, idempotency_key)
            if _is_decryption_failure(r):
                # Clé tournée côté payment-api : on recharge et on rejoue une fois, même clé.
                stage = "key"
                pem = await self._get_public_key(refresh=True)
                stage = "payment"
                r = await self._transfer(token, pem, idempotency_key)
            if r.status_code == 401:
                self._token = None
            status = r.status_code
        except Exception as exc:  # la sonde ne doit jamais tuer la boucle
            error = type(exc).__name__

        ok = status == 201
        latency = time.perf_counter() - start
        result = {
            "at": datetime.now(UTC).isoformat(),
            "ok": ok,
            "stage": stage,
            "latency_ms": round(latency * 1000, 1),
        }
        self.results.append(result)
        PROBE_SUCCESS.set(1 if ok else 0)
        PROBE_LATENCY.observe(latency)
        if not ok:
            PROBE_FAILURES.labels(stage).inc()
        (log.info if ok else log.warning)("probe.result", **result, status=status, error=error)
        clear_contextvars()
        return result

    async def run(self) -> None:
        while True:
            started = time.monotonic()
            await self.probe_once()
            await asyncio.sleep(max(0.0, self.settings.interval_s - (time.monotonic() - started)))


def _is_decryption_failure(r: httpx.Response) -> bool:
    if r.status_code != 400:
        return False
    try:
        return r.json()["detail"]["code"] == "decryption_failed"
    except (ValueError, KeyError, TypeError):
        return False
