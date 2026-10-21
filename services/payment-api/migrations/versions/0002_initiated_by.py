"""Origine d'une opération : colonne `initiated_by` sur transactions.

Permet à la vue admin d'écarter le trafic synthétique de la sonde.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SCHEMA = "payments"
# Figés ici : une migration ne doit pas dépendre du code applicatif.
INITIATED_BY_USER = "user"
INITIATED_BY_PROBER = "prober"
# Compte de service du client Keycloak `prober` (cf. payment_api.seed.USERS).
PROBER_OWNER_ID = "55555555-5555-4555-8555-555555555555"


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("initiated_by", sa.Text(), nullable=False, server_default=INITIATED_BY_USER),
        schema=SCHEMA,
    )

    # Rattrapage de l'historique : les lignes déjà en base n'ont pas de rôle associé.
    # Seul l'émetteur peut encore les départager, d'où l'UUID du compte de service.
    op.execute(
        f"UPDATE {SCHEMA}.transactions "
        f"SET initiated_by = '{INITIATED_BY_PROBER}' "
        f"WHERE owner_id = '{PROBER_OWNER_ID}'::uuid"
    )

    op.create_check_constraint(
        "ck_transactions_initiated_by",
        "transactions",
        f"initiated_by IN ('{INITIATED_BY_USER}','{INITIATED_BY_PROBER}')",
        schema=SCHEMA,
    )
    # La sonde domine vite la table : cet index évite de parcourir son trafic pour
    # servir une page de la vue admin, et sert aussi l'agrégation par minute.
    op.create_index(
        "ix_transactions_initiated_created",
        "transactions",
        ["initiated_by", sa.text("created_at DESC")],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_initiated_created", table_name="transactions", schema=SCHEMA)
    op.drop_constraint("ck_transactions_initiated_by", "transactions", schema=SCHEMA, type_="check")
    op.drop_column("transactions", "initiated_by", schema=SCHEMA)
