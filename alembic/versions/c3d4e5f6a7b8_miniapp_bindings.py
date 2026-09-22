"""MiniApp: привязка аккаунтов мессенджеров к покупателям.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_bindings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_customer_bindings_customer_id", "customer_bindings", ["customer_id"])
    op.create_index(
        "ix_customer_bindings_channel_external",
        "customer_bindings",
        ["channel", "external_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("customer_bindings")
