"""Изображение товара.

Revision ID: 0d1e2f3a4b5c
Revises: 9c0d1e2f3a4b
Create Date: 2026-09-21
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0d1e2f3a4b5c"
down_revision = "9c0d1e2f3a4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nomenklatura", sa.Column("image_path", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("nomenklatura", "image_path")
