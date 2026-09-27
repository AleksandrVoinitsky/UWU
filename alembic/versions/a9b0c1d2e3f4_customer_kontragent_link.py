"""Покупатель ↔ контрагент: связь аккаунта с контрагентом учёта.

Добавляет ``customers.kontragent_id`` — явную связь аккаунта покупателя с
контрагентом (``kontragenty``). Контрагент = аккаунт по номеру телефона; заказы и
продажи оформляются на контрагента.

Revision ID: a9b0c1d2e3f4
Revises: f7a8b9c0d1e2
Create Date: 2026-10-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a9b0c1d2e3f4"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column("kontragent_id", sa.Integer(), sa.ForeignKey("kontragenty.id"), nullable=True),
    )
    op.create_index("ix_customers_kontragent_id", "customers", ["kontragent_id"])


def downgrade() -> None:
    op.drop_index("ix_customers_kontragent_id", table_name="customers")
    op.drop_column("customers", "kontragent_id")
