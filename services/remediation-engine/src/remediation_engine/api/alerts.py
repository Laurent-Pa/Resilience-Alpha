"""POST /alerts : entrée signée HMAC des alertes (ml-detector et Alertmanager).

Authentification : signature HMAC du corps (`X-Signature`, ml-detector) OU jeton bearer
(`Authorization: Bearer`, Alertmanager, qui ne sait pas signer un corps).
Chaque alerte reçue est journalisée brute (table `alerts`, audit), y compris celles ignorées.
"""

import hmac
import json

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import ValidationError

from remediation_engine.core.classifier import classify
from remediation_engine.core.models import Alert
from resilience_common.hmac import verify

router = APIRouter()


def _authorized(request: Request, raw: bytes, signature: str | None) -> bool:
    if verify(request.app.state.hmac_secret, raw, signature):
        return True
    token = request.app.state.alert_token
    auth = request.headers.get("authorization", "")
    if not token or not auth.startswith("Bearer "):
        return False  # jeton non configuré : bearer refusé (pas de jeton vide accepté)
    return hmac.compare_digest(auth.removeprefix("Bearer ").strip().encode(), token)


def normalize(data: dict) -> list[tuple[Alert, dict]]:
    """ml-detector (alert.schema.json) et webhook Alertmanager v4 -> [(Alert, brut)].

    Alertmanager groupe plusieurs alertes et renvoie aussi les `resolved` (send_resolved) :
    seules les `firing` déclenchent quelque chose, sinon une résolution relancerait un incident.
    """
    if "alerts" in data:
        out = []
        for item in data["alerts"]:
            if item.get("status", "firing") != "firing":
                continue
            labels = item.get("labels", {})
            alert = Alert(
                source="alertmanager",
                type=labels.get("alertname", "unknown"),
                target=labels.get("service", "unknown"),
                src_ip=labels.get("src_ip"),
                at=item.get("startsAt"),
            )
            out.append((alert, item))
        return out
    return [(Alert(**data), data)]  # format ml : les champs en trop (features) sont ignorés


@router.post("/alerts", status_code=status.HTTP_202_ACCEPTED)
async def post_alert(request: Request, x_signature: str | None = Header(default=None)) -> dict:
    raw = await request.body()
    if not _authorized(request, raw, x_signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_signature")
    try:
        alerts = normalize(json.loads(raw))
    except (ValueError, KeyError, TypeError, ValidationError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_alert") from exc

    store = request.app.state.store
    incidents = []
    for alert, item in alerts:
        inc_type = classify(alert)
        inc = None
        if inc_type is not None:
            if inc_type == "idp_down":
                alert.target = "keycloak"  # le recyclage vise l'IdP, pas l'émetteur (ex. prober)
            inc = await request.app.state.orchestrator.submit(alert, inc_type)
            incidents.append({"incident_id": inc.id, "type": inc_type})
        await store.record_alert(inc.id if inc else None, item)

    if not incidents:
        return {"status": "ignored"}  # rien de reconnu (ou que des `resolved`) : pas d'incident
    return {"status": "accepted", **incidents[0], "incidents": incidents}
