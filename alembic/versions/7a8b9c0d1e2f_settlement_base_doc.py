"""Основание платежа в движениях взаиморасчётов.

Revision ID: 7a8b9c0d1e2f
Revises: 6f7a8b9c0d1e
Create Date: 2026-09-21
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "7a8b9c0d1e2f"
down_revision = "6f7a8b9c0d1e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("settlement_movements", sa.Column("base_document_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_settlement_base_doc", "settlement_movements", "documents", ["base_document_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_settlement_base_doc", "settlement_movements", type_="foreignkey")
    op.drop_column("settlement_movements", "base_document_id")
