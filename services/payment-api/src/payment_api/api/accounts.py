from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from payment_api.db import get_session
from payment_api.repo import accounts as accounts_repo
from payment_api.schemas import Account
from resilience_common.auth import Claims, require_role

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get(
    "/me",
    response_model=Account,
    responses={404: {"description": "Aucun compte associé à cet utilisateur"}},
)
async def my_account(
    session: Annotated[AsyncSession, Depends(get_session)],
    claims: Claims = Depends(require_role("client", "prober")),
) -> Account:
    """L'unique compte de l'utilisateur (un compte par personne)."""
    row = await accounts_repo.with_balance(session, claims.sub)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no_account")
    account, balance = row
    return Account(
        id=account.id,
        iban_masked=account.iban_masked,
        bic=account.bic,
        label=account.label,
        currency=account.currency,
        balance_cents=balance,
    )
