"""POST /alerts : entrée signée HMAC des alertes (ml-detector et Alertmanager)."""

import json

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import ValidationError

from remediation_engine.core.classifier import classify
from remediation_engine.core.models import Alert
from resilience_common.hmac import verify

router = APIRouter()


def normalize(data: dict) -> Alert:
    """ml-detector (alert.schema.json) et webhook Alertmanager v4 -> modèle Alert unique."""
    if "alerts" in data:  # webhook Alertmanager v4 : on prend la première alerte
        first = data["alerts"][0]
        labels = first.get("labels", {})
        return Alert(
            source="alertmanager",
            type=labels.get("alertname", "unknown"),
            target=labels.get("service", "unknown"),
            src_ip=labels.get("src_ip"),
            at=first.get("startsAt"),
        )
    return Alert(**data)  # format ml : les champs en trop (features) sont ignorés


@router.post("/alerts", status_code=status.HTTP_202_ACCEPTED)
async def post_alert(request: Request, x_signature: str | None = Header(default=None)) -> dict:
    raw = await request.body()
    if not verify(request.app.state.hmac_secret, raw, x_signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_signature")
    try:
        alert = normalize(json.loads(raw))
    except (ValueError, KeyError, ValidationError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_alert") from exc

    inc_type = classify(alert)
    if inc_type is None:
        return {"status": "ignored"}  # alerte non reconnue : pas d'incident
    inc = await request.app.state.orchestrator.submit(alert, inc_type)
    return {"status": "accepted", "incident_id": inc.id, "type": inc_type}
