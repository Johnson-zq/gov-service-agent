"""PostgreSQL / pgvector projection store (F06)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    delete,
    insert,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from gov_service_agent.retrieval.types import (
    ELIGIBILITY_SCOPE_ONLINE,
    EXPECTED_EMBEDDING_DIMENSION,
    INDEX_NAME,
)

_store_metadata = MetaData()

semantic_retrieval_index_meta = Table(
    "semantic_retrieval_index_meta",
    _store_metadata,
    Column("projection_key", String, primary_key=True),
    Column("index_name", String, nullable=False),
    Column("provider_name", String, nullable=False),
    Column("model_id", String, nullable=False),
    Column("embedding_dimension", Integer, nullable=False),
    Column("projection_version", String, nullable=False),
    Column("policy_version", String, nullable=False),
    Column("document_count", Integer, nullable=False),
    Column("status", String, nullable=False),
    Column("built_at", DateTime(timezone=True), nullable=False),
)

semantic_retrieval_document = Table(
    "semantic_retrieval_document",
    _store_metadata,
    Column("projection_key", String, primary_key=True),
    Column("business_id", String, primary_key=True),
    Column("display_name", String, nullable=False),
    Column("direction", String, nullable=False),
    Column("retrieval_text", String, nullable=False),
    Column("eligibility_scope", String, nullable=False),
    Column("source_data_version", Integer, nullable=False),
    Column("source_fingerprint", String, nullable=False),
    Column("embedding", Vector(EXPECTED_EMBEDDING_DIMENSION), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


@dataclass(frozen=True, slots=True)
class ProjectionMetaRow:
    projection_key: str
    index_name: str
    provider_name: str
    model_id: str
    embedding_dimension: int
    projection_version: str
    policy_version: str
    document_count: int
    status: str
    built_at: datetime


@dataclass(frozen=True, slots=True)
class VectorSearchHit:
    business_id: str
    display_name: str
    direction: str
    eligibility_scope: str
    distance: float


@dataclass(frozen=True, slots=True)
class DocumentWriteRow:
    business_id: str
    display_name: str
    direction: str
    retrieval_text: str
    source_data_version: int
    source_fingerprint: str
    embedding: list[float]


class ProjectionStore:
    """Persistence and exact cosine search for semantic retrieval projection."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def check_connectivity(self) -> bool:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False

    def load_ready_meta(self, projection_key: str) -> ProjectionMetaRow | None:
        stmt = select(semantic_retrieval_index_meta).where(
            semantic_retrieval_index_meta.c.projection_key == projection_key,
            semantic_retrieval_index_meta.c.status == "READY",
        )
        with self._engine.connect() as connection:
            row = connection.execute(stmt).mappings().first()
        if row is None:
            return None
        return ProjectionMetaRow(
            projection_key=row["projection_key"],
            index_name=row["index_name"],
            provider_name=row["provider_name"],
            model_id=row["model_id"],
            embedding_dimension=int(row["embedding_dimension"]),
            projection_version=row["projection_version"],
            policy_version=row["policy_version"],
            document_count=int(row["document_count"]),
            status=row["status"],
            built_at=row["built_at"],
        )

    def search(
        self,
        *,
        projection_key: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[VectorSearchHit]:
        if limit < 1:
            return []
        distance = semantic_retrieval_document.c.embedding.cosine_distance(
            list(query_embedding)
        )
        stmt = (
            select(
                semantic_retrieval_document.c.business_id,
                semantic_retrieval_document.c.display_name,
                semantic_retrieval_document.c.direction,
                semantic_retrieval_document.c.eligibility_scope,
                distance.label("distance"),
            )
            .where(
                semantic_retrieval_document.c.projection_key == projection_key,
                semantic_retrieval_document.c.eligibility_scope
                == ELIGIBILITY_SCOPE_ONLINE,
            )
            .order_by(distance)
            .limit(limit)
        )
        with self._engine.connect() as connection:
            rows = connection.execute(stmt).mappings().all()
        return [
            VectorSearchHit(
                business_id=row["business_id"],
                display_name=row["display_name"],
                direction=row["direction"],
                eligibility_scope=row["eligibility_scope"],
                distance=float(row["distance"]),
            )
            for row in rows
        ]

    def replace_projection(
        self,
        *,
        projection_key: str,
        provider_name: str,
        model_id: str,
        embedding_dimension: int,
        projection_version: str,
        policy_version: str,
        documents: Sequence[DocumentWriteRow],
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._engine.begin() as connection:
            connection.execute(delete(semantic_retrieval_document))
            connection.execute(delete(semantic_retrieval_index_meta))
            if documents:
                connection.execute(
                    insert(semantic_retrieval_document),
                    [
                        {
                            "projection_key": projection_key,
                            "business_id": doc.business_id,
                            "display_name": doc.display_name,
                            "direction": doc.direction,
                            "retrieval_text": doc.retrieval_text,
                            "eligibility_scope": ELIGIBILITY_SCOPE_ONLINE,
                            "source_data_version": doc.source_data_version,
                            "source_fingerprint": doc.source_fingerprint,
                            "embedding": doc.embedding,
                            "updated_at": now,
                        }
                        for doc in documents
                    ],
                )
            connection.execute(
                insert(semantic_retrieval_index_meta).values(
                    projection_key=projection_key,
                    index_name=INDEX_NAME,
                    provider_name=provider_name,
                    model_id=model_id,
                    embedding_dimension=embedding_dimension,
                    projection_version=projection_version,
                    policy_version=policy_version,
                    document_count=len(documents),
                    status="READY",
                    built_at=now,
                )
            )
