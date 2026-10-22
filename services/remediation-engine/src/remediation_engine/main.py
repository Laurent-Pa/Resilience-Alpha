"""Point d'entrée : `uvicorn --factory remediation_engine.main:create_app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI

from remediation_engine.api import alerts, events, incidents
from remediation_engine.bus import Bus
from remediation_engine.core.actions import ALLOWED
from remediation_engine.core.orchestrator import Orchestrator
from remediation_engine.core.policy import Policy
from remediation_engine.core.verifier import FakeVerifier, Verifier
from remediation_engine.executors.ansible import AnsibleExecutor
from remediation_engine.executors.fake import FakeExecutor
from remediation_engine.settings import Settings
from remediation_engine.store import Store
from resilience_common.auth import TokenVerifier
from resilience_common.health import health_router
from resilience_common.logging import RequestContextMiddleware, configure_logging
from resilience_common.metrics import MetricsMiddleware, metrics_router

log = structlog.get_logger()


def _secret(value) -> str:
    return value.get_secret_value().strip() if value else ""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    configure_logging(settings.service_name, settings.log_level)
    if settings.webhook_hmac_key is None:
        raise RuntimeError("webhook_hmac_key manquant : secret HMAC requis pour POST /alerts")

    store = Store(_db_connect(settings))
    bus = Bus()
    if settings.executor == "ansible":
        executor = AnsibleExecutor(settings.playbooks_dir, settings.action_timeout_s)
        # Pas de crash au boot (le moteur doit rester joignable) : chaque action manquante
        # échouera puis escaladera. Mais l'écart doit sauter aux yeux dans les logs.
        if missing := executor.missing_playbooks(ALLOWED):
            log.error("ansible.playbooks_missing", dir=settings.playbooks_dir, missing=missing)
    else:
        executor = FakeExecutor()
    verifier = FakeVerifier()  # remplacé par le vrai Verifier dans lifespan si verifier=real
    orchestrator = Orchestrator(
        store,
        bus,
        executor,
        verifier,
        Policy(),
        cooldown_s=settings.cooldown_s,
        flapping_max=settings.flapping_max,
        flapping_window_s=settings.flapping_window_s,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        for inc in await store.open():
            log.info("remediation.resume", incident_id=inc.id, state=inc.state)
            orchestrator.resume(inc)
        async with httpx.AsyncClient(timeout=5, verify=settings.ca_bundle or True) as client:
            if settings.verifier == "real":
                orchestrator.verifier = Verifier(
                    client,
                    settings.prober_status_url,
                    settings.ledger_url,
                    token_url=settings.kc_token_url,
                    client_id=settings.client_id,
                    client_secret=_secret(settings.remediation_client_secret),
                )
            yield
        await store.close()

    app = FastAPI(title="remediation-engine", lifespan=lifespan)
    app.state.store = store
    app.state.bus = bus
    app.state.orchestrator = orchestrator
    app.state.hmac_secret = _secret(settings.webhook_hmac_key).encode()
    app.state.alert_token = _secret(settings.alertmanager_token).encode()
    app.state.token_verifier = TokenVerifier(
        settings.oidc_issuer, settings.oidc_jwks_url, settings.oidc_audience
    )

    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router())
    app.include_router(metrics_router())
    app.include_router(alerts.router)
    app.include_router(incidents.router)
    app.include_router(events.router)
    return app


def _db_connect(settings: Settings) -> dict | None:
    if not settings.db_host:
        return None
    return {
        "host": settings.db_host,
        "port": settings.db_port,
        "database": settings.db_name,
        "user": settings.db_user,
        "password": _secret(settings.db_password) or None,
    }
