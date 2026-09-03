"""Unit tests for F06 admission + projection builder (no Docker / real model)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from gov_service_agent.business_data.models import (
    DataScope,
    LifecycleStatus,
    load_snapshot,
    snapshot_from_dict,
)
from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.embedding.provider import EmbeddingDimensionError
from gov_service_agent.retrieval.admission import (
    AdmissionPolicyError,
    build_retrieval_text,
    compute_projection_key,
    draft_online_documents,
    load_admission_policy,
    parse_admission_policy,
    source_fingerprint,
)
from gov_service_agent.retrieval.builder import ProjectionRebuildError, rebuild_projection
from gov_service_agent.retrieval.types import (
    EXPECTED_EMBEDDING_DIMENSION,
    POLICY_VERSION,
    PROJECTION_VERSION,
)
from tests.test_embedding import FakeEmbeddingProvider, make_test_vector

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_SS_001_PATH = REPO_ROOT / "data" / "demo" / "demo_ss_001.json"
POLICY_PATH = REPO_ROOT / "data" / "retrieval" / "f06_online_eligibility.json"


@dataclass
class RecordingStore:
    replace_calls: list[dict] = field(default_factory=list)
    fail_replace: bool = False

    def replace_projection(self, **kwargs):  # type: ignore[no-untyped-def]
        if self.fail_replace:
            raise RuntimeError("forced replace failure")
        self.replace_calls.append(kwargs)


def _demo_repo() -> JsonBusinessRepository:
    return JsonBusinessRepository.from_paths([DEMO_SS_001_PATH])


def test_official_policy_loads() -> None:
    policy = load_admission_policy(POLICY_PATH)
    assert policy.schema_version == 1
    assert policy.policy_version == POLICY_VERSION
    assert policy.allow_ids() == frozenset({"DEMO_SS_001"})


def test_policy_does_not_auto_admit_by_prefix() -> None:
    """Only explicit ALLOW entries are online; no prefix / similarity admit."""
    policy = load_admission_policy(POLICY_PATH)
    assert "DEMO_SS_002" not in policy.allow_ids()
    assert "DEMO_INV" not in policy.allow_ids()
    drafts = draft_online_documents(_demo_repo(), policy)
    assert [d.business_id for d in drafts] == ["DEMO_SS_001"]


@pytest.mark.parametrize(
    "mutator,match",
    [
        (lambda d: d.__setitem__("schema_version", 99), "schema_version"),
        (lambda d: d.__setitem__("policy_version", ""), "policy_version"),
        (lambda d: d.__setitem__("policy_version", None), "policy_version"),
    ],
)
def test_policy_schema_errors(mutator, match: str) -> None:  # type: ignore[no-untyped-def]
    raw = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    mutator(raw)
    with pytest.raises(AdmissionPolicyError, match=match):
        parse_admission_policy(raw)


def test_duplicate_business_id_invalid() -> None:
    raw = {
        "schema_version": 1,
        "policy_version": POLICY_VERSION,
        "entries": [
            {
                "business_id": "DEMO_SS_001",
                "decision": "ALLOW",
                "reason": "a",
            },
            {
                "business_id": "DEMO_SS_001",
                "decision": "ALLOW",
                "reason": "b",
            },
        ],
    }
    with pytest.raises(AdmissionPolicyError, match="duplicate"):
        parse_admission_policy(raw)


def test_unknown_business_fail_closed(tmp_path: Path) -> None:
    raw = {
        "schema_version": 1,
        "policy_version": POLICY_VERSION,
        "entries": [
            {
                "business_id": "DEMO_NOT_EXIST",
                "decision": "ALLOW",
                "reason": "x",
            }
        ],
    }
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    policy = load_admission_policy(path)
    with pytest.raises(AdmissionPolicyError, match="unknown business_id"):
        draft_online_documents(_demo_repo(), policy)


def test_non_allow_and_empty_reason_invalid() -> None:
    with pytest.raises(AdmissionPolicyError, match="ALLOW"):
        parse_admission_policy(
            {
                "schema_version": 1,
                "policy_version": POLICY_VERSION,
                "entries": [
                    {
                        "business_id": "DEMO_SS_001",
                        "decision": "DENY",
                        "reason": "x",
                    }
                ],
            }
        )
    with pytest.raises(AdmissionPolicyError, match="reason"):
        parse_admission_policy(
            {
                "schema_version": 1,
                "policy_version": POLICY_VERSION,
                "entries": [
                    {
                        "business_id": "DEMO_SS_001",
                        "decision": "ALLOW",
                        "reason": "  ",
                    }
                ],
            }
        )


def test_inactive_or_test_scope_not_eligible() -> None:
    snapshot = load_snapshot(DEMO_SS_001_PATH)
    data = snapshot.model_dump(mode="json")
    data["business"]["status"] = LifecycleStatus.INACTIVE.value
    inactive = snapshot_from_dict(data)
    repo = JsonBusinessRepository(
        {inactive.business.business_id: inactive}
    )
    policy = load_admission_policy(POLICY_PATH)
    with pytest.raises(AdmissionPolicyError, match="ONLINE predicate"):
        draft_online_documents(repo, policy)

    data2 = load_snapshot(DEMO_SS_001_PATH).model_dump(mode="json")
    data2["business"]["data_scope"] = DataScope.TEST.value
    test_snap = snapshot_from_dict(data2)
    repo2 = JsonBusinessRepository({test_snap.business.business_id: test_snap})
    with pytest.raises(AdmissionPolicyError, match="ONLINE predicate"):
        draft_online_documents(repo2, policy)


def test_retrieval_text_and_fingerprint_stable() -> None:
    snapshot = load_snapshot(DEMO_SS_001_PATH)
    text = build_retrieval_text(snapshot)
    assert text == (
        f"{snapshot.business.category}\n{snapshot.business.canonical_name}"
    )
    assert "身份证" not in text
    fp1 = source_fingerprint(snapshot, retrieval_text=text)
    fp2 = source_fingerprint(snapshot, retrieval_text=text)
    assert fp1 == fp2
    other = source_fingerprint(
        snapshot, retrieval_text=text, policy_version="other"
    )
    assert other != fp1


def test_projection_key_ignores_model_path() -> None:
    a = compute_projection_key(
        provider_name="LOCAL_SENTENCE_TRANSFORMER",
        model_id="AI-ModelScope/gte-base-zh",
        dimension=768,
    )
    b = compute_projection_key(
        provider_name="LOCAL_SENTENCE_TRANSFORMER",
        model_id="AI-ModelScope/gte-base-zh",
        dimension=768,
    )
    assert a == b
    c = compute_projection_key(
        provider_name="LOCAL_SENTENCE_TRANSFORMER",
        model_id="other-model",
        dimension=768,
    )
    assert a != c


def test_builder_dimension_mismatch_no_replace() -> None:
    store = RecordingStore()
    provider = FakeEmbeddingProvider(dimension=384)
    with pytest.raises(ProjectionRebuildError):
        rebuild_projection(
            repository=_demo_repo(),
            store=store,  # type: ignore[arg-type]
            provider=provider,
            policy_path=POLICY_PATH,
            expected_dimension=EXPECTED_EMBEDDING_DIMENSION,
        )
    assert store.replace_calls == []


def test_builder_embed_shape_mismatch_no_replace() -> None:
    store = RecordingStore()
    provider = FakeEmbeddingProvider(
        vectors_by_text={},
    )

    def _bad_embed(texts):  # type: ignore[no-untyped-def]
        return [[0.0] * 10 for _ in texts]

    provider.embed_documents = _bad_embed  # type: ignore[method-assign]
    # dimension property still 768, but vectors wrong length
    with pytest.raises(ProjectionRebuildError):
        rebuild_projection(
            repository=_demo_repo(),
            store=store,  # type: ignore[arg-type]
            provider=provider,
            policy_path=POLICY_PATH,
        )
    assert store.replace_calls == []


def test_builder_success_and_replace_failure() -> None:
    snapshot = load_snapshot(DEMO_SS_001_PATH)
    text = build_retrieval_text(snapshot)
    provider = FakeEmbeddingProvider(
        model_id="AI-ModelScope/gte-base-zh",
        vectors_by_text={text: make_test_vector(5)},
    )
    store = RecordingStore()
    key = rebuild_projection(
        repository=_demo_repo(),
        store=store,  # type: ignore[arg-type]
        provider=provider,
        policy_path=POLICY_PATH,
    )
    assert key
    assert len(store.replace_calls) == 1
    assert len(store.replace_calls[0]["documents"]) == 1

    store2 = RecordingStore(fail_replace=True)
    with pytest.raises(ProjectionRebuildError, match="replace"):
        rebuild_projection(
            repository=_demo_repo(),
            store=store2,  # type: ignore[arg-type]
            provider=provider,
            policy_path=POLICY_PATH,
        )
