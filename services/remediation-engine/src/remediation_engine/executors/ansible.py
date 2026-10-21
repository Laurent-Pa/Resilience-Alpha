"""Exécuteur réel via ansible-runner (playbooks de l'infra, montés dans /playbooks).

Une action = un playbook `<action>.yml`, paramètres validés passés en extravars, exécuté en
local dans le conteneur (le playbook joint Docker via docker-socket-proxy, jamais docker.sock).
Un échec, un timeout ou une exception donne ActionResult(ok=False) : l'orchestrateur décide.
"""

import asyncio
import sys
import tempfile
import time
from pathlib import Path

import structlog
from pydantic import BaseModel

from remediation_engine.core.models import ActionResult

log = structlog.get_logger()
INVENTORY = f"localhost ansible_connection=local ansible_python_interpreter={sys.executable}"


class AnsibleExecutor:
    def __init__(self, playbooks_dir: str = "/playbooks", timeout_s: float = 60) -> None:
        self.playbooks_dir = playbooks_dir
        self.timeout_s = timeout_s

    def missing_playbooks(self, actions) -> list[str]:
        return [a for a in actions if not (Path(self.playbooks_dir) / f"{a}.yml").is_file()]

    async def run(self, action: str, params: BaseModel) -> ActionResult:
        t0 = time.monotonic()
        try:
            status, rc, tail = await asyncio.to_thread(
                self._run_sync, action, params.model_dump(mode="json")
            )
        except Exception as exc:
            log.exception("ansible.error", action=action)
            return ActionResult(False, (time.monotonic() - t0) * 1000, type(exc).__name__)
        ok = status == "successful" and rc == 0
        output = f"{status} rc={rc}" + ("" if ok else f" | {tail}")
        return ActionResult(ok, (time.monotonic() - t0) * 1000, output)

    def _run_sync(self, action: str, extravars: dict) -> tuple[str, int, str]:
        import ansible_runner  # import paresseux : ansible ne s'importe pas sous Windows (tests)

        with tempfile.TemporaryDirectory() as tmp:
            r = ansible_runner.run(
                private_data_dir=tmp,
                project_dir=self.playbooks_dir,
                playbook=f"{action}.yml",
                inventory=INVENTORY,
                extravars=extravars,
                timeout=int(self.timeout_s),  # status "timeout" si dépassé
                quiet=True,
            )
            tail = r.stdout.read()[-300:] if r.status != "successful" else ""
            return r.status, r.rc, tail
