"""Кассовые смены.

Revision ID: 8b9c0d1e2f3a
Revises: 7a8b9c0d1e2f
Create Date: 2026-09-21
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "8b9c0d1e2f3a"
down_revision = "7a8b9c0d1e2f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cash_shifts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kassa_id", sa.Integer(), sa.ForeignKey("kassy.id"), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("opening_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("closing_amount", sa.Numeric(14, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("cash_shifts")
