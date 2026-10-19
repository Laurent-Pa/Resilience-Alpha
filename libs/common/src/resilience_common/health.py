"""Endpoints /health/live et /health/ready.

`ready` n'exécute que les checks injectés : uniquement des dépendances réellement
bloquantes (la DB), jamais Keycloak.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping

from fastapi import APIRouter, Response

Check = Callable[[], Awaitable[object]]


def health_router(checks: Mapping[str, Check] | None = None, timeout_s: float = 0.5) -> APIRouter:
    router = APIRouter(tags=["health"])
    checks = dict(checks or {})

    @router.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/health/ready")
    async def ready(response: Response) -> dict[str, object]:
        results: dict[str, str] = {}
        for name, check in checks.items():
            try:
                await asyncio.wait_for(check(), timeout_s)
                results[name] = "ok"
            except Exception as exc:
                results[name] = f"fail: {type(exc).__name__}"
        ok = all(r == "ok" for r in results.values())
        if not ok:
            response.status_code = 503
        return {"status": "ok" if ok else "fail", "checks": results}

    return router
