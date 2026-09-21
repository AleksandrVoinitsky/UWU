"""Режим цены номенклатуры (свободная / по виду цен).

Revision ID: 3c4d5e6f7a8b
Revises: 2a1b3c4d5e6f
Create Date: 2026-09-21
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "3c4d5e6f7a8b"
down_revision = "2a1b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nomenklatura", sa.Column("price_mode", sa.String(10), nullable=False, server_default="free"))
    op.add_column("nomenklatura", sa.Column("tip_tsen_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_nomenklatura_tip_tsen", "nomenklatura", "tipy_tsen", ["tip_tsen_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_nomenklatura_tip_tsen", "nomenklatura", type_="foreignkey")
    op.drop_column("nomenklatura", "tip_tsen_id")
    op.drop_column("nomenklatura", "price_mode")
