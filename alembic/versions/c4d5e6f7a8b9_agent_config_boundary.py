"""AI-агент: граница конфигурации — модель LLM уходит в env сервиса агента.

Убирает из ``agent_prompt_versions`` колонки ``model``/``temperature``/``max_tokens``
(параметры LLM задаются переменными окружения отдельного сервиса ``uwu-ai-agent``,
а не в админке ядра) и включает автоответ агента по умолчанию для новых чатов
(``chats.agent_enabled`` server_default ``true``).

Revision ID: c4d5e6f7a8b9
Revises: b1c2d3e4f5a6
Create Date: 2026-10-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("agent_prompt_versions", "max_tokens")
    op.drop_column("agent_prompt_versions", "temperature")
    op.drop_column("agent_prompt_versions", "model")
    op.alter_column(
        "chats",
        "agent_enabled",
        existing_type=sa.Boolean(),
        server_default=sa.text("true"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "chats",
        "agent_enabled",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )
    op.add_column("agent_prompt_versions", sa.Column("model", sa.String(120), nullable=True))
    op.add_column("agent_prompt_versions", sa.Column("temperature", sa.Float(), nullable=True))
    op.add_column("agent_prompt_versions", sa.Column("max_tokens", sa.Integer(), nullable=True))
