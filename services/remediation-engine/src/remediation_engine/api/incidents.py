"""Lecture des incidents et stats (rôle ops)."""

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from remediation_engine.core import models as m
from remediation_engine.core.models import Incident
from resilience_common.auth import Claims, require_role

router = APIRouter()


def _view(inc: Incident) -> dict:
    return {
        "id": inc.id,
        "type": inc.type,
        "target": inc.target,
        "state": inc.state,
        "src_ip": str(inc.src_ip) if inc.src_ip else None,
        "detected_at": inc.detected_at.isoformat(),
        "recovered_at": inc.recovered_at.isoformat() if inc.recovered_at else None,
        "mttd_s": inc.mttd_s,
        "mttr_s": inc.mttr_s,
        "attempt": inc.attempt,
        "plan": {"actions": inc.plan.actions, "verify": inc.plan.verify},
    }


@router.get("/incidents")
async def list_incidents(
    request: Request,
    state: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    _: Claims = Depends(require_role("ops")),
) -> list[dict]:
    items = sorted(
        request.app.state.store.incidents.values(), key=lambda i: i.detected_at, reverse=True
    )
    if state:
        items = [i for i in items if i.state == state]
    return [_view(i) for i in items[:limit]]


@router.get("/incidents/{incident_id}")
async def get_incident(
    incident_id: str, request: Request, _: Claims = Depends(require_role("ops"))
) -> dict:
    store = request.app.state.store
    inc = store.incidents.get(incident_id)
    if inc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    transitions = [t for t in store.transitions if t["incident_id"] == incident_id]
    return {**_view(inc), "transitions": transitions}


@router.get("/stats")
async def stats(request: Request, _: Claims = Depends(require_role("ops"))) -> dict:
    incs = list(request.app.state.store.incidents.values())
    last = max(incs, key=lambda i: i.detected_at, default=None)
    return {
        "incidents_total": len(incs),
        "incidents_open": sum(1 for i in incs if i.state not in m.TERMINAL),
        "by_state": dict(Counter(i.state for i in incs)),
        "last_mttd_s": last.mttd_s if last else None,
        "last_mttr_s": last.mttr_s if last else None,
    }
