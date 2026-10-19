"""Requêtes du contrôle d'invariant comptable."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

UNBALANCED_TX = text("""
    SELECT tx_id FROM payments.ledger_entries
    GROUP BY tx_id HAVING SUM(amount_cents) <> 0
""")

INCOMPLETE_TX = text("""
    SELECT t.id FROM payments.transactions t
    LEFT JOIN payments.ledger_entries e ON e.tx_id = t.id
    WHERE t.status = 'COMPLETED'
    GROUP BY t.id HAVING COUNT(e.id) <> 2
""")

NEGATIVE_ACCOUNTS = text("""
    SELECT e.account_id FROM payments.ledger_entries e
    JOIN payments.accounts a ON a.id = e.account_id
    WHERE a.label <> 'bank_reserve'
    GROUP BY e.account_id HAVING SUM(e.amount_cents) < 0
""")


async def _ids(s: AsyncSession, query) -> list[UUID]:
    return sorted(await s.scalars(query))


async def check(s: AsyncSession) -> dict[str, list[UUID]]:
    return {
        "unbalanced_tx": await _ids(s, UNBALANCED_TX),
        "incomplete_tx": await _ids(s, INCOMPLETE_TX),
        "negative_accounts": await _ids(s, NEGATIVE_ACCOUNTS),
    }
