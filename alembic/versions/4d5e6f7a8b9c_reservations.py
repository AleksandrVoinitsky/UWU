"""Резервирование товара.

Revision ID: 4d5e6f7a8b9c
Revises: 3c4d5e6f7a8b
Create Date: 2026-09-21
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "4d5e6f7a8b9c"
down_revision = "3c4d5e6f7a8b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reservations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nomenklatura_id", sa.Integer(), sa.ForeignKey("nomenklatura.id"), nullable=False),
        sa.Column("sklad_id", sa.Integer(), sa.ForeignKey("sklady.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("zakaz_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_reservations_nomenklatura_id", "reservations", ["nomenklatura_id"])
    op.create_index("ix_reservations_sklad_id", "reservations", ["sklad_id"])


def downgrade() -> None:
    op.drop_table("reservations")
