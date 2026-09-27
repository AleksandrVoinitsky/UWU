"""chat unique channel external

Revision ID: 50ca465f83fc
Revises: a9b0c1d2e3f4
Create Date: 2026-09-27 20:10:07.324493
"""
from __future__ import annotations

from alembic import op

revision = "50ca465f83fc"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Один внешний чат на (канал, external_id) — защита от дублей при гонке
    # параллельного первого сообщения. NULL external_id (чаты сайта) не
    # конфликтуют (в PostgreSQL несколько NULL допустимы).
    op.create_unique_constraint(
        "uq_chats_channel_external", "chats", ["channel", "external_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_chats_channel_external", "chats", type_="unique")
