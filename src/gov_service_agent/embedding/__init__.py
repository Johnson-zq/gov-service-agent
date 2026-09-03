"""Embedding Provider abstraction (F06)."""

from gov_service_agent.embedding.provider import (
    EmbeddingDependencyError,
    EmbeddingDeviceError,
    EmbeddingDimensionError,
    EmbeddingModelError,
    EmbeddingProvider,
    EmbeddingProviderError,
    LocalSentenceTransformerProvider,
)

__all__ = [
    "EmbeddingDependencyError",
    "EmbeddingDeviceError",
    "EmbeddingDimensionError",
    "EmbeddingModelError",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "LocalSentenceTransformerProvider",
]
