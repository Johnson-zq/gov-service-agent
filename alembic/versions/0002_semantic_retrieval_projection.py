"""Semantic retrieval projection tables (pgvector).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-03

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE semantic_retrieval_index_meta (
            projection_key TEXT PRIMARY KEY,
            index_name TEXT NOT NULL,
            provider_name TEXT NOT NULL,
            model_id TEXT NOT NULL,
            embedding_dimension INTEGER NOT NULL,
            projection_version TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            document_count INTEGER NOT NULL,
            status TEXT NOT NULL,
            built_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT semantic_retrieval_index_meta_dim_chk
                CHECK (embedding_dimension = 768),
            CONSTRAINT semantic_retrieval_index_meta_count_chk
                CHECK (document_count >= 0),
            CONSTRAINT semantic_retrieval_index_meta_status_chk
                CHECK (status = 'READY')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE semantic_retrieval_document (
            projection_key TEXT NOT NULL,
            business_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            direction TEXT NOT NULL,
            retrieval_text TEXT NOT NULL,
            eligibility_scope TEXT NOT NULL,
            source_data_version INTEGER NOT NULL,
            source_fingerprint TEXT NOT NULL,
            embedding vector(768) NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (projection_key, business_id),
            CONSTRAINT semantic_retrieval_document_scope_chk
                CHECK (eligibility_scope = 'ONLINE')
        )
        """
    )


def downgrade() -> None:
    # Derived projection only; do not DROP EXTENSION vector.
    op.execute("DROP TABLE IF EXISTS semantic_retrieval_document")
    op.execute("DROP TABLE IF EXISTS semantic_retrieval_index_meta")
