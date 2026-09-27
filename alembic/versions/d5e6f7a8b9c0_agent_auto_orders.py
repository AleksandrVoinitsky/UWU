"""AI-агент: сбор заказов без одобрения (approval_policy → auto).

Агент только собирает заказы и корзину, не проводит продажи, поэтому
human-in-the-loop одобрение для ``add_to_cart``/``create_order`` убрано:
политика меняется на ``auto``, порог суммы сбрасывается. Документ по-прежнему
создаётся в статусе ``DRAFT`` (проведение остаётся за оператором).

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-06
"""
from __future__ import annotations

from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE agent_tools SET approval_policy = 'auto', approval_threshold_amount = NULL "
        "WHERE key IN ('add_to_cart', 'create_order')"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE agent_tools SET approval_policy = 'threshold', approval_threshold_amount = 10000 "
        "WHERE key = 'add_to_cart'"
    )
    op.execute(
        "UPDATE agent_tools SET approval_policy = 'always', approval_threshold_amount = NULL "
        "WHERE key = 'create_order'"
    )
