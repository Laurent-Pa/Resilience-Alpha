"""Schéma initial : comptes, transactions, écritures.

Revision ID: 0001
Revises:
Create Date: 2026-10-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "payments"
DEFAULT_BIC = "RSALFRP0XXX"  # figé ici : une migration ne doit pas dépendre du code applicatif


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("iban_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("iban_masked", sa.Text(), nullable=False),
        sa.Column("bic", sa.Text(), nullable=False, server_default=DEFAULT_BIC),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False, server_default="EUR"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema=SCHEMA,
    )
    # Un seul compte par personne : le compte débité se déduit du jeton.
    op.create_index("ux_accounts_owner_id", "accounts", ["owner_id"], unique=True, schema=SCHEMA)

    op.create_table(
        "transactions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("src_account", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.accounts.id"), nullable=False),
        sa.Column("dst_account", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.accounts.id"), nullable=False),
        sa.Column("dst_iban_masked", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        sa.CheckConstraint("status IN ('COMPLETED','REJECTED')", name="ck_transactions_status"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_transactions_owner_created",
        "transactions",
        ["owner_id", sa.text("created_at DESC")],
        schema=SCHEMA,
    )

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("tx_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.transactions.id"), nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.accounts.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_ledger_entries_account_id", "ledger_entries", ["account_id"], schema=SCHEMA)
    op.create_index("ix_ledger_entries_tx_id", "ledger_entries", ["tx_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("ledger_entries", schema=SCHEMA)
    op.drop_table("transactions", schema=SCHEMA)
    op.drop_table("accounts", schema=SCHEMA)
