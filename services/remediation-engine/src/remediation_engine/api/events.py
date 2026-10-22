"""GET /events : flux SSE des transitions (rôle ops). Jeton en query, jamais journalisé."""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query, Request, status
from sse_starlette.sse import EventSourceResponse

from resilience_common.auth import verify_token

router = APIRouter()

HEARTBEAT_S = 15


@router.get("/events")
async def events(request: Request, token: str = Query(...)) -> EventSourceResponse:
    claims = await verify_token(request, token)
    if "ops" not in claims.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")

    bus = request.app.state.bus
    queue = bus.subscribe()

    async def stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_S)
                    yield {"event": "incident", "data": json.dumps(event)}
                except TimeoutError:
                    yield {"event": "heartbeat", "data": ""}
        finally:
            bus.unsubscribe(queue)

    return EventSourceResponse(stream())
