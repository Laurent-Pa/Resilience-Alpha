"""Point d'entrée : `uvicorn --factory remediation_engine.main:create_app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from remediation_engine.api import alerts, events, incidents
from remediation_engine.bus import Bus
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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    configure_logging(settings.service_name, settings.log_level)
    if settings.webhook_hmac_key is None:
        raise RuntimeError("webhook_hmac_key manquant : secret HMAC requis pour POST /alerts")

    store = Store()
    bus = Bus()
    executor = FakeExecutor() if settings.executor == "fake" else AnsibleExecutor()
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
        if settings.verifier != "real":
            yield
            return
        async with httpx.AsyncClient(timeout=5) as client:
            orchestrator.verifier = Verifier(
                client, settings.prober_status_url, settings.ledger_url
            )
            yield

    app = FastAPI(title="remediation-engine", lifespan=lifespan)
    app.state.store = store
    app.state.bus = bus
    app.state.orchestrator = orchestrator
    app.state.hmac_secret = settings.webhook_hmac_key.get_secret_value().strip().encode()
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
