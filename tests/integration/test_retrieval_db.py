"""F06 retrieval projection DB integration (Fake provider; gov_service_agent_test only)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.retrieval.admission import (
    build_retrieval_text,
    compute_projection_key,
)
from gov_service_agent.retrieval.builder import ProjectionRebuildError, rebuild_projection
from gov_service_agent.retrieval.service import SemanticRetrievalService
from gov_service_agent.retrieval.store import DocumentWriteRow, ProjectionStore
from gov_service_agent.retrieval.types import (
    EXPECTED_EMBEDDING_DIMENSION,
    POLICY_VERSION,
    PROJECTION_VERSION,
    RetrievalStatus,
)
from gov_service_agent.settings import Settings
from tests.test_embedding import FakeEmbeddingProvider, make_test_vector

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"
_REQUIRED_TEST_DATABASE = "gov_service_agent_test"
_DEMO_PATH = _REPO_ROOT / "data" / "demo" / "demo_ss_001.json"
_POLICY_PATH = _REPO_ROOT / "data" / "retrieval" / "f06_online_eligibility.json"
_PROVIDER = "LOCAL_SENTENCE_TRANSFORMER"
_MODEL_ID = "fake-model"


def _validate_test_database_url(test_url: str) -> None:
    parsed = make_url(test_url)
    if parsed.drivername != "postgresql+psycopg":
        pytest.fail(
            "TEST_DATABASE_URL driver must be postgresql+psycopg "
            f"(got {parsed.drivername!r})"
        )
    if parsed.database != _REQUIRED_TEST_DATABASE:
        pytest.fail(
            "TEST_DATABASE_URL database must be "
            f"{_REQUIRED_TEST_DATABASE!r} (got {parsed.database!r})"
        )


def _require_test_url() -> str:
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url or not test_url.strip():
        # Match F05: absent URL → skip in default/no-docker runs.
        # When URL is present, guard + connectivity failures must FAIL.
        pytest.skip("TEST_DATABASE_URL is not set")
    _validate_test_database_url(test_url)
    return test_url


def _alembic_cfg(test_url: str) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", test_url)
    cfg.attributes["configure_logger"] = False
    return cfg


def _engine(test_url: str):
    return create_engine(test_url)


def _table_exists(database_url: str, table_name: str) -> bool:
    engine = _engine(database_url)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = :name"
                ),
                {"name": table_name},
            ).first()
            return row is not None
    finally:
        engine.dispose()


def _vector_extension_exists(database_url: str) -> bool:
    engine = _engine(database_url)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ).first()
            return row is not None
    finally:
        engine.dispose()


def _embedding_udt(database_url: str) -> str | None:
    engine = _engine(database_url)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT format_type(a.atttypid, a.atttypmod) "
                    "FROM pg_attribute a "
                    "JOIN pg_class c ON a.attrelid = c.oid "
                    "JOIN pg_namespace n ON c.relnamespace = n.oid "
                    "WHERE n.nspname = 'public' "
                    "AND c.relname = 'semantic_retrieval_document' "
                    "AND a.attname = 'embedding' "
                    "AND a.attnum > 0 AND NOT a.attisdropped"
                )
            ).first()
            return None if row is None else str(row[0])
    finally:
        engine.dispose()


def _configured_settings(**overrides: object) -> Settings:
    payload = {
        "embedding_provider": _PROVIDER,
        "embedding_model_id": _MODEL_ID,
        "embedding_model_path": "unused-path",
        "embedding_device": "cpu",
        "retrieval_top_k": 5,
        "retrieval_min_score": 0.50,
        "_env_file": None,
    }
    payload.update(overrides)
    return Settings(**payload)  # type: ignore[arg-type]


def _projection_key() -> str:
    return compute_projection_key(
        provider_name=_PROVIDER,
        model_id=_MODEL_ID,
        dimension=EXPECTED_EMBEDDING_DIMENSION,
        projection_version=PROJECTION_VERSION,
        policy_version=POLICY_VERSION,
    )


def _demo_repo() -> JsonBusinessRepository:
    return JsonBusinessRepository.from_paths([_DEMO_PATH])


def _fake_provider_for_demo() -> FakeEmbeddingProvider:
    from gov_service_agent.business_data.models import load_snapshot

    snapshot = load_snapshot(_DEMO_PATH)
    text_value = build_retrieval_text(snapshot)
    return FakeEmbeddingProvider(
        model_id=_MODEL_ID,
        vectors_by_text={text_value: make_test_vector(1)},
    )


@pytest.fixture
def test_db():
    test_url = _require_test_url()
    engine = _engine(test_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        pytest.fail(f"TEST_DATABASE_URL unreachable: {type(exc).__name__}")
    cfg = _alembic_cfg(test_url)
    command.upgrade(cfg, "0002")
    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM semantic_retrieval_document"))
            connection.execute(text("DELETE FROM semantic_retrieval_index_meta"))
        yield test_url, engine
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM semantic_retrieval_document"))
            connection.execute(text("DELETE FROM semantic_retrieval_index_meta"))
        engine.dispose()


@pytest.mark.integration
def test_migration_0001_to_0002_and_schema() -> None:
    test_url = _require_test_url()
    cfg = _alembic_cfg(test_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "0001")
    assert _vector_extension_exists(test_url)
    assert not _table_exists(test_url, "semantic_retrieval_index_meta")
    assert not _table_exists(test_url, "semantic_retrieval_document")

    command.upgrade(cfg, "0002")
    assert _vector_extension_exists(test_url)
    assert _table_exists(test_url, "semantic_retrieval_index_meta")
    assert _table_exists(test_url, "semantic_retrieval_document")
    assert _embedding_udt(test_url) == "vector(768)"

    # No business fact tables from 0002.
    for name in (
        "business",
        "material",
        "location",
        "channel",
        "rule",
    ):
        assert not _table_exists(test_url, name)

    # No ANN indexes.
    engine = _engine(test_url)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' "
                    "AND (indexdef ILIKE '%hnsw%' OR indexdef ILIKE '%ivfflat%')"
                )
            ).all()
            assert rows == []
    finally:
        engine.dispose()


@pytest.mark.integration
def test_migration_round_trip_preserves_vector_extension() -> None:
    test_url = _require_test_url()
    cfg = _alembic_cfg(test_url)
    command.upgrade(cfg, "0001")
    command.upgrade(cfg, "0002")
    assert _table_exists(test_url, "semantic_retrieval_document")
    command.downgrade(cfg, "0001")
    assert not _table_exists(test_url, "semantic_retrieval_document")
    assert not _table_exists(test_url, "semantic_retrieval_index_meta")
    assert _vector_extension_exists(test_url)
    command.upgrade(cfg, "0002")
    assert _table_exists(test_url, "semantic_retrieval_document")
    assert _vector_extension_exists(test_url)


@pytest.mark.integration
def test_built_empty_not_index_missing(test_db) -> None:  # type: ignore[no-untyped-def]
    test_url, engine = test_db
    key = _projection_key()
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO semantic_retrieval_index_meta ("
                "projection_key, index_name, provider_name, model_id, "
                "embedding_dimension, projection_version, policy_version, "
                "document_count, status, built_at"
                ") VALUES ("
                ":projection_key, 'business_intent', :provider_name, :model_id, "
                "768, :projection_version, :policy_version, 0, 'READY', :built_at)"
            ),
            {
                "projection_key": key,
                "provider_name": _PROVIDER,
                "model_id": _MODEL_ID,
                "projection_version": PROJECTION_VERSION,
                "policy_version": POLICY_VERSION,
                "built_at": now,
            },
        )
    provider = FakeEmbeddingProvider(model_id=_MODEL_ID)
    store = ProjectionStore(engine)
    service = SemanticRetrievalService(
        settings=_configured_settings(),
        provider=provider,
        store=store,
    )
    result = service.retrieve("交社保")
    assert result.status == RetrievalStatus.NO_USABLE_CANDIDATE
    assert provider.embed_query_calls == 0
    assert test_url  # keep guard context referenced


@pytest.mark.integration
def test_projection_key_filtering_and_cosine_ranking(test_db) -> None:  # type: ignore[no-untyped-def]
    _test_url, engine = test_db
    key = _projection_key()
    foreign_key = "foreign-" + key[:16]
    now = datetime.now(timezone.utc)
    store = ProjectionStore(engine)
    # Current projection: B closer to query axis-1 than A
    current_docs = [
        DocumentWriteRow(
            business_id="NEAR",
            display_name="near",
            direction="social_security",
            retrieval_text="near",
            source_data_version=1,
            source_fingerprint="fp-near",
            embedding=make_test_vector(1),
        ),
        DocumentWriteRow(
            business_id="FAR",
            display_name="far",
            direction="other",
            retrieval_text="far",
            source_data_version=1,
            source_fingerprint="fp-far",
            embedding=make_test_vector(50),
        ),
    ]
    store.replace_projection(
        projection_key=key,
        provider_name=_PROVIDER,
        model_id=_MODEL_ID,
        embedding_dimension=768,
        projection_version=PROJECTION_VERSION,
        policy_version=POLICY_VERSION,
        documents=current_docs,
    )
    # Insert a foreign projection row that would be "closer" if not filtered.
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO semantic_retrieval_document ("
                "projection_key, business_id, display_name, direction, "
                "retrieval_text, eligibility_scope, source_data_version, "
                "source_fingerprint, embedding, updated_at"
                ") VALUES ("
                ":projection_key, 'FOREIGN_NEAR', 'foreign', 'other', 'x', "
                "'ONLINE', 1, 'fp-f', :embedding, :updated_at)"
            ),
            {
                "projection_key": foreign_key,
                "embedding": make_test_vector(1, 2),
                "updated_at": now,
            },
        )

    hits = store.search(
        projection_key=key,
        query_embedding=make_test_vector(1),
        limit=10,
    )
    assert [h.business_id for h in hits] == ["NEAR", "FAR"]
    assert hits[0].distance < hits[1].distance
    score0 = 1.0 - hits[0].distance
    score1 = 1.0 - hits[1].distance
    assert score0 > score1
    assert all(h.business_id != "FOREIGN_NEAR" for h in hits)


@pytest.mark.integration
def test_threshold_and_top_k(test_db) -> None:  # type: ignore[no-untyped-def]
    _test_url, engine = test_db
    key = _projection_key()
    store = ProjectionStore(engine)
    docs = [
        DocumentWriteRow(
            business_id=f"ID_{i}",
            display_name=f"n{i}",
            direction="d",
            retrieval_text=f"t{i}",
            source_data_version=1,
            source_fingerprint=f"fp{i}",
            embedding=make_test_vector(i),
        )
        for i in range(1, 8)
    ]
    store.replace_projection(
        projection_key=key,
        provider_name=_PROVIDER,
        model_id=_MODEL_ID,
        embedding_dimension=768,
        projection_version=PROJECTION_VERSION,
        policy_version=POLICY_VERSION,
        documents=docs,
    )
    query = "q"
    # Query equals vector index 1 → ID_1 highest.
    provider = FakeEmbeddingProvider(
        model_id=_MODEL_ID,
        vectors_by_text={query: make_test_vector(1)},
    )
    service = SemanticRetrievalService(
        settings=_configured_settings(retrieval_top_k=3, retrieval_min_score=0.0),
        provider=provider,
        store=store,
    )
    result = service.retrieve(query)
    assert result.status == RetrievalStatus.CANDIDATES
    assert len(result.candidates) == 3
    assert result.candidates[0].business_id == "ID_1"

    # Boundary: score == threshold is included (>=).
    # Force a known distance via identical vectors → score ~= 1.0
    # Boundary: score == configured threshold is included (>=).
    service2 = SemanticRetrievalService(
        settings=_configured_settings(retrieval_top_k=5, retrieval_min_score=1.0),
        provider=provider,
        store=store,
    )
    result2 = service2.retrieve(query)
    assert result2.status == RetrievalStatus.CANDIDATES
    assert result2.candidates[0].score == pytest.approx(1.0)
    assert all(c.score >= 1.0 for c in result2.candidates)

    service3 = SemanticRetrievalService(
        settings=_configured_settings(retrieval_top_k=5, retrieval_min_score=0.999),
        provider=provider,
        store=store,
    )
    result3 = service3.retrieve(query)
    assert result3.status == RetrievalStatus.CANDIDATES
    assert all(c.score >= 0.999 for c in result3.candidates)


@pytest.mark.integration
def test_atomic_rebuild_rollback(test_db) -> None:  # type: ignore[no-untyped-def]
    _test_url, engine = test_db
    store = ProjectionStore(engine)
    provider = _fake_provider_for_demo()
    key = rebuild_projection(
        repository=_demo_repo(),
        store=store,
        provider=provider,
        policy_path=_POLICY_PATH,
    )
    with engine.connect() as connection:
        before_docs = connection.execute(
            text("SELECT count(*) FROM semantic_retrieval_document")
        ).scalar_one()
        before_meta = connection.execute(
            text(
                "SELECT projection_key FROM semantic_retrieval_index_meta "
                "WHERE status = 'READY'"
            )
        ).scalar_one()
    assert before_docs == 1
    assert before_meta == key

    # Constraint failure mid-replace must roll back; old READY remains.
    bad_docs = [
        DocumentWriteRow(
            business_id="X",
            display_name="x",
            direction="d",
            retrieval_text="t",
            source_data_version=1,
            source_fingerprint="fp",
            embedding=make_test_vector(2),
        )
    ]
    with pytest.raises(Exception):
        store.replace_projection(
            projection_key="new-key",
            provider_name=_PROVIDER,
            model_id=_MODEL_ID,
            embedding_dimension=384,  # violates CHECK (=768)
            projection_version=PROJECTION_VERSION,
            policy_version=POLICY_VERSION,
            documents=bad_docs,
        )

    with engine.connect() as connection:
        after_docs = connection.execute(
            text("SELECT count(*) FROM semantic_retrieval_document")
        ).scalar_one()
        after_meta = connection.execute(
            text(
                "SELECT projection_key FROM semantic_retrieval_index_meta "
                "WHERE status = 'READY'"
            )
        ).scalar_one()
    assert after_docs == before_docs
    assert after_meta == before_meta


@pytest.mark.integration
def test_duplicate_rebuild_does_not_double(test_db) -> None:  # type: ignore[no-untyped-def]
    _test_url, engine = test_db
    store = ProjectionStore(engine)
    provider = _fake_provider_for_demo()
    rebuild_projection(
        repository=_demo_repo(),
        store=store,
        provider=provider,
        policy_path=_POLICY_PATH,
    )
    rebuild_projection(
        repository=_demo_repo(),
        store=store,
        provider=provider,
        policy_path=_POLICY_PATH,
    )
    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM semantic_retrieval_document")
        ).scalar_one()
        meta_count = connection.execute(
            text("SELECT count(*) FROM semantic_retrieval_index_meta")
        ).scalar_one()
    assert count == 1
    assert meta_count == 1


@pytest.mark.integration
def test_builder_reports_not_ready_on_replace_failure(test_db) -> None:  # type: ignore[no-untyped-def]
    _test_url, engine = test_db
    store = ProjectionStore(engine)
    provider = FakeEmbeddingProvider(model_id=_MODEL_ID, dimension=384)
    with pytest.raises(ProjectionRebuildError):
        rebuild_projection(
            repository=_demo_repo(),
            store=store,
            provider=provider,
            policy_path=_POLICY_PATH,
        )
    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM semantic_retrieval_document")
        ).scalar_one()
    assert count == 0
