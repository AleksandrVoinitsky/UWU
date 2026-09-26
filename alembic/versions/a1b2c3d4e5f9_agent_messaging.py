"""AI-агент: поля обмена сообщениями (author, agent_run_id, agent_enabled).

Revision ID: a1b2c3d4e5f9
Revises: a1b2c3d4e5f8
Create Date: 2026-10-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f9"
down_revision = "a1b2c3d4e5f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("author", sa.String(20), server_default="operator", nullable=False),
    )
    op.add_column(
        "messages",
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=True),
    )
    op.add_column(
        "chats",
        sa.Column("agent_enabled", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("chats", "agent_enabled")
    op.drop_column("messages", "agent_run_id")
    op.drop_column("messages", "author")
