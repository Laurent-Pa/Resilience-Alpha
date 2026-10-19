from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from payment_api.domain import iban
from payment_api.domain.rules import TransferRequest
from payment_api.models import Account, LedgerEntry, Transaction


async def get_by_key(s: AsyncSession, key: str) -> Transaction | None:
    return await s.scalar(select(Transaction).where(Transaction.idempotency_key == key))


async def get(s: AsyncSession, tx_id: UUID) -> Transaction | None:
    return await s.get(Transaction, tx_id)


async def insert(
    s: AsyncSession,
    key: str,
    request_hash: str,
    owner: UUID,
    req: TransferRequest,
    src_account: UUID,
    dst_account: UUID,
    status: str,
) -> Transaction:
    tx = Transaction(
        idempotency_key=key,
        request_hash=request_hash,
        owner_id=owner,
        src_account=src_account,
        dst_account=dst_account,
        dst_iban_masked=iban.mask(req.dst_iban),
        amount_cents=req.amount_cents,
        status=status,
    )
    s.add(tx)
    await s.flush()
    return tx


async def insert_entries(s: AsyncSession, tx_id: UUID, entries: list[tuple[UUID, int]]) -> None:
    s.add_all(LedgerEntry(tx_id=tx_id, account_id=a, amount_cents=amt) for a, amt in entries)
    await s.flush()


async def is_visible_to(s: AsyncSession, tx: Transaction, user: UUID) -> bool:
    """Visible par l'émetteur et par le propriétaire du compte destinataire."""
    if tx.owner_id == user:
        return True
    dst_owner = await s.scalar(select(Account.owner_id).where(Account.id == tx.dst_account))
    return dst_owner == user


async def history(s: AsyncSession, user: UUID, account_ids: list[UUID], limit: int):
    stmt = (
        select(Transaction)
        .where(or_(Transaction.owner_id == user, Transaction.dst_account.in_(account_ids)))
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    return list(await s.scalars(stmt))
