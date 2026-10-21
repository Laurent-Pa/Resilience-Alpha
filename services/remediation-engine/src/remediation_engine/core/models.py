"""Modèles du moteur : alerte entrante, incident, plan, résultat d'action.

Les états sont de simples chaînes (sérialisables, lisibles dans les logs JSON et le SSE).
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from ipaddress import IPv4Address
from typing import Literal

from pydantic import BaseModel

DETECTED = "DETECTED"
TRIAGED = "TRIAGED"
EXECUTING = "EXECUTING"
VERIFYING = "VERIFYING"
RECOVERED = "RECOVERED"
ESCALATED = "ESCALATED"
TERMINAL = frozenset({RECOVERED, ESCALATED})


class Alert(BaseModel):
    """Modèle normalisé (ml-detector et Alertmanager convergent ici). Cf. alert.schema.json."""

    source: Literal["alertmanager", "ml"]
    type: str
    target: str
    src_ip: IPv4Address | None = None
    score: float | None = None
    at: datetime


@dataclass
class Plan:
    actions: list[str]
    verify: dict


@dataclass
class Incident:
    type: str
    target: str
    src_ip: IPv4Address | None
    plan: Plan
    detected_at: datetime
    mttd_s: float  # détection - début de l'anomalie (alert.at)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    state: str = DETECTED
    attempt: int = 0
    recovered_at: datetime | None = None
    mttr_s: float | None = None


@dataclass
class ActionResult:
    ok: bool
    duration_ms: float
    output: str = ""


def now() -> datetime:
    return datetime.now(UTC)
