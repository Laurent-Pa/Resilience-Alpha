"""Exécuteur réel via ansible-runner (playbooks de l'infra, montés dans /playbooks).

shortcut: non branché ; implémentation (ansible_runner.run_async + timeout) et dépendance
ansible-runner à l'étape 7, avec les playbooks block_ip/recycle_service/kill_db_conns.
"""

from pydantic import BaseModel

from remediation_engine.core.models import ActionResult


class AnsibleExecutor:
    def __init__(self, playbooks_dir: str = "/playbooks") -> None:
        self.playbooks_dir = playbooks_dir

    async def run(self, action: str, params: BaseModel) -> ActionResult:
        raise NotImplementedError("AnsibleExecutor branché à l'étape 7 (playbooks infra)")
