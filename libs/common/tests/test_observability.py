import asyncio
import json
import uuid

import httpx
import structlog
from fastapi import FastAPI

from resilience_common.health import health_router
from resilience_common.logging import (
    RequestContextMiddleware,
    configure_logging,
    propagation_headers,
)
from resilience_common.metrics import MetricsMiddleware, metrics_router


def make_app(checks=None) -> FastAPI:
    app = FastAPI()
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router(checks))
    app.include_router(metrics_router())

    @app.get("/items/{item_id}")
    async def item(item_id: int) -> dict:
        structlog.get_logger().info("item.read", item_id=item_id)
        return {"outgoing": propagation_headers()}

    return app


def client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def log_lines(capsys) -> list[dict]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]


async def test_request_id_is_propagated_to_logs_and_response(capsys):
    configure_logging("test-svc")
    async with client(make_app()) as c:
        r = await c.get(
            "/items/7?token=secret",
            headers={"X-Request-ID": "req-123", "X-Forwarded-For": "10.0.0.9, 172.18.0.2"},
        )

    assert r.headers["x-request-id"] == "req-123"
    assert r.json() == {"outgoing": {"X-Request-ID": "req-123"}}

    lines = log_lines(capsys)
    business = next(line for line in lines if line["event"] == "item.read")
    access = next(line for line in lines if line["event"] == "http.request")
    for line in (business, access):
        assert line["trace_id"] == "req-123"
        assert line["src_ip"] == "10.0.0.9"
        assert line["service"] == "test-svc"
        assert "ts" in line and line["level"] == "info"
    assert access["status"] == 200
    assert access["path"] == "/items/7"
    assert "secret" not in json.dumps(lines)


async def test_request_id_is_generated_when_absent(capsys):
    configure_logging("test-svc")
    async with client(make_app()) as c:
        r = await c.get("/items/1")
    generated = r.headers["x-request-id"]
    assert uuid.UUID(generated)
    access = next(line for line in log_lines(capsys) if line["event"] == "http.request")
    assert access["trace_id"] == generated


async def test_health_live_and_ready_ok():
    async def db_ok() -> None:
        return None

    async with client(make_app({"db": db_ok})) as c:
        assert (await c.get("/health/live")).status_code == 200
        r = await c.get("/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "checks": {"db": "ok"}}


async def test_health_ready_fails_fast_on_slow_or_broken_check():
    async def db_slow() -> None:
        await asyncio.sleep(5)

    async def db_broken() -> None:
        raise ConnectionError

    async with client(make_app({"slow": db_slow, "broken": db_broken})) as c:
        r = await asyncio.wait_for(c.get("/health/ready"), timeout=2)
    assert r.status_code == 503
    assert r.json()["checks"] == {"slow": "fail: TimeoutError", "broken": "fail: ConnectionError"}


async def test_metrics_use_route_template():
    async with client(make_app()) as c:
        await c.get("/items/42")
        body = (await c.get("/metrics")).text
    assert 'http_requests_total{method="GET",route="/items/{item_id}",status="200"}' in body
    assert "http_request_duration_seconds_bucket" in body


async def test_metrics_count_requests_by_source_ip():
    async with client(make_app()) as c:
        await c.get("/items/42", headers={"X-Forwarded-For": "203.0.113.7, 172.18.0.2"})
        body = (await c.get("/metrics")).text
    assert 'http_requests_by_source_total{src_ip="203.0.113.7"}' in body
