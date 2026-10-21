"""Cas d'usage transactionnels (orchestrent domaine + repo dans une transaction DB)."""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from payment_api.crypto import Pseudonymizer
from payment_api.domain import rules
from payment_api.domain.rules import NoAccount, TransferRequest, UnknownAccount
from payment_api.models import STATUS_COMPLETED, Transaction
from payment_api.repo import accounts as accounts_repo
from payment_api.repo import transactions as tx_repo


async def transfer(
    s: AsyncSession, key: str, owner: UUID, req: TransferRequest, pseudo: Pseudonymizer
) -> tuple[Transaction, bool]:
    """Exécute un virement idempotent. Renvoie (transaction, créée?)."""
    rules.validate_transfer(req)
    request_hash = rules.hash_request(pseudo.key, owner, req)

    try:
        async with s.begin():
            existing = await tx_repo.get_by_key(s, key)
            if existing:
                rules.check_replay(existing.request_hash, request_hash)
                return existing, False

            # Compte débité = l'unique compte du porteur du jeton.
            src = await accounts_repo.find_by_owner(s, owner)
            if src is None:
                raise NoAccount()
            dst = await accounts_repo.find_by_iban_hash(s, pseudo.iban_hash(req.dst_iban))
            if dst is None:
                raise UnknownAccount()
            rules.check_bic(dst.bic, req.dst_bic)
            rules.check_distinct(src.id, dst.id)

            await accounts_repo.lock_accounts(s, rules.lock_order(src.id, dst.id))
            rules.check_funds(await accounts_repo.balance(s, src.id), req.amount)

            tx = await tx_repo.insert(
                s, key, request_hash, owner, req, src.id, dst.id, STATUS_COMPLETED
            )
            await tx_repo.insert_entries(s, tx.id, [(src.id, -req.amount), (dst.id, req.amount)])
            return tx, True
    except IntegrityError:
        # Course entre deux requêtes portant la même clé : l'autre a gagné, on la relit.
        async with s.begin():
            existing = await tx_repo.get_by_key(s, key)
        if existing is None:
            raise
        rules.check_replay(existing.request_hash, request_hash)
        return existing, False
