"""Бухгалтерские проводки.

Revision ID: 5e6f7a8b9c0d
Revises: 4d5e6f7a8b9c
Create Date: 2026-09-21
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "5e6f7a8b9c0d"
down_revision = "4d5e6f7a8b9c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounting_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("account_debit", sa.String(20), nullable=False),
        sa.Column("account_credit", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("nomenklatura_id", sa.Integer(), sa.ForeignKey("nomenklatura.id"), nullable=True),
        sa.Column("kontragent_id", sa.Integer(), sa.ForeignKey("kontragenty.id"), nullable=True),
    )
    op.create_index("ix_accounting_entries_document_id", "accounting_entries", ["document_id"])
    op.create_index("ix_accounting_entries_date", "accounting_entries", ["date"])


def downgrade() -> None:
    op.drop_table("accounting_entries")
