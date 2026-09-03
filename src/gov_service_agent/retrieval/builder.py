"""Full rebuild of ONLINE semantic retrieval projection (F06)."""

from __future__ import annotations

import logging
from pathlib import Path

from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.embedding.provider import (
    EmbeddingDependencyError,
    EmbeddingDeviceError,
    EmbeddingDimensionError,
    EmbeddingModelError,
    EmbeddingProvider,
)
from gov_service_agent.retrieval.admission import (
    AdmissionPolicyError,
    compute_projection_key,
    draft_online_documents,
    load_admission_policy,
)
from gov_service_agent.retrieval.store import DocumentWriteRow, ProjectionStore
from gov_service_agent.retrieval.types import (
    EXPECTED_EMBEDDING_DIMENSION as RETRIEVAL_EXPECTED_DIM,
    POLICY_VERSION,
    PROJECTION_VERSION,
)

logger = logging.getLogger("gov_service_agent")


class ProjectionRebuildError(Exception):
    """Controlled rebuild failure; must not leave half-written projection."""


def rebuild_projection(
    *,
    repository: JsonBusinessRepository,
    store: ProjectionStore,
    provider: EmbeddingProvider,
    policy_path: Path | str,
    expected_policy_version: str = POLICY_VERSION,
    expected_projection_version: str = PROJECTION_VERSION,
    expected_dimension: int = RETRIEVAL_EXPECTED_DIM,
) -> str:
    """
    Fresh-read policy + business data, encode outside DB txn, atomic replace.

    Returns the active projection_key on success.
    """
    try:
        policy = load_admission_policy(policy_path)
    except AdmissionPolicyError as exc:
        raise ProjectionRebuildError(str(exc)) from exc

    if policy.policy_version != expected_policy_version:
        raise ProjectionRebuildError(
            "eligibility policy_version does not match expected version"
        )

    try:
        drafts = draft_online_documents(repository, policy)
    except AdmissionPolicyError as exc:
        raise ProjectionRebuildError(str(exc)) from exc

    # Dimension gate before any DB write.
    try:
        provider_dim = provider.dimension
    except EmbeddingDependencyError as exc:
        raise ProjectionRebuildError(str(exc)) from exc
    except EmbeddingDeviceError as exc:
        raise ProjectionRebuildError(str(exc)) from exc
    except EmbeddingModelError as exc:
        raise ProjectionRebuildError(str(exc)) from exc
    except EmbeddingDimensionError as exc:
        raise ProjectionRebuildError(str(exc)) from exc

    if provider_dim != expected_dimension:
        raise ProjectionRebuildError(
            "provider dimension does not match expected schema dimension"
        )

    texts = [d.retrieval_text for d in drafts]
    try:
        vectors = provider.embed_documents(texts) if texts else []
    except EmbeddingDependencyError as exc:
        raise ProjectionRebuildError(str(exc)) from exc
    except EmbeddingDeviceError as exc:
        raise ProjectionRebuildError(str(exc)) from exc
    except EmbeddingModelError as exc:
        raise ProjectionRebuildError(str(exc)) from exc
    except EmbeddingDimensionError as exc:
        raise ProjectionRebuildError(str(exc)) from exc

    if len(vectors) != len(drafts):
        raise ProjectionRebuildError("embedding count does not match documents")
    for vector in vectors:
        if len(vector) != expected_dimension:
            raise ProjectionRebuildError(
                "document embedding shape does not match expected dimension"
            )

    provider_name = provider.provider_name
    model_id = provider.model_id
    projection_key = compute_projection_key(
        provider_name=provider_name,
        model_id=model_id,
        dimension=expected_dimension,
        projection_version=expected_projection_version,
        policy_version=policy.policy_version,
    )

    rows = [
        DocumentWriteRow(
            business_id=draft.business_id,
            display_name=draft.display_name,
            direction=draft.direction,
            retrieval_text=draft.retrieval_text,
            source_data_version=draft.source_data_version,
            source_fingerprint=draft.source_fingerprint,
            embedding=vector,
        )
        for draft, vector in zip(drafts, vectors, strict=True)
    ]

    try:
        store.replace_projection(
            projection_key=projection_key,
            provider_name=provider_name,
            model_id=model_id,
            embedding_dimension=expected_dimension,
            projection_version=expected_projection_version,
            policy_version=policy.policy_version,
            documents=rows,
        )
    except Exception as exc:
        raise ProjectionRebuildError("projection replace transaction failed") from exc

    logger.info(
        "message=projection_rebuild_ok provider=%s model_id=%s "
        "dimension=%s document_count=%s projection_version=%s policy_version=%s",
        provider_name,
        model_id,
        expected_dimension,
        len(rows),
        expected_projection_version,
        policy.policy_version,
    )
    return projection_key
