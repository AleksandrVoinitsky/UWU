"""Привязка чата к покупателю интернет-магазина.

Добавляет колонку ``chats.customer_id`` для чата «сайт» (покупатель ↔ продавец),
чтобы сообщения покупателя отображались в чате продавца с именем покупателя.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-23
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chats",
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
    )
    op.create_index("ix_chats_customer_id", "chats", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_chats_customer_id", table_name="chats")
    op.drop_column("chats", "customer_id")
