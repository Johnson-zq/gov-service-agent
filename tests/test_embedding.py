"""Unit tests for F06 EmbeddingProvider (no real model / GPU)."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from gov_service_agent.embedding.provider import (
    EmbeddingDependencyError,
    EmbeddingDeviceError,
    EmbeddingDimensionError,
    EmbeddingModelError,
    LocalSentenceTransformerProvider,
)


def make_test_vector(
    primary_index: int,
    secondary_index: int | None = None,
    dimension: int = 768,
) -> list[float]:
    """Deterministic sparse 768-D vector helper for ranking tests."""
    if primary_index < 0 or primary_index >= dimension:
        raise ValueError("primary_index out of range")
    vector = [0.0] * dimension
    vector[primary_index] = 1.0
    if secondary_index is not None:
        if secondary_index < 0 or secondary_index >= dimension:
            raise ValueError("secondary_index out of range")
        vector[secondary_index] = 0.25
    return vector


class FakeEmbeddingProvider:
    """Deterministic EmbeddingProvider-compatible double."""

    def __init__(
        self,
        *,
        model_id: str = "fake-model",
        dimension: int = 768,
        actual_device: str = "cpu",
        vectors_by_text: dict[str, list[float]] | None = None,
        fail: Exception | None = None,
    ) -> None:
        self._model_id = model_id
        self._dimension = dimension
        self._actual_device = actual_device
        self._vectors_by_text = vectors_by_text or {}
        self._fail = fail
        self.load_count = 0
        self.embed_query_calls = 0
        self.embed_documents_calls = 0
        self.last_normalize: bool | None = None

    @property
    def provider_name(self) -> str:
        return "LOCAL_SENTENCE_TRANSFORMER"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        self.load_count += 1
        if self._fail is not None:
            raise self._fail
        return self._dimension

    @property
    def actual_device(self) -> str | None:
        return self._actual_device

    def embed_query(self, text: str) -> list[float]:
        self.embed_query_calls += 1
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: list[str] | tuple[str, ...]) -> list[list[float]]:
        self.embed_documents_calls += 1
        if self._fail is not None:
            raise self._fail
        out: list[list[float]] = []
        for text in texts:
            if text in self._vectors_by_text:
                vector = list(self._vectors_by_text[text])
            else:
                # Stable fallback from text hash into a one-hot-ish slot.
                idx = sum(ord(ch) for ch in text) % self._dimension
                vector = make_test_vector(idx, dimension=self._dimension)
            if len(vector) != self._dimension:
                raise EmbeddingDimensionError("fake vector shape mismatch")
            out.append(vector)
        return out


def test_package_import_does_not_require_sentence_transformers() -> None:
    import gov_service_agent
    import gov_service_agent.embedding
    import gov_service_agent.retrieval

    assert gov_service_agent is not None
    assert gov_service_agent.embedding is not None
    assert gov_service_agent.retrieval is not None


def test_local_provider_constructor_is_lightweight(tmp_path: Path) -> None:
    path = tmp_path / "missing-model"
    provider = LocalSentenceTransformerProvider(
        model_id="AI-ModelScope/gte-base-zh",
        model_path=path,
        device="cpu",
    )
    assert provider.provider_name == "LOCAL_SENTENCE_TRANSFORMER"
    assert provider.model_id == "AI-ModelScope/gte-base-zh"
    assert provider.actual_device is None


def test_dependency_unavailable_is_controlled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    real_import = __import__

    def _fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "sentence_transformers" or name.startswith(
            "sentence_transformers."
        ):
            raise ImportError("forced missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _fake_import)
    provider = LocalSentenceTransformerProvider(
        model_id="AI-ModelScope/gte-base-zh",
        model_path=model_dir,
        device="cpu",
    )
    with pytest.raises(EmbeddingDependencyError):
        _ = provider.dimension


def test_model_path_missing(tmp_path: Path) -> None:
    provider = LocalSentenceTransformerProvider(
        model_id="AI-ModelScope/gte-base-zh",
        model_path=tmp_path / "nope",
        device="cpu",
    )
    with pytest.raises(EmbeddingModelError):
        _ = provider.dimension


def test_explicit_cuda_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    class _FakeST:
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("should not construct before device check")

    fake_mod = types.ModuleType("sentence_transformers")
    fake_mod.SentenceTransformer = _FakeST  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_mod)
    monkeypatch.setattr(
        LocalSentenceTransformerProvider,
        "_cuda_available",
        staticmethod(lambda: False),
    )
    provider = LocalSentenceTransformerProvider(
        model_id="AI-ModelScope/gte-base-zh",
        model_path=model_dir,
        device="cuda",
    )
    with pytest.raises(EmbeddingDeviceError):
        _ = provider.dimension


def test_lazy_load_once_and_normalize_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    encode_calls: list[dict[str, object]] = []

    class _FakeModel:
        def get_sentence_embedding_dimension(self) -> int:
            return 768

        def encode(self, texts, normalize_embeddings=False, show_progress_bar=False):  # type: ignore[no-untyped-def]
            encode_calls.append(
                {
                    "texts": list(texts),
                    "normalize_embeddings": normalize_embeddings,
                }
            )
            return [[0.0] * 768 for _ in texts]

    class _FakeST:
        construct_count = 0

        def __init__(self, path, device="cpu"):  # type: ignore[no-untyped-def]
            _FakeST.construct_count += 1
            self.path = path
            self.device = device

        def get_sentence_embedding_dimension(self) -> int:
            return 768

        def encode(self, texts, normalize_embeddings=False, show_progress_bar=False):  # type: ignore[no-untyped-def]
            return _FakeModel().encode(
                texts,
                normalize_embeddings=normalize_embeddings,
                show_progress_bar=show_progress_bar,
            )

    fake_mod = types.ModuleType("sentence_transformers")
    fake_mod.SentenceTransformer = _FakeST  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_mod)

    provider = LocalSentenceTransformerProvider(
        model_id="AI-ModelScope/gte-base-zh",
        model_path=model_dir,
        device="cpu",
    )
    v1 = provider.embed_query("hello")
    v2 = provider.embed_documents(["a", "b"])
    assert len(v1) == 768
    assert len(v2) == 2
    assert _FakeST.construct_count == 1
    assert all(call["normalize_embeddings"] is True for call in encode_calls)
    assert provider.actual_device == "cpu"


def test_dimension_mismatch_on_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    class _FakeST:
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            pass

        def get_sentence_embedding_dimension(self) -> int:
            return 384

    fake_mod = types.ModuleType("sentence_transformers")
    fake_mod.SentenceTransformer = _FakeST  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_mod)
    provider = LocalSentenceTransformerProvider(
        model_id="AI-ModelScope/gte-base-zh",
        model_path=model_dir,
        device="cpu",
    )
    with pytest.raises(EmbeddingDimensionError):
        _ = provider.dimension


def test_fake_helper_deterministic() -> None:
    a = make_test_vector(3, 7)
    b = make_test_vector(3, 7)
    assert a == b
    assert len(a) == 768
    assert a[3] == 1.0
    assert a[7] == 0.25
