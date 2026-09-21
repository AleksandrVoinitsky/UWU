"""Добавить цены номенклатуры (закупочная и свободная розничная).

Revision ID: 2a1b3c4d5e6f
Revises: 747d56ea4efc
Create Date: 2026-09-21
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "2a1b3c4d5e6f"
down_revision = "747d56ea4efc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nomenklatura", sa.Column("purchase_price", sa.Numeric(14, 2), nullable=True))
    op.add_column("nomenklatura", sa.Column("retail_price", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("nomenklatura", "retail_price")
    op.drop_column("nomenklatura", "purchase_price")
