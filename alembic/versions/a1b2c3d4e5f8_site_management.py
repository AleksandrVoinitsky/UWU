"""Управление сайтом/MiniApp: публикация товаров, настройки сайта, акции.

Revision ID: a1b2c3d4e5f8
Revises: a1b2c3d4e5f7
Create Date: 2026-09-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "a1b2c3d4e5f8"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "nomenklatura",
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "site_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_site_settings_key", "site_settings", ["key"], unique=True)

    op.create_table(
        "promotions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("discount_type", sa.String(20), nullable=False),
        sa.Column("value", sa.Numeric(14, 2), nullable=False),
        sa.Column("nomenklatura_id", sa.Integer(), sa.ForeignKey("nomenklatura.id"), nullable=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("starts_at", sa.Date(), nullable=True),
        sa.Column("ends_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("promotions")
    op.drop_index("ix_site_settings_key", table_name="site_settings")
    op.drop_table("site_settings")
    op.drop_column("nomenklatura", "is_published")
