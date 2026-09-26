"""Расширяет колонку customers.phone до 64 символов.

Синтетический телефон MiniApp ``ma_<channel>_<external_id>`` (например,
``ma_telegram_279058397``) не помещался в VARCHAR(20), из-за чего первый вход
через Telegram падал с «value too long for type character varying(20)».

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-23
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "customers",
        "phone",
        existing_type=sa.String(20),
        type_=sa.String(64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "customers",
        "phone",
        existing_type=sa.String(64),
        type_=sa.String(20),
        existing_nullable=False,
    )
