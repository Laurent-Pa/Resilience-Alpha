"""Métriques HTTP Prometheus et endpoint /metrics."""

import time

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from resilience_common.logging import client_ip

HTTP_REQUESTS = Counter(
    "http_requests_total", "Requêtes HTTP traitées", ["method", "route", "status"]
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds", "Durée des requêtes HTTP", ["method", "route"]
)
# Labellé par IP source uniquement (cardinalité = nb d'IP, bornée en labo) : sert à la
# remédiation (block_ip) à repérer l'IP dominante d'un flood via topk(sum by (src_ip)).
HTTP_REQUESTS_BY_SOURCE = Counter(
    "http_requests_by_source_total", "Requêtes HTTP par IP source", ["src_ip"]
)


class MetricsMiddleware:
    """Compte les requêtes par gabarit de route (`/payments/{payment_id}`), pas par URL brute."""

    def __init__(self, app: ASGIApp, skip_paths: tuple[str, ...] = ("/metrics",)) -> None:
        self.app = app
        self.skip_paths = skip_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in self.skip_paths:
            await self.app(scope, receive, send)
            return

        status = 500
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            template = getattr(scope.get("route"), "path", "unmatched")
            method = scope["method"]
            HTTP_REQUESTS.labels(method, template, str(status)).inc()
            HTTP_DURATION.labels(method, template).observe(time.perf_counter() - start)
            HTTP_REQUESTS_BY_SOURCE.labels(client_ip(Headers(scope=scope), scope) or "unknown").inc()


def metrics_router() -> APIRouter:
    router = APIRouter()

    @router.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return router
