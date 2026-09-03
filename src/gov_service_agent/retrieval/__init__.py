"""Semantic retrieval package (F06)."""

from gov_service_agent.retrieval.builder import ProjectionRebuildError, rebuild_projection
from gov_service_agent.retrieval.service import SemanticRetrievalService
from gov_service_agent.retrieval.types import (
    NotReadyReason,
    RetrievalCandidate,
    RetrievalResult,
    RetrievalStatus,
)

__all__ = [
    "NotReadyReason",
    "ProjectionRebuildError",
    "RetrievalCandidate",
    "RetrievalResult",
    "RetrievalStatus",
    "SemanticRetrievalService",
    "rebuild_projection",
]
