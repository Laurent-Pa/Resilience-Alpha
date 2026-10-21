"""Métriques Prometheus du moteur (exposées par le /metrics commun)."""

from prometheus_client import Counter, Gauge, Histogram

INCIDENTS = Counter("incidents_total", "Incidents traités", ["type", "outcome"])
ACTIONS = Counter("remediation_actions_total", "Actions exécutées", ["action", "result"])
MTTR = Histogram("incident_mttr_seconds", "Temps de rétablissement")
MTTD = Histogram("incident_mttd_seconds", "Temps de détection")
OPEN = Gauge("incidents_open", "Incidents non terminaux en cours")
