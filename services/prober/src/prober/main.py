"""Point d'entrée : `uvicorn --factory prober.main:create_app`.

La boucle de sonde tourne en tâche de fond ; HTTP n'expose que /status, /metrics et /health.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI

from prober.probe import Prober
from prober.settings import Settings
from resilience_common.health import health_router
from resilience_common.logging import configure_logging
from resilience_common.metrics import metrics_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    configure_logging(settings.service_name, settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(
            verify=settings.ca_bundle or True, timeout=settings.timeout_s
        ) as client:
            app.state.prober = Prober(settings, client)
            task = asyncio.create_task(app.state.prober.run())
            yield
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="prober", lifespan=lifespan)
    app.include_router(health_router())
    app.include_router(metrics_router())

    @app.get("/status")
    async def status() -> list[dict]:
        """Les 60 derniers résultats, du plus ancien au plus récent."""
        return list(app.state.prober.results)

    return app
