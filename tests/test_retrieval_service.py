"""Unit tests for SemanticRetrievalService (Fake provider/store; no DB/model)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from gov_service_agent.embedding.provider import EmbeddingDependencyError
from gov_service_agent.retrieval.admission import compute_projection_key
from gov_service_agent.retrieval.service import SemanticRetrievalService
from gov_service_agent.retrieval.types import (
    EXPECTED_EMBEDDING_DIMENSION,
    POLICY_VERSION,
    PROJECTION_VERSION,
    NotReadyReason,
    RetrievalStatus,
)
from gov_service_agent.settings import Settings
from tests.test_embedding import FakeEmbeddingProvider, make_test_vector


@dataclass
class FakeMeta:
    projection_key: str
    index_name: str = "business_intent"
    provider_name: str = "LOCAL_SENTENCE_TRANSFORMER"
    model_id: str = "fake-model"
    embedding_dimension: int = 768
    projection_version: str = PROJECTION_VERSION
    policy_version: str = POLICY_VERSION
    document_count: int = 0
    status: str = "READY"
    built_at: object | None = None


@dataclass
class FakeHit:
    business_id: str
    display_name: str
    direction: str
    eligibility_scope: str
    distance: float


@dataclass
class FakeStore:
    meta: FakeMeta | None = None
    hits: list[FakeHit] = field(default_factory=list)
    connectivity: bool = True
    search_calls: int = 0

    def check_connectivity(self) -> bool:
        return self.connectivity

    def load_ready_meta(self, projection_key: str) -> FakeMeta | None:
        if self.meta is None:
            return None
        if self.meta.projection_key != projection_key:
            return None
        return self.meta

    def search(self, *, projection_key: str, query_embedding, limit: int):  # type: ignore[no-untyped-def]
        self.search_calls += 1
        assert projection_key == (self.meta.projection_key if self.meta else "")
        return list(self.hits)[:limit]


def _configured_settings(**overrides: object) -> Settings:
    payload = {
        "embedding_provider": "LOCAL_SENTENCE_TRANSFORMER",
        "embedding_model_id": "fake-model",
        "embedding_model_path": "unused-path",
        "embedding_device": "cpu",
        "retrieval_top_k": 5,
        "retrieval_min_score": 0.50,
        "_env_file": None,
    }
    payload.update(overrides)
    return Settings(**payload)  # type: ignore[arg-type]


def _expected_key(settings: Settings) -> str:
    assert settings.embedding_provider is not None
    assert settings.embedding_model_id is not None
    return compute_projection_key(
        provider_name=settings.embedding_provider,
        model_id=settings.embedding_model_id,
        dimension=EXPECTED_EMBEDDING_DIMENSION,
        projection_version=PROJECTION_VERSION,
        policy_version=POLICY_VERSION,
    )


def test_empty_and_whitespace_invalid_query() -> None:
    provider = FakeEmbeddingProvider()
    store = FakeStore()
    service = SemanticRetrievalService(
        settings=_configured_settings(),
        provider=provider,
        store=store,
    )
    for query in ("", "   ", None):
        result = service.retrieve(query)  # type: ignore[arg-type]
        assert result.status == RetrievalStatus.INVALID_QUERY
        assert result.candidates == []
    assert provider.embed_query_calls == 0
    assert store.search_calls == 0


def test_provider_not_configured() -> None:
    settings = Settings(_env_file=None)
    service = SemanticRetrievalService(settings=settings, store=FakeStore())
    result = service.retrieve("交社保")
    assert result.status == RetrievalStatus.NOT_READY
    assert result.reason == NotReadyReason.PROVIDER_NOT_CONFIGURED


def test_db_unavailable_when_no_store_engine() -> None:
    settings = _configured_settings()
    # store_override None and no DATABASE_URL → UNAVAILABLE
    service = SemanticRetrievalService(settings=settings, store=None)
    result = service.retrieve("交社保")
    assert result.status == RetrievalStatus.UNAVAILABLE


def test_store_connectivity_false() -> None:
    settings = _configured_settings()
    service = SemanticRetrievalService(
        settings=settings,
        store=FakeStore(connectivity=False),
        provider=FakeEmbeddingProvider(),
    )
    result = service.retrieve("交社保")
    assert result.status == RetrievalStatus.UNAVAILABLE


def test_index_missing() -> None:
    settings = _configured_settings()
    provider = FakeEmbeddingProvider()
    service = SemanticRetrievalService(
        settings=settings,
        provider=provider,
        store=FakeStore(meta=None),
    )
    result = service.retrieve("交社保")
    assert result.status == RetrievalStatus.NOT_READY
    assert result.reason == NotReadyReason.INDEX_MISSING
    assert provider.embed_query_calls == 0


def test_model_mismatch() -> None:
    settings = _configured_settings()
    key = _expected_key(settings)
    provider = FakeEmbeddingProvider()
    store = FakeStore(
        meta=FakeMeta(projection_key=key, model_id="other-model", document_count=1)
    )
    service = SemanticRetrievalService(
        settings=settings, provider=provider, store=store
    )
    result = service.retrieve("交社保")
    assert result.status == RetrievalStatus.NOT_READY
    assert result.reason == NotReadyReason.MODEL_MISMATCH
    assert provider.embed_query_calls == 0


@pytest.mark.parametrize(
    "meta_kwargs,reason",
    [
        ({"embedding_dimension": 384}, NotReadyReason.DIMENSION_MISMATCH),
        (
            {"projection_version": "other-v1"},
            NotReadyReason.PROJECTION_VERSION_MISMATCH,
        ),
        ({"policy_version": "other-policy"}, NotReadyReason.POLICY_VERSION_MISMATCH),
    ],
)
def test_identity_mismatches(meta_kwargs: dict, reason: NotReadyReason) -> None:
    settings = _configured_settings()
    key = _expected_key(settings)
    meta = FakeMeta(projection_key=key, document_count=1, **meta_kwargs)
    provider = FakeEmbeddingProvider()
    service = SemanticRetrievalService(
        settings=settings,
        provider=provider,
        store=FakeStore(meta=meta),
    )
    result = service.retrieve("交社保")
    assert result.status == RetrievalStatus.NOT_READY
    assert result.reason == reason
    assert provider.embed_query_calls == 0


def test_built_empty_no_model_load() -> None:
    settings = _configured_settings()
    key = _expected_key(settings)
    provider = FakeEmbeddingProvider()
    service = SemanticRetrievalService(
        settings=settings,
        provider=provider,
        store=FakeStore(meta=FakeMeta(projection_key=key, document_count=0)),
    )
    result = service.retrieve("交社保")
    assert result.status == RetrievalStatus.NO_USABLE_CANDIDATE
    assert provider.embed_query_calls == 0
    assert provider.load_count == 0


def test_dependency_unavailable_maps_reason() -> None:
    settings = _configured_settings()
    key = _expected_key(settings)
    provider = FakeEmbeddingProvider(fail=EmbeddingDependencyError("missing"))
    store = FakeStore(meta=FakeMeta(projection_key=key, document_count=1))
    service = SemanticRetrievalService(
        settings=settings, provider=provider, store=store
    )
    result = service.retrieve("交社保")
    assert result.status == RetrievalStatus.NOT_READY
    assert result.reason == NotReadyReason.DEPENDENCY_UNAVAILABLE


def test_candidates_top_k_threshold_direction_and_no_final_id() -> None:
    settings = _configured_settings(retrieval_top_k=2, retrieval_min_score=0.50)
    key = _expected_key(settings)
    query = "交社保"
    query_vec = make_test_vector(1)
    provider = FakeEmbeddingProvider(vectors_by_text={query: query_vec})
    # distances → scores 0.9, 0.8, 0.2
    hits = [
        FakeHit("DEMO_SS_001", "灵活就业", "social_security", "ONLINE", 0.1),
        FakeHit("B", "B", "other", "ONLINE", 0.2),
        FakeHit("C", "C", "other", "ONLINE", 0.8),
    ]
    store = FakeStore(
        meta=FakeMeta(projection_key=key, document_count=3),
        hits=hits,
    )
    service = SemanticRetrievalService(
        settings=settings, provider=provider, store=store
    )
    result = service.retrieve(query)
    assert result.status == RetrievalStatus.CANDIDATES
    assert len(result.candidates) == 2
    assert result.candidates[0].business_id == "DEMO_SS_001"
    assert result.candidates[0].rank == 1
    assert result.candidates[0].score == pytest.approx(0.9)
    assert result.direction == "social_security"
    assert not hasattr(result, "final_business_id")
    dumped = result.model_dump()
    assert "final_business_id" not in dumped
    assert "confirmed_business_id" not in dumped
    assert "next_node" not in dumped


def test_below_threshold_no_usable() -> None:
    settings = _configured_settings(retrieval_min_score=0.95)
    key = _expected_key(settings)
    query = "q"
    provider = FakeEmbeddingProvider(vectors_by_text={query: make_test_vector(0)})
    store = FakeStore(
        meta=FakeMeta(projection_key=key, document_count=1),
        hits=[FakeHit("DEMO_SS_001", "n", "social_security", "ONLINE", 0.2)],
    )
    service = SemanticRetrievalService(
        settings=settings, provider=provider, store=store
    )
    result = service.retrieve(query)
    assert result.status == RetrievalStatus.NO_USABLE_CANDIDATE
    assert result.candidates == []
    assert result.direction is None


def test_score_higher_is_better_ordering() -> None:
    # Unit-level score conversion check used by service.
    distances = [0.4, 0.1, 0.2]
    scores = [1.0 - d for d in distances]
    ordered = sorted(zip(scores, ["a", "b", "c"], strict=True), reverse=True)
    assert [item[1] for item in ordered] == ["b", "c", "a"]
