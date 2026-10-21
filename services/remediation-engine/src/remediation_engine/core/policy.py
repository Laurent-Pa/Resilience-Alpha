"""Politique : type d'incident -> plan (actions + critères de vérification), depuis le YAML."""

from pathlib import Path

import yaml

from remediation_engine.core.models import Plan

# playbook_map.yaml est packagé avec le module (racine du package).
DEFAULT_PATH = Path(__file__).resolve().parents[1] / "playbook_map.yaml"


class Policy:
    def __init__(self, path: Path | str = DEFAULT_PATH) -> None:
        self._map: dict = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    def plan_for(self, incident_type: str) -> Plan:
        entry = self._map[incident_type]  # KeyError si type inconnu (le classifier filtre avant)
        return Plan(actions=list(entry["actions"]), verify=dict(entry.get("verify", {})))
