"""Opt-in real gte-base-zh smoke (govagent + local weights; never auto-run)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.embedding.provider import LocalSentenceTransformerProvider
from gov_service_agent.retrieval.builder import rebuild_projection
from gov_service_agent.retrieval.service import SemanticRetrievalService
from gov_service_agent.retrieval.store import ProjectionStore
from gov_service_agent.retrieval.types import RetrievalStatus
from gov_service_agent.settings import Settings, get_settings
from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_PATH = _REPO_ROOT / "data" / "demo" / "demo_ss_001.json"
_POLICY_PATH = _REPO_ROOT / "data" / "retrieval" / "f06_online_eligibility.json"
_REQUIRED_TEST_DATABASE = "gov_service_agent_test"
_GOLDEN_QUERY = "我辞职了，现在没单位，想自己交社保"


def _require_opt_in() -> None:
    if os.environ.get("RUN_EMBEDDING_REAL", "").strip() != "1":
        pytest.skip("RUN_EMBEDDING_REAL=1 required for real embedding smoke")


def _real_settings(*, device: str | None = None) -> Settings:
    get_settings.cache_clear()
    # Prefer process environment / local ignored .env via Settings default.
    settings = Settings()
    if (
        settings.embedding_provider is None
        or settings.embedding_model_id is None
        or settings.embedding_model_path is None
    ):
        # Opt-in already required by callers: missing config must FAIL, not SKIP.
        pytest.fail("RUN_EMBEDDING_REAL=1 requires embedding configuration")
    if device is not None:
        settings = Settings(
            embedding_provider=settings.embedding_provider,
            embedding_model_id=settings.embedding_model_id,
            embedding_model_path=settings.embedding_model_path,
            embedding_device=device,
            retrieval_top_k=settings.retrieval_top_k,
            retrieval_min_score=settings.retrieval_min_score,
            _env_file=None,
        )
    return settings


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


def test_opt_in_missing_embedding_config_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Opt-in without embedding config must FAIL (not SKIP). Always cheap; no model."""
    monkeypatch.setenv("RUN_EMBEDDING_REAL", "1")
    for key in (
        "EMBEDDING_PROVIDER",
        "EMBEDDING_MODEL_ID",
        "EMBEDDING_MODEL_PATH",
        "EMBEDDING_DEVICE",
        "RETRIEVAL_TOP_K",
        "RETRIEVAL_MIN_SCORE",
    ):
        monkeypatch.delenv(key, raising=False)
    # Isolate from any project .env without reading or printing its contents.
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    with pytest.raises(
        pytest.fail.Exception, match="requires embedding configuration"
    ):
        _real_settings()


@pytest.mark.embedding_real
def test_real_provider_cuda_smoke() -> None:
    _require_opt_in()
    settings = _real_settings(device="cuda")
    provider = LocalSentenceTransformerProvider(
        model_id=settings.embedding_model_id,  # type: ignore[arg-type]
        model_path=settings.embedding_model_path,  # type: ignore[arg-type]
        device="cuda",
    )
    dim = provider.dimension
    assert dim == 768
    assert provider.actual_device == "cuda"
    vector = provider.embed_query("社保缴费")
    assert len(vector) == 768


@pytest.mark.embedding_real
def test_real_provider_cpu_fallback_smoke() -> None:
    _require_opt_in()
    settings = _real_settings(device="cpu")
    provider = LocalSentenceTransformerProvider(
        model_id=settings.embedding_model_id,  # type: ignore[arg-type]
        model_path=settings.embedding_model_path,  # type: ignore[arg-type]
        device="cpu",
    )
    assert provider.dimension == 768
    assert provider.actual_device == "cpu"
    vector = provider.embed_query("社保缴费")
    assert len(vector) == 768


@pytest.mark.embedding_real
@pytest.mark.integration
def test_real_golden_demo_ss_001_recall() -> None:
    _require_opt_in()
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url or not test_url.strip():
        pytest.fail("TEST_DATABASE_URL is required for golden real retrieval")
    _validate_test_database_url(test_url)

    settings = _real_settings(device="cuda")
    provider = LocalSentenceTransformerProvider(
        model_id=settings.embedding_model_id,  # type: ignore[arg-type]
        model_path=settings.embedding_model_path,  # type: ignore[arg-type]
        device="cuda",
    )
    engine = create_engine(test_url)
    try:
        store = ProjectionStore(engine)
        rebuild_projection(
            repository=JsonBusinessRepository.from_paths([_DEMO_PATH]),
            store=store,
            provider=provider,
            policy_path=_POLICY_PATH,
        )
        service = SemanticRetrievalService(
            settings=Settings(
                embedding_provider=settings.embedding_provider,
                embedding_model_id=settings.embedding_model_id,
                embedding_model_path=settings.embedding_model_path,
                embedding_device="cuda",
                retrieval_top_k=5,
                retrieval_min_score=0.50,
                _env_file=None,
            ),
            provider=provider,
            store=store,
        )
        result = service.retrieve(_GOLDEN_QUERY)
        assert result.status == RetrievalStatus.CANDIDATES
        assert result.candidates
        assert result.candidates[0].business_id == "DEMO_SS_001"
        assert result.candidates[0].rank == 1
        assert result.candidates[0].score >= 0.50
        dumped = result.model_dump()
        assert "final_business_id" not in dumped
        assert "confirmed_business_id" not in dumped
    finally:
        engine.dispose()
