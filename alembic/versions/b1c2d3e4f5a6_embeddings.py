"""Семантический поиск: эмбеддинги номенклатуры (pgvector).

Создаёт расширение ``vector`` и таблицу ``nomenklatura_embeddings`` (векторное
представление текста товара для RAG-поиска ``/api/agent/search_semantic``).

Требуется образ PostgreSQL с pgvector (``pgvector/pgvector:pg16``) — обычный
``postgres``-образ не содержит расширение.

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f9
Create Date: 2026-10-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "b1c2d3e4f5a6"
down_revision = "a1b2c3d4e5f9"
branch_labels = None
depends_on = None

# Размерность вектора (совпадает с app.models.embeddings.EMBEDDING_DIM).
EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "nomenklatura_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nomenklatura_id", sa.Integer(), sa.ForeignKey("nomenklatura.id"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_nomenklatura_embeddings_nomenklatura_id",
        "nomenklatura_embeddings",
        ["nomenklatura_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_nomenklatura_embeddings_nomenklatura_id", table_name="nomenklatura_embeddings")
    op.drop_table("nomenklatura_embeddings")
