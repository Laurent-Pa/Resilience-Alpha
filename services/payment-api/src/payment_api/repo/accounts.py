from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from payment_api.models import Account, LedgerEntry


async def lock_accounts(s: AsyncSession, ids: list[UUID]) -> dict[UUID, Account]:
    """SELECT … FOR UPDATE ; l'ORDER BY garantit l'ordre d'acquisition des verrous."""
    rows = await s.scalars(
        select(Account).where(Account.id.in_(ids)).order_by(Account.id).with_for_update()
    )
    return {a.id: a for a in rows}


async def find_by_owner(s: AsyncSession, owner: UUID) -> Account | None:
    return await s.scalar(select(Account).where(Account.owner_id == owner))


async def find_by_iban_hash(s: AsyncSession, iban_hash: str) -> Account | None:
    return await s.scalar(select(Account).where(Account.iban_hash == iban_hash))


async def balance(s: AsyncSession, account_id: UUID) -> int:
    total = await s.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(
            LedgerEntry.account_id == account_id
        )
    )
    return int(total or 0)


async def owned_ids(s: AsyncSession, owner: UUID) -> list[UUID]:
    return list(await s.scalars(select(Account.id).where(Account.owner_id == owner)))


async def with_balance(s: AsyncSession, owner: UUID) -> tuple[Account, int] | None:
    stmt = (
        select(Account, func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
        .outerjoin(LedgerEntry, LedgerEntry.account_id == Account.id)
        .where(Account.owner_id == owner)
        .group_by(Account.id)
    )
    row = (await s.execute(stmt)).one_or_none()
    return (row[0], int(row[1])) if row else None
