"""AI-агент: полное удаление механики одобрения (human-in-the-loop).

Агент собирает заказы и консультирует полностью самостоятельно — участие человека
не требуется. Удаляется таблица ``agent_approvals`` (очередь одобрений) и колонки
``approval_policy``/``approval_threshold_amount`` из ``agent_tools`` (политика
одобрения больше не применяется).

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-10-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("agent_tools", "approval_threshold_amount")
    op.drop_column("agent_tools", "approval_policy")
    op.drop_table("agent_approvals")


def downgrade() -> None:
    op.add_column("agent_tools", sa.Column("approval_policy", sa.String(20), nullable=True))
    op.add_column(
        "agent_tools", sa.Column("approval_threshold_amount", sa.Numeric(14, 2), nullable=True)
    )
    op.create_table(
        "agent_approvals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("chat_id", sa.Integer(), sa.ForeignKey("chats.id"), nullable=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("tool_key", sa.String(80), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("decided_by", sa.String(120), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resume_value", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
