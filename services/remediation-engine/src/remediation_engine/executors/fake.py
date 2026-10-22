"""Exécuteur factice : succès (ou échec configurable) avec un petit délai. Dev + tests."""

import asyncio

from pydantic import BaseModel

from remediation_engine.core.models import ActionResult


class FakeExecutor:
    def __init__(self, *, ok: bool = True, delay_s: float = 0.02) -> None:
        self.ok = ok
        self.delay_s = delay_s
        self.calls: list[tuple[str, dict]] = []  # inspecté par les tests

    async def run(self, action: str, params: BaseModel) -> ActionResult:
        self.calls.append((action, params.model_dump(mode="json")))
        await asyncio.sleep(self.delay_s)
        return ActionResult(ok=self.ok, duration_ms=self.delay_s * 1000, output="fake")
