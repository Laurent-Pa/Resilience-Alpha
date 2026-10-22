"""Bus de publication en mémoire : chaque abonné SSE a sa file. Publication non bloquante."""

import asyncio
import contextlib


class Bus:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    async def publish(self, event: dict) -> None:
        for q in list(self._subs):
            with contextlib.suppress(asyncio.QueueFull):  # un abonné lent ne bloque pas le moteur
                q.put_nowait(event)
