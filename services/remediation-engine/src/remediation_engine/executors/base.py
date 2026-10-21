"""Interface d'exécution d'une action. Le moteur ne connaît que ce contrat."""

from typing import Protocol

from pydantic import BaseModel

from remediation_engine.core.models import ActionResult


class Executor(Protocol):
    async def run(self, action: str, params: BaseModel) -> ActionResult: ...
