from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from payment_api.db import get_session
from payment_api.repo import ledger as ledger_repo
from payment_api.schemas import LedgerCheck
from resilience_common.auth import require_role

log = structlog.get_logger()
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role("ops"))])


@router.get("/ledger/check", response_model=LedgerCheck)
async def ledger_check(session: Annotated[AsyncSession, Depends(get_session)]) -> LedgerCheck:
    """Invariant comptable : chaque transaction s'équilibre, a deux écritures, et aucun
    compte client n'est négatif. Utilisé par le verifier du moteur de remédiation."""
    found = await ledger_repo.check(session)
    result = LedgerCheck(ok=not any(found.values()), **found)
    log.info("ledger.check", ok=result.ok, **{k: len(v) for k, v in found.items()})
    return result
