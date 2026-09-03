"""EmbeddingProvider Protocol and LocalSentenceTransformerProvider (F06)."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

logger = logging.getLogger("gov_service_agent")

EXPECTED_EMBEDDING_DIMENSION = 768
LOCAL_PROVIDER_NAME = "LOCAL_SENTENCE_TRANSFORMER"


class EmbeddingProviderError(Exception):
    """Base class for controlled embedding provider failures."""


class EmbeddingDependencyError(EmbeddingProviderError):
    """Optional embedding dependency is not installed."""


class EmbeddingModelError(EmbeddingProviderError):
    """Model path missing, invalid files, or load failure."""


class EmbeddingDeviceError(EmbeddingProviderError):
    """Explicit CUDA requested but unavailable."""


class EmbeddingDimensionError(EmbeddingProviderError):
    """Provider or vector dimension does not match expected schema dimension."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Unified embedding capability; Retrieval must not import SentenceTransformer."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_id(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    @property
    def actual_device(self) -> str | None: ...

    def embed_query(self, text: str) -> list[float]: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...


class LocalSentenceTransformerProvider:
    """Local sentence-transformers provider with lazy import/load."""

    def __init__(
        self,
        *,
        model_id: str,
        model_path: str | Path,
        device: str = "auto",
        expected_dimension: int = EXPECTED_EMBEDDING_DIMENSION,
    ) -> None:
        if not model_id or not str(model_id).strip():
            raise ValueError("model_id must be non-empty")
        path = Path(model_path)
        self._model_id = str(model_id).strip()
        self._model_path = path
        self._device_policy = str(device).strip().lower()
        if self._device_policy not in {"auto", "cpu", "cuda"}:
            raise ValueError("device must be auto, cpu, or cuda")
        self._expected_dimension = expected_dimension
        self._model = None
        self._actual_device: str | None = None
        self._resolved_dimension: int | None = None
        self._lock = threading.Lock()

    @property
    def provider_name(self) -> str:
        return LOCAL_PROVIDER_NAME

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        self._ensure_model_loaded()
        assert self._resolved_dimension is not None
        return self._resolved_dimension

    @property
    def actual_device(self) -> str | None:
        return self._actual_device

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        return vectors[0]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._ensure_model_loaded()
        raw = model.encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vectors: list[list[float]] = []
        for item in raw:
            vector = [float(x) for x in item]
            if len(vector) != self._expected_dimension:
                raise EmbeddingDimensionError(
                    "embedding vector length does not match expected dimension"
                )
            vectors.append(vector)
        return vectors

    def _ensure_model_loaded(self):  # type: ignore[no-untyped-def]
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            self._load_model_unlocked()
            assert self._model is not None
            return self._model

    def _load_model_unlocked(self) -> None:
        # Path gate before optional dependency import so missing path maps to
        # MODEL_NOT_AVAILABLE even when sentence-transformers is absent.
        if not self._model_path.exists():
            raise EmbeddingModelError("embedding model path is unavailable")

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingDependencyError(
                "sentence-transformers is not installed "
                "(optional extra: embedding-local)"
            ) from exc

        target_device = self._resolve_device()
        try:
            model = SentenceTransformer(
                str(self._model_path),
                device=target_device,
            )
        except EmbeddingProviderError:
            raise
        except Exception as exc:
            raise EmbeddingModelError("embedding model failed to load") from exc

        dim = self._read_dimension(model)
        if dim != self._expected_dimension:
            raise EmbeddingDimensionError(
                "provider dimension does not match expected schema dimension"
            )

        self._model = model
        self._resolved_dimension = dim
        self._actual_device = target_device
        logger.info(
            "message=embedding_model_loaded provider=%s model_id=%s "
            "dimension=%s actual_device=%s",
            self.provider_name,
            self._model_id,
            dim,
            target_device,
        )

    def _resolve_device(self) -> str:
        if self._device_policy == "cpu":
            return "cpu"
        if self._device_policy == "cuda":
            if not self._cuda_available():
                raise EmbeddingDeviceError("cuda requested but unavailable")
            return "cuda"
        # auto
        if self._cuda_available():
            return "cuda"
        return "cpu"

    @staticmethod
    def _cuda_available() -> bool:
        try:
            import torch
        except ImportError:
            return False
        try:
            return bool(torch.cuda.is_available())
        except Exception:
            return False

    @staticmethod
    def _read_dimension(model) -> int:  # type: ignore[no-untyped-def]
        get_dim = getattr(model, "get_embedding_dimension", None)
        if not callable(get_dim):
            get_dim = getattr(model, "get_sentence_embedding_dimension", None)
        if callable(get_dim):
            value = get_dim()
            if value is not None:
                return int(value)
        # Fallback probe without relying on business text.
        probe = model.encode(
            ["dimension_probe"],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return int(len(probe[0]))
