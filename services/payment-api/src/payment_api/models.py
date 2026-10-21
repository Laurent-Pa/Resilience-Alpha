"""Tables du schéma `payments`. Le solde n'est jamais stocké : SUM(ledger_entries)."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    Numeric,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from payment_api.domain.bic import DEFAULT_BIC

SCHEMA = "payments"

STATUS_COMPLETED = "COMPLETED"
STATUS_REJECTED = "REJECTED"

# Origine d'une opération. Déduite du rôle realm porté par le jeton, et non de l'UUID du
# compte émetteur : le jour où une seconde sonde apparaît, elle est classée correctement
# sans toucher au code. Sert à écarter le trafic synthétique de la vue admin.
INITIATED_BY_USER = "user"
INITIATED_BY_PROBER = "prober"
# À garder aligné avec la contrainte CHECK de `Transaction`. Permet d'exprimer « toutes
# les origines sauf X » en égalités : un `!=` sur la colonne de tête de
# `ix_transactions_initiated_created` ne sait pas utiliser l'index.
INITIATED_BY_VALUES = (INITIATED_BY_USER, INITIATED_BY_PROBER)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(unique=True)  # un seul compte par personne
    # L'IBAN n'est jamais stocké en clair : HMAC-SHA256 (recherche) + forme masquée.
    iban_hash: Mapped[str] = mapped_column(Text, unique=True)
    iban_masked: Mapped[str] = mapped_column(Text)
    bic: Mapped[str] = mapped_column(Text, default=DEFAULT_BIC, server_default=DEFAULT_BIC)
    label: Mapped[str] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(CHAR(3), default="EUR", server_default="EUR")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        CheckConstraint("status IN ('COMPLETED','REJECTED')", name="ck_transactions_status"),
        CheckConstraint("initiated_by IN ('user','prober')", name="ck_transactions_initiated_by"),
        Index("ix_transactions_owner_created", "owner_id", "created_at"),
        # La sonde écrit ~12 lignes/min et domine vite la table : sans cet index, écarter
        # son trafic obligerait à la parcourir pour servir une page de la vue admin.
        Index("ix_transactions_initiated_created", "initiated_by", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)
    owner_id: Mapped[UUID]
    src_account: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    dst_account: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    # IBAN saisi par l'émetteur, conservé masqué uniquement (pays + 4 derniers caractères).
    dst_iban_masked: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # euros, 2 décimales
    status: Mapped[str] = mapped_column(Text)
    # `server_default` ne couvre que les lignes antérieures à la migration 0002 ;
    # l'application renseigne toujours la valeur explicitement.
    initiated_by: Mapped[str] = mapped_column(
        Text, default=INITIATED_BY_USER, server_default=INITIATED_BY_USER
    )
    request_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tx_id: Mapped[UUID] = mapped_column(ForeignKey("transactions.id"), index=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
