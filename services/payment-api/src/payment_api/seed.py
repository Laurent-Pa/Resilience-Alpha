"""Comptes fictifs, un par personne. Idempotent : peut être rejoué à chaque démarrage.

Les UUID des utilisateurs DOIVENT être identiques aux `id` fixés dans
keycloak/realm-resilience.json (le `sub` du jeton devient `owner_id`).

Les IBAN (code banque fictif 99999) ne sont stockés qu'en HMAC + forme masquée.
Pour les connaître en démo : `python -m payment_api.seed`.
"""

from dataclasses import dataclass
from uuid import UUID, uuid5

import structlog
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from payment_api.crypto import Pseudonymizer
from payment_api.domain import iban
from payment_api.models import STATUS_COMPLETED, Account, LedgerEntry, Transaction

USERS: dict[str, UUID] = {
    "alice": UUID("11111111-1111-4111-8111-111111111111"),
    "bob": UUID("22222222-2222-4222-8222-222222222222"),
    "carol": UUID("33333333-3333-4333-8333-333333333333"),
    "operator": UUID("44444444-4444-4444-8444-444444444444"),  # ops : pas de compte
    # Service account du client Keycloak `prober`.
    "prober": UUID("55555555-5555-4555-8555-555555555555"),
}

# Propriétaires techniques, sans utilisateur Keycloak.
BANK_OWNER = UUID(int=0)
PROBE_SINK_OWNER = UUID(int=1)
BANK_RESERVE_LABEL = "bank_reserve"

_NAMESPACE = UUID("6f1c2d3e-0000-4000-8000-00000000a1fa")


@dataclass(frozen=True)
class SeedAccount:
    name: str
    owner: UUID
    label: str
    number: int  # n° de compte à 11 chiffres, base de l'IBAN
    opening_cents: int

    @property
    def iban(self) -> str:
        return iban.make_fr(self.number)


SEED_ACCOUNTS: list[SeedAccount] = [
    SeedAccount("alice", USERS["alice"], "Compte courant", 10_000_000_011, 150_000),
    SeedAccount("bob", USERS["bob"], "Compte courant", 10_000_000_021, 80_000),
    SeedAccount("carol", USERS["carol"], "Compte courant", 10_000_000_031, 250_000),
    # Le prober paie 1 centime toutes les 5 s vers PROBE_SINK : ~57 jours d'autonomie.
    SeedAccount("prober", USERS["prober"], "PROBE", 90_000_000_001, 1_000_000),
    SeedAccount("probe_sink", PROBE_SINK_OWNER, "PROBE_SINK", 90_000_000_002, 0),
]
BANK_RESERVE = SeedAccount("bank", BANK_OWNER, BANK_RESERVE_LABEL, 1, 0)

log = structlog.get_logger()


def account_id(owner: UUID) -> UUID:
    return uuid5(_NAMESPACE, str(owner))


BANK_RESERVE_ID = account_id(BANK_OWNER)


def seed_account(name: str) -> SeedAccount:
    return next(a for a in SEED_ACCOUNTS if a.name == name)


def seed_iban(name: str) -> str:
    """IBAN en clair d'un compte du seed (démo et tests uniquement, jamais en base)."""
    return seed_account(name).iban


async def seed(s: AsyncSession, pseudo: Pseudonymizer) -> None:
    async with s.begin():
        rows = [
            {
                "id": account_id(a.owner),
                "owner_id": a.owner,
                "label": a.label,
                "iban_hash": pseudo.iban_hash(a.iban),
                "iban_masked": iban.mask(a.iban),
            }
            for a in [BANK_RESERVE, *SEED_ACCOUNTS]
        ]
        await s.execute(insert(Account).values(rows).on_conflict_do_nothing(index_elements=["id"]))

        opened = 0
        for a in SEED_ACCOUNTS:
            if a.opening_cents == 0:
                continue
            dst = account_id(a.owner)
            tx_id = await s.scalar(
                insert(Transaction)
                .values(
                    idempotency_key=f"seed:opening:{dst}",
                    owner_id=BANK_OWNER,
                    src_account=BANK_RESERVE_ID,
                    dst_account=dst,
                    dst_iban_masked=iban.mask(a.iban),
                    amount_cents=a.opening_cents,
                    status=STATUS_COMPLETED,
                    request_hash="seed",
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
                .returning(Transaction.id)
            )
            if tx_id is not None:
                s.add_all(
                    [
                        LedgerEntry(
                            tx_id=tx_id, account_id=BANK_RESERVE_ID, amount_cents=-a.opening_cents
                        ),
                        LedgerEntry(tx_id=tx_id, account_id=dst, amount_cents=a.opening_cents),
                    ]
                )
                opened += 1
    log.info("seed.done", accounts=len(SEED_ACCOUNTS), opened=opened)


if __name__ == "__main__":
    for a in SEED_ACCOUNTS:
        shown = iban.format_groups(a.iban)
        print(f"{a.name:10} {a.label:15} {shown}  {a.opening_cents / 100:>9.2f} €")
