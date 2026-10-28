"""F16-2 real local embedding recall checks (opt-in; no paid LLM).

Requires:
  RUN_EMBEDDING_REAL=1
  EMBEDDING_* configured for LOCAL_SENTENCE_TRANSFORMER / gte-base-zh

Does not write PostgreSQL. Validates that AFTER corpus includes both matters,
Owner-reported queries rank the expected business_id above min_score.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.embedding.provider import LocalSentenceTransformerProvider
from gov_service_agent.matters.registry import load_matter_registry
from gov_service_agent.retrieval.admission import draft_online_documents, load_admission_policy
from gov_service_agent.retrieval.types import EXPECTED_EMBEDDING_DIMENSION
from gov_service_agent.settings import Settings, get_settings

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REGISTRY = _REPO_ROOT / "data" / "matters" / "registry.json"
_POLICY = _REPO_ROOT / "data" / "retrieval" / "f06_online_eligibility.json"
_ID = "IDCARD_RC_LT5Y"
_SS = "DEMO_SS_001"
_MIN_SCORE = 0.50

_QUERIES: tuple[tuple[str, str], ...] = (
    ("我的身份证丢了，想在网上补办。", _ID),
    ("我的身份证损坏了，而且现在相貌变化比较大，可以网上补办吗？", _ID),
    ("补办身份证需要多少钱？", _ID),
    ("我辞职了，没有单位，想自己交社保。", _SS),
)


def _require_opt_in() -> Settings:
    if os.environ.get("RUN_EMBEDDING_REAL", "").strip() != "1":
        pytest.skip("RUN_EMBEDDING_REAL=1 required for real embedding recall")
    get_settings.cache_clear()
    settings = Settings()
    if (
        settings.embedding_provider is None
        or settings.embedding_model_id is None
        or settings.embedding_model_path is None
    ):
        pytest.fail("RUN_EMBEDDING_REAL=1 requires embedding configuration")
    return settings


def _dot(a: list[float], b: list[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b, strict=True)))


@pytest.mark.embedding_real
def test_real_local_embedding_ranks_idcard_and_ss() -> None:
    settings = _require_opt_in()
    registry = load_matter_registry(_REGISTRY, repo_root=_REPO_ROOT)
    assert registry.has(_ID) and registry.has(_SS)
    repo = JsonBusinessRepository.from_paths(registry.business_data_paths())
    policy = load_admission_policy(_POLICY)
    drafts = draft_online_documents(repo, policy)
    by_id = {d.business_id: d for d in drafts}
    assert set(by_id) == {_ID, _SS}

    provider = LocalSentenceTransformerProvider(
        model_id=settings.embedding_model_id,  # type: ignore[arg-type]
        model_path=settings.embedding_model_path,  # type: ignore[arg-type]
        device=settings.embedding_device,
        expected_dimension=EXPECTED_EMBEDDING_DIMENSION,
    )
    assert provider.dimension == EXPECTED_EMBEDDING_DIMENSION

    doc_vectors = {
        business_id: provider.embed_query(draft.retrieval_text)
        for business_id, draft in by_id.items()
    }
    for vector in doc_vectors.values():
        assert len(vector) == EXPECTED_EMBEDDING_DIMENSION
        assert math.isclose(math.sqrt(_dot(vector, vector)), 1.0, abs_tol=1e-3)

    for query, expected in _QUERIES:
        qv = provider.embed_query(query)
        ranked = sorted(
            (
                (business_id, _dot(qv, vector))
                for business_id, vector in doc_vectors.items()
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        top_id, top_score = ranked[0]
        assert top_id == expected, (query, ranked)
        assert top_score >= _MIN_SCORE, (query, ranked)
        # Cross-matter must not tie as sole usable hit for the other domain.
        other = _SS if expected == _ID else _ID
        other_score = next(score for bid, score in ranked if bid == other)
        assert top_score > other_score, (query, ranked)
