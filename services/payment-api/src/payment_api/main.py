"""Point d'entrée : `uvicorn --factory payment_api.main:create_app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from payment_api import __version__, crypto
from payment_api.api import accounts, admin, payments
from payment_api.db import make_engine, make_sessionmaker, ping
from payment_api.settings import Settings
from resilience_common.auth import TokenVerifier
from resilience_common.health import health_router
from resilience_common.logging import RequestContextMiddleware, configure_logging
from resilience_common.metrics import MetricsMiddleware, metrics_router

log = structlog.get_logger()

API_PREFIX = "/api"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    configure_logging(settings.service_name, settings.log_level)

    app = FastAPI(
        title="payment-api",
        version=__version__,
        description="Virements idempotents entre comptes fictifs, ledger en partie double.",
        lifespan=lifespan,
    )
    engine = make_engine(settings)
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.token_verifier = TokenVerifier(
        settings.oidc_issuer, settings.oidc_jwks_url, settings.oidc_audience
    )
    app.state.pseudonymizer = crypto.pseudonymizer_from(settings)
    app.state.transfer_cipher, ephemeral = crypto.cipher_from(settings)
    if ephemeral:
        log.warning(
            "crypto.ephemeral_rsa_key",
            key_id=app.state.transfer_cipher.key_id,
            hint="fournir $SECRETS_DIR/rsa_private_key pour une clé stable entre redémarrages",
        )

    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestContextMiddleware)

    # Sondes techniques à la racine (Docker, Prometheus) ; API métier sous /api.
    app.include_router(health_router({"db": lambda: ping(engine)}))
    app.include_router(metrics_router())
    for router in (payments.router, accounts.router, admin.router):
        app.include_router(router, prefix=API_PREFIX)
    return app
