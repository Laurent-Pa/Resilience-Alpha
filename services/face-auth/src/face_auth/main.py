"""Point d'entrée : `uvicorn --factory face_auth.main:create_app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from face_auth import __version__
from face_auth.api import admin, internal
from face_auth.crypto import TemplateCipher
from face_auth.engine import Engine, FaceEngine
from face_auth.service import Biometrics
from face_auth.settings import Settings
from face_auth.store import MemoryStore, PgStore, Store
from resilience_common.auth import TokenVerifier
from resilience_common.health import health_router
from resilience_common.logging import RequestContextMiddleware, configure_logging
from resilience_common.metrics import MetricsMiddleware, metrics_router

API_PREFIX = "/api"


def _secret(value) -> str:
    return value.get_secret_value().strip() if value else ""


def make_store(settings: Settings) -> Store:
    if not settings.db_host:
        return MemoryStore()
    return PgStore(
        {
            "host": settings.db_host,
            "port": settings.db_port,
            "database": settings.db_name,
            "user": settings.db_user,
            "password": _secret(settings.db_password) or None,
        }
    )


def make_biometrics(settings: Settings, engine: Engine | None = None) -> Biometrics:
    if not _secret(settings.biometric_key):
        raise RuntimeError("biometric_key manquant : clé de chiffrement des empreintes requise")
    return Biometrics(
        make_store(settings),
        engine or FaceEngine(settings.models_dir),
        TemplateCipher.from_hex(_secret(settings.biometric_key)),
        threshold=settings.match_threshold,
        max_failures=settings.max_failures,
        lock_s=settings.lock_s,
    )


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or Settings.load()
    configure_logging(settings.service_name, settings.log_level)
    if not _secret(settings.face_service_token):
        raise RuntimeError("face_service_token manquant : jeton partagé avec Keycloak requis")
    bio = make_biometrics(settings, engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await bio.store.open()
        yield
        await bio.store.close()

    app = FastAPI(
        title="face-auth",
        version=__version__,
        description="Second facteur facial du back-office : enrôlement et vérification.",
        lifespan=lifespan,
    )
    app.state.biometrics = bio
    app.state.service_token = _secret(settings.face_service_token).encode()
    app.state.token_verifier = TokenVerifier(
        settings.oidc_issuer, settings.oidc_jwks_url, settings.oidc_audience
    )

    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router({"db": bio.store.ping}))
    app.include_router(metrics_router())
    app.include_router(internal.router)
    app.include_router(admin.router, prefix=API_PREFIX)
    return app
