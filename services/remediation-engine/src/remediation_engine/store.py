"""Stockage en mémoire : incidents, transitions, et fenêtre récente pour cooldown/flapping.

shortcut: en mémoire, perdu au redémarrage. Passer au schéma Postgres `remediation`
(incidents/transitions/alerts) + reprise des incidents EXECUTING/VERIFYING -> VERIFYING
avant l'étape 7 (le moteur doit survivre à son propre redémarrage).
"""

from collections import deque
from datetime import datetime

from remediation_engine.core.models import TERMINAL, Incident


class Store:
    def __init__(self) -> None:
        self.incidents: dict[str, Incident] = {}
        self.transitions: list[dict] = []
        self.last_terminal: dict[str, datetime] = {}  # target -> fin du dernier incident (cooldown)
        self._recent: deque[tuple[str, datetime]] = deque(maxlen=500)  # (target, detected_at)

    def add(self, inc: Incident) -> None:
        self.incidents[inc.id] = inc
        self._recent.append((inc.target, inc.detected_at))

    def open_for(self, type_: str, target: str) -> Incident | None:
        for inc in self.incidents.values():
            if inc.type == type_ and inc.target == target and inc.state not in TERMINAL:
                return inc
        return None

    def record_transition(self, row: dict) -> None:
        self.transitions.append(row)

    def recent_count(self, target: str, since: datetime) -> int:
        return sum(1 for tg, at in self._recent if tg == target and at >= since)
