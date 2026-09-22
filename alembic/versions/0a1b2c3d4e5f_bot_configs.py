"""Боты мессенджеров: конфигурация и external_id для чатов.

Revision ID: 0a1b2c3d4e5f
Revises: 1e2f3a4b5c6d
Create Date: 2026-09-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0a1b2c3d4e5f"
down_revision = "1e2f3a4b5c6d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chats",
        sa.Column("external_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_chats_external_id", "chats", ["external_id"])

    op.create_table(
        "bot_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("token", sa.String(512), nullable=True),
        sa.Column("name", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bot_configs_channel", "bot_configs", ["channel"], unique=True)


def downgrade() -> None:
    op.drop_table("bot_configs")
    op.drop_index("ix_chats_external_id", table_name="chats")
    op.drop_column("chats", "external_id")
