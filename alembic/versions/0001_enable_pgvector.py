"""Enable pgvector extension.

Revision ID: 0001
Revises:
Create Date: 2026-09-02

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Intentional no-op: vector extension is treated as infrastructure capability.
    # Do not DROP EXTENSION (and never CASCADE).
    pass
