from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from payment_api.db import get_session
from payment_api.models import INITIATED_BY_PROBER
from payment_api.repo import ledger as ledger_repo
from payment_api.repo import transactions as tx_repo
from payment_api.schemas import AdminPayment, LedgerCheck, PaymentPage
from resilience_common.auth import require_role

log = structlog.get_logger()
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role("ops"))])

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/ledger/check", response_model=LedgerCheck)
async def ledger_check(session: Session) -> LedgerCheck:
    """Invariant comptable : chaque transaction s'équilibre, a deux écritures, et aucun
    compte client n'est négatif. Utilisé par le verifier du moteur de remédiation."""
    found = await ledger_repo.check(session)
    result = LedgerCheck(ok=not any(found.values()), **found)
    log.info("ledger.check", ok=result.ok, **{k: len(v) for k, v in found.items()})
    return result


@router.get("/payments", response_model=PaymentPage)
async def list_all_payments(
    session: Session,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200, alias="page_size")] = 20,
    include_prober: bool = False,
) -> PaymentPage:
    """Vue back-office : les virements, tous émetteurs/destinataires confondus
    (contrairement à GET /payments, qui ne renvoie que l'historique de l'appelant).

    Le trafic de la sonde est écarté par défaut : elle émet un virement toutes les
    quelques secondes et noierait la liste. `include_prober=true` le réintègre.

    L'IBAN n'est jamais exposé qu'au format masqué (`AdminPayment.dst_iban_masked`,
    ex. "FR****8995") : c'est la seule forme stockée en base, il n'y a donc rien
    à filtrer ici."""
    excluded = None if include_prober else INITIATED_BY_PROBER
    offset = (page - 1) * page_size
    total = await tx_repo.count_all(session, exclude_initiated_by=excluded)
    txs = await tx_repo.list_all(
        session, limit=page_size, offset=offset, exclude_initiated_by=excluded
    )
    log.info(
        "admin.payments.list",
        page=page,
        page_size=page_size,
        total=total,
        include_prober=include_prober,
    )
    return PaymentPage(
        items=[AdminPayment.model_validate(t) for t in txs],
        total=total,
        page=page,
        page_size=page_size,
    )
