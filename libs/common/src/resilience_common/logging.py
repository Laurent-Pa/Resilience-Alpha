"""Logs JSON sur une ligne (structlog) et middleware de contexte de requête.

Le middleware lit `X-Request-ID` (posé par le WAF) ou en génère un, l'expose comme
`trace_id` dans tous les logs de la requête, et le renvoie dans la réponse.
"""

import logging
import time
import uuid

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.contextvars import bind_contextvars, clear_contextvars, get_contextvars

MAX_REQUEST_ID_LEN = 128

log = structlog.get_logger()


def configure_logging(service: str, level: str = "INFO") -> None:
    def add_service(_logger: object, _method: str, event_dict: dict) -> dict:
        event_dict.setdefault("service", service)
        return event_dict

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            add_service,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def client_ip(headers: Headers, scope: Scope) -> str | None:
    if forwarded := headers.get("x-forwarded-for"):
        return forwarded.split(",")[0].strip()
    if real_ip := headers.get("x-real-ip"):
        return real_ip.strip()
    client = scope.get("client")
    return client[0] if client else None


def propagation_headers() -> dict[str, str]:
    """Headers à ajouter aux appels sortants pour propager le trace_id."""
    trace_id = get_contextvars().get("trace_id")
    return {"X-Request-ID": trace_id} if trace_id else {}


class RequestContextMiddleware:
    """Middleware ASGI pur : trace_id, src_ip, et une ligne `http.request` par requête.

    Seul le chemin est journalisé, jamais la query string (elle peut porter un jeton SSE).
    """

    def __init__(
        self,
        app: ASGIApp,
        skip_paths: tuple[str, ...] = ("/metrics", "/health/live", "/health/ready"),
    ) -> None:
        self.app = app
        self.skip_paths = skip_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        trace_id = (headers.get("x-request-id") or uuid.uuid4().hex)[:MAX_REQUEST_ID_LEN]
        clear_contextvars()
        bind_contextvars(trace_id=trace_id, src_ip=client_ip(headers, scope))

        status = 500
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message).append("X-Request-ID", trace_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            log.exception("http.unhandled_error", path=scope["path"])
            raise
        finally:
            if scope["path"] not in self.skip_paths:
                log.info(
                    "http.request",
                    method=scope["method"],
                    path=scope["path"],
                    status=status,
                    latency_ms=round((time.perf_counter() - start) * 1000, 1),
                )
            clear_contextvars()
