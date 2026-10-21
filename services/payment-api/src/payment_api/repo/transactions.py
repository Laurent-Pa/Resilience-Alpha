from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from payment_api.domain import iban
from payment_api.domain.rules import TransferRequest
from payment_api.models import (
    INITIATED_BY_VALUES,
    STATUS_COMPLETED,
    Account,
    LedgerEntry,
    Transaction,
)


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
    initiated_by: str,
) -> Transaction:
    tx = Transaction(
        idempotency_key=key,
        request_hash=request_hash,
        owner_id=owner,
        src_account=src_account,
        dst_account=dst_account,
        dst_iban_masked=iban.mask(req.dst_iban),
        amount=req.amount,
        status=status,
        initiated_by=initiated_by,
    )
    s.add(tx)
    await s.flush()
    return tx


async def insert_entries(s: AsyncSession, tx_id: UUID, entries: list[tuple[UUID, Decimal]]) -> None:
    s.add_all(LedgerEntry(tx_id=tx_id, account_id=a, amount=amt) for a, amt in entries)
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


def _kept_origins(excluded: str) -> list[str]:
    """Les origines à conserver, en `IN (...)` plutôt qu'en `!=` : seule la forme en
    égalités sait utiliser `ix_transactions_initiated_created`, et la sonde domine
    vite la table."""
    return [v for v in INITIATED_BY_VALUES if v != excluded]


async def list_all(
    s: AsyncSession, limit: int, offset: int, exclude_initiated_by: str | None = None
) -> list[Transaction]:
    """Vue admin : les virements, tous émetteurs/destinataires confondus.
    `exclude_initiated_by` écarte une origine (la sonde, par défaut côté API).
    `AdminPayment.dst_iban_masked` (seule forme d'IBAN exposée) reste masquée comme
    pour les autres vues ; aucun IBAN en clair n'est jamais stocké ni renvoyé."""
    stmt = select(Transaction)
    if exclude_initiated_by is not None:
        stmt = stmt.where(Transaction.initiated_by.in_(_kept_origins(exclude_initiated_by)))
    stmt = stmt.order_by(Transaction.created_at.desc()).limit(limit).offset(offset)
    return list(await s.scalars(stmt))


async def count_all(s: AsyncSession, exclude_initiated_by: str | None = None) -> int:
    """Même filtre que `list_all` : sinon la pagination compterait des lignes que la
    liste n'affiche pas."""
    stmt = select(func.count()).select_from(Transaction)
    if exclude_initiated_by is not None:
        stmt = stmt.where(Transaction.initiated_by.in_(_kept_origins(exclude_initiated_by)))
    total = await s.scalar(stmt)
    return int(total or 0)


async def completed_per_minute(
    s: AsyncSession, initiated_by: str, start: datetime, end: datetime
) -> dict[datetime, int]:
    """Virements réussis d'une origine, comptés par minute sur [start, end). Les minutes
    sans virement sont absentes : à l'appelant de les compléter. Servie par
    `ix_transactions_initiated_created` (égalité sur l'origine + plage sur la date)."""
    minute = func.date_trunc("minute", Transaction.created_at).label("minute")
    stmt = (
        select(minute, func.count())
        .where(
            Transaction.initiated_by == initiated_by,
            Transaction.status == STATUS_COMPLETED,
            Transaction.created_at >= start,
            Transaction.created_at < end,
        )
        .group_by(minute)
    )
    return {m: n for m, n in (await s.execute(stmt)).all()}
