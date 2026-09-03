"""Online Semantic Retrieval service (F06)."""

from __future__ import annotations

import logging
from pathlib import Path

from gov_service_agent.db.runtime import get_engine
from gov_service_agent.embedding.provider import (
    EmbeddingDependencyError,
    EmbeddingDeviceError,
    EmbeddingDimensionError,
    EmbeddingModelError,
    EmbeddingProvider,
    LocalSentenceTransformerProvider,
)
from gov_service_agent.retrieval.admission import compute_projection_key
from gov_service_agent.retrieval.store import ProjectionStore
from gov_service_agent.retrieval.types import (
    DEFAULT_MIN_SCORE,
    DEFAULT_TOP_K,
    EXPECTED_EMBEDDING_DIMENSION,
    POLICY_VERSION,
    PROJECTION_VERSION,
    NotReadyReason,
    RetrievalCandidate,
    RetrievalResult,
    RetrievalStatus,
)
from gov_service_agent.settings import Settings, get_settings

logger = logging.getLogger("gov_service_agent")


class SemanticRetrievalService:
    """Query orchestration for ONLINE semantic retrieval."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        provider: EmbeddingProvider | None = None,
        store: ProjectionStore | None = None,
        policy_path: Path | str | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._provider_override = provider
        self._store_override = store
        self._policy_path = (
            Path(policy_path)
            if policy_path is not None
            else Path("data/retrieval/f06_online_eligibility.json")
        )

    def retrieve(self, query: str | None) -> RetrievalResult:
        normalized = "" if query is None else str(query).strip()
        top_k = self._settings.retrieval_top_k
        min_score = self._settings.retrieval_min_score

        if normalized == "":
            return RetrievalResult(
                status=RetrievalStatus.INVALID_QUERY,
                query=normalized,
                top_k=top_k,
                min_score=min_score,
            )

        if not self._embedding_configured():
            return self._not_ready(
                normalized,
                NotReadyReason.PROVIDER_NOT_CONFIGURED,
                top_k=top_k,
                min_score=min_score,
            )

        store = self._resolve_store()
        if store is None:
            return RetrievalResult(
                status=RetrievalStatus.UNAVAILABLE,
                query=normalized,
                top_k=top_k,
                min_score=min_score,
            )
        if not store.check_connectivity():
            return RetrievalResult(
                status=RetrievalStatus.UNAVAILABLE,
                query=normalized,
                top_k=top_k,
                min_score=min_score,
            )

        provider_name = self._settings.embedding_provider
        model_id = self._settings.embedding_model_id
        assert provider_name is not None and model_id is not None

        expected_key = compute_projection_key(
            provider_name=provider_name,
            model_id=model_id,
            dimension=EXPECTED_EMBEDDING_DIMENSION,
            projection_version=PROJECTION_VERSION,
            policy_version=POLICY_VERSION,
        )

        meta = store.load_ready_meta(expected_key)
        if meta is None:
            # Cheap identity / missing check before loading the model.
            return self._not_ready(
                normalized,
                NotReadyReason.INDEX_MISSING,
                top_k=top_k,
                min_score=min_score,
                provider_name=provider_name,
                model_id=model_id,
                projection_key=expected_key,
            )

        if meta.provider_name != provider_name or meta.model_id != model_id:
            return self._not_ready(
                normalized,
                NotReadyReason.MODEL_MISMATCH,
                top_k=top_k,
                min_score=min_score,
                provider_name=provider_name,
                model_id=model_id,
                projection_key=expected_key,
            )
        if meta.embedding_dimension != EXPECTED_EMBEDDING_DIMENSION:
            return self._not_ready(
                normalized,
                NotReadyReason.DIMENSION_MISMATCH,
                top_k=top_k,
                min_score=min_score,
                provider_name=provider_name,
                model_id=model_id,
                projection_key=expected_key,
            )
        if meta.projection_version != PROJECTION_VERSION:
            return self._not_ready(
                normalized,
                NotReadyReason.PROJECTION_VERSION_MISMATCH,
                top_k=top_k,
                min_score=min_score,
                provider_name=provider_name,
                model_id=model_id,
                projection_key=expected_key,
            )
        if meta.policy_version != POLICY_VERSION:
            return self._not_ready(
                normalized,
                NotReadyReason.POLICY_VERSION_MISMATCH,
                top_k=top_k,
                min_score=min_score,
                provider_name=provider_name,
                model_id=model_id,
                projection_key=expected_key,
            )

        # Built-empty: no need to load the heavy model.
        if meta.document_count == 0:
            return RetrievalResult(
                status=RetrievalStatus.NO_USABLE_CANDIDATE,
                query=normalized,
                provider_name=provider_name,
                model_id=model_id,
                projection_version=PROJECTION_VERSION,
                policy_version=POLICY_VERSION,
                projection_key=expected_key,
                top_k=top_k,
                min_score=min_score,
            )

        provider = self._resolve_provider()
        if isinstance(provider, RetrievalResult):
            return provider

        try:
            if provider.dimension != EXPECTED_EMBEDDING_DIMENSION:
                return self._not_ready(
                    normalized,
                    NotReadyReason.DIMENSION_MISMATCH,
                    top_k=top_k,
                    min_score=min_score,
                    provider_name=provider.provider_name,
                    model_id=provider.model_id,
                    projection_key=expected_key,
                )
            query_vector = provider.embed_query(normalized)
        except EmbeddingDependencyError:
            return self._not_ready(
                normalized,
                NotReadyReason.DEPENDENCY_UNAVAILABLE,
                top_k=top_k,
                min_score=min_score,
                provider_name=provider_name,
                model_id=model_id,
                projection_key=expected_key,
            )
        except EmbeddingDeviceError:
            return self._not_ready(
                normalized,
                NotReadyReason.DEVICE_UNAVAILABLE,
                top_k=top_k,
                min_score=min_score,
                provider_name=provider_name,
                model_id=model_id,
                projection_key=expected_key,
            )
        except EmbeddingModelError:
            return self._not_ready(
                normalized,
                NotReadyReason.MODEL_NOT_AVAILABLE,
                top_k=top_k,
                min_score=min_score,
                provider_name=provider_name,
                model_id=model_id,
                projection_key=expected_key,
            )
        except EmbeddingDimensionError:
            return self._not_ready(
                normalized,
                NotReadyReason.DIMENSION_MISMATCH,
                top_k=top_k,
                min_score=min_score,
                provider_name=provider_name,
                model_id=model_id,
                projection_key=expected_key,
            )

        if len(query_vector) != EXPECTED_EMBEDDING_DIMENSION:
            return self._not_ready(
                normalized,
                NotReadyReason.DIMENSION_MISMATCH,
                top_k=top_k,
                min_score=min_score,
                provider_name=provider.provider_name,
                model_id=provider.model_id,
                projection_key=expected_key,
            )

        # Fetch a wider pool then apply threshold in service.
        fetch_limit = max(top_k * 3, 20)
        try:
            hits = store.search(
                projection_key=expected_key,
                query_embedding=query_vector,
                limit=fetch_limit,
            )
        except Exception:
            logger.warning("message=retrieval_search_unavailable")
            return RetrievalResult(
                status=RetrievalStatus.UNAVAILABLE,
                query=normalized,
                provider_name=provider.provider_name,
                model_id=provider.model_id,
                projection_version=PROJECTION_VERSION,
                policy_version=POLICY_VERSION,
                projection_key=expected_key,
                top_k=top_k,
                min_score=min_score,
            )

        candidates: list[RetrievalCandidate] = []
        for hit in hits:
            score = 1.0 - hit.distance
            if score < min_score:
                continue
            candidates.append(
                RetrievalCandidate(
                    business_id=hit.business_id,
                    display_name=hit.display_name,
                    score=score,
                    rank=len(candidates) + 1,
                    direction=hit.direction,
                    eligibility_scope=hit.eligibility_scope,
                )
            )
            if len(candidates) >= top_k:
                break

        if not candidates:
            return RetrievalResult(
                status=RetrievalStatus.NO_USABLE_CANDIDATE,
                query=normalized,
                provider_name=provider.provider_name,
                model_id=provider.model_id,
                projection_version=PROJECTION_VERSION,
                policy_version=POLICY_VERSION,
                projection_key=expected_key,
                top_k=top_k,
                min_score=min_score,
            )

        direction_hint = candidates[0].direction
        logger.info(
            "message=retrieval_ok status=CANDIDATES candidate_count=%s "
            "provider=%s model_id=%s dimension=%s actual_device=%s",
            len(candidates),
            provider.provider_name,
            provider.model_id,
            EXPECTED_EMBEDDING_DIMENSION,
            provider.actual_device,
        )
        return RetrievalResult(
            status=RetrievalStatus.CANDIDATES,
            query=normalized,
            direction=direction_hint,
            candidates=candidates,
            provider_name=provider.provider_name,
            model_id=provider.model_id,
            projection_version=PROJECTION_VERSION,
            policy_version=POLICY_VERSION,
            projection_key=expected_key,
            top_k=top_k,
            min_score=min_score,
        )

    def _embedding_configured(self) -> bool:
        s = self._settings
        return (
            s.embedding_provider is not None
            and s.embedding_model_id is not None
            and s.embedding_model_path is not None
        )

    def _resolve_store(self) -> ProjectionStore | None:
        if self._store_override is not None:
            return self._store_override
        engine = get_engine(self._settings)
        if engine is None:
            return None
        return ProjectionStore(engine)

    def _resolve_provider(self) -> EmbeddingProvider | RetrievalResult:
        if self._provider_override is not None:
            return self._provider_override
        s = self._settings
        assert s.embedding_provider is not None
        assert s.embedding_model_id is not None
        assert s.embedding_model_path is not None
        if s.embedding_provider != "LOCAL_SENTENCE_TRANSFORMER":
            return self._not_ready(
                "",
                NotReadyReason.PROVIDER_NOT_CONFIGURED,
                top_k=s.retrieval_top_k,
                min_score=s.retrieval_min_score,
            )
        return LocalSentenceTransformerProvider(
            model_id=s.embedding_model_id,
            model_path=s.embedding_model_path,
            device=s.embedding_device,
            expected_dimension=EXPECTED_EMBEDDING_DIMENSION,
        )

    def _not_ready(
        self,
        query: str,
        reason: NotReadyReason,
        *,
        top_k: int,
        min_score: float,
        provider_name: str | None = None,
        model_id: str | None = None,
        projection_key: str | None = None,
    ) -> RetrievalResult:
        return RetrievalResult(
            status=RetrievalStatus.NOT_READY,
            query=query,
            reason=reason,
            provider_name=provider_name,
            model_id=model_id,
            projection_version=PROJECTION_VERSION,
            policy_version=POLICY_VERSION,
            projection_key=projection_key,
            top_k=top_k,
            min_score=min_score,
        )


# Re-export defaults for importers that need the frozen numbers without magic.
__all__ = [
    "DEFAULT_MIN_SCORE",
    "DEFAULT_TOP_K",
    "SemanticRetrievalService",
]
