"""Classification explicite : d'une alerte normalisée vers un type d'incident (ou None)."""

from remediation_engine.core.models import Alert

_FLOOD_ALERTS = {"HighRequestRate", "High5xx", "DbPoolSaturated"}
_DOWN_ALERTS = {"ServiceDown", "Unhealthy"}


def classify(alert: Alert) -> str | None:
    t, target = alert.type, alert.target
    flood = (alert.source == "ml" and t == "anomaly") or t in _FLOOD_ALERTS
    if target == "payment-api" and flood:
        return "http_flood"
    if target == "payment-api" and t in _DOWN_ALERTS:
        return "service_down"
    if t == "KeycloakDown" or target == "keycloak":
        return "idp_down"
    if t == "WafBlocksBurst":
        return "injection_attempt"
    return None  # alerte non reconnue : ignorée (pas d'incident)
