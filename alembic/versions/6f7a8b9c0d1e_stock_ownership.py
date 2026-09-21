"""Раздельный учёт товара (ownership в партиях).

Revision ID: 6f7a8b9c0d1e
Revises: 5e6f7a8b9c0d
Create Date: 2026-09-21
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "6f7a8b9c0d1e"
down_revision = "5e6f7a8b9c0d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_batches", sa.Column("ownership", sa.String(20), nullable=False, server_default="own"))


def downgrade() -> None:
    op.drop_column("stock_batches", "ownership")
