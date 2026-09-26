"""Фирма (юрлицо) в движениях денег и взаиморасчётов (многофирменный учёт).

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-09-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "money_movements",
        sa.Column("firma_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "settlement_movements",
        sa.Column("firma_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_money_movements_firma_id", "money_movements", "firmy", ["firma_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_settlement_movements_firma_id",
        "settlement_movements",
        "firmy",
        ["firma_id"],
        ["id"],
    )
    op.create_index(
        "ix_money_movements_firma_id", "money_movements", ["firma_id"], unique=False
    )
    op.create_index(
        "ix_settlement_movements_firma_id",
        "settlement_movements",
        ["firma_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_settlement_movements_firma_id", table_name="settlement_movements")
    op.drop_index("ix_money_movements_firma_id", table_name="money_movements")
    op.drop_constraint(
        "fk_settlement_movements_firma_id", "settlement_movements", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_money_movements_firma_id", "money_movements", type_="foreignkey"
    )
    op.drop_column("settlement_movements", "firma_id")
    op.drop_column("money_movements", "firma_id")
