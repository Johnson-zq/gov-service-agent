"""F03 JsonBusinessRepository tests (written in Code; execute in Test stage)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gov_service_agent.business_data.models import (
    VerificationStatus,
    load_snapshot,
)
from gov_service_agent.business_data.repository import (
    BusinessNotFoundError,
    ConsumptionMode,
    DuplicateBusinessError,
    JsonBusinessRepository,
    RelationType,
    TargetType,
)
from gov_service_agent.business_graph import (
    load_decision_graph,
    validate_graph_business_refs,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_SS_001_PATH = REPO_ROOT / "data" / "demo" / "demo_ss_001.json"
GRAPH_PATH = REPO_ROOT / "data" / "graphs" / "demo" / "social_security.json"


def _demo_repo() -> JsonBusinessRepository:
    return JsonBusinessRepository.from_paths([DEMO_SS_001_PATH])


def test_demo_ss_001_exact_load() -> None:
    repo = _demo_repo()
    business = repo.get_business("DEMO_SS_001")
    assert business.business_id == "DEMO_SS_001"
    assert business.canonical_name == "灵活就业人员社会保险费申报缴费"
    assert repo.has_business("DEMO_SS_001") is True


def test_unknown_business_raises() -> None:
    repo = _demo_repo()
    with pytest.raises(BusinessNotFoundError):
        repo.get_business("DOES_NOT_EXIST")


def test_duplicate_business_raises() -> None:
    with pytest.raises(DuplicateBusinessError):
        JsonBusinessRepository.from_paths(
            [DEMO_SS_001_PATH, DEMO_SS_001_PATH]
        )


def test_get_materials_id_card() -> None:
    repo = _demo_repo()
    materials = repo.get_materials("DEMO_SS_001")
    texts = [m.source_text for m in materials]
    assert "身份证" in texts
    assert any(m.material_id == "mat-id-card" for m in materials)


def test_get_handling_location_jianguo() -> None:
    repo = _demo_repo()
    locations = repo.get_handling_locations("DEMO_SS_001")
    assert len(locations) == 1
    assert locations[0].name == (
        "国家税务总局杭州市上城区税务局建国南路办公区"
    )
    assert "建国南路" in locations[0].address


def test_no_service_center_in_public_locations() -> None:
    repo = _demo_repo()
    for loc in repo.get_handling_locations("DEMO_SS_001"):
        assert "政务服务中心" not in loc.name
        assert "政务服务中心" not in loc.address
    raw = DEMO_SS_001_PATH.read_text(encoding="utf-8")
    assert "政务服务中心" not in raw


def test_public_conditions_exclude_to_confirm() -> None:
    repo = _demo_repo()
    public = repo.get_conditions(
        "DEMO_SS_001", consumption=ConsumptionMode.PUBLIC
    )
    assert len(public) == 3
    assert all(
        c.source_status == VerificationStatus.SOURCE_EXPLICIT for c in public
    )
    assert all(
        c.source_status != VerificationStatus.TO_CONFIRM for c in public
    )


def test_internal_conditions_include_to_confirm() -> None:
    repo = _demo_repo()
    internal = repo.get_conditions(
        "DEMO_SS_001", consumption=ConsumptionMode.INTERNAL
    )
    assert len(internal) == 7
    to_confirm = [
        c
        for c in internal
        if c.source_status == VerificationStatus.TO_CONFIRM
    ]
    assert len(to_confirm) == 4


def test_default_consumption_is_public() -> None:
    repo = _demo_repo()
    defaulted = repo.get_conditions("DEMO_SS_001")
    explicit = repo.get_conditions(
        "DEMO_SS_001", consumption=ConsumptionMode.PUBLIC
    )
    assert len(defaulted) == len(explicit) == 3


def test_public_relations_exclude_to_confirm_conditions() -> None:
    repo = _demo_repo()
    relations = repo.list_relations(
        "DEMO_SS_001", consumption=ConsumptionMode.PUBLIC
    )
    condition_rels = [
        r
        for r in relations
        if r.relation_type == RelationType.HAS_CONDITION
    ]
    assert len(condition_rels) == 3
    condition_ids = {r.target_id for r in condition_rels}
    assert condition_ids == {
        "cond-applicant-01",
        "cond-applicant-02",
        "cond-applicant-03",
    }
    assert "cond-tc-01" not in condition_ids


def test_has_material_relation() -> None:
    repo = _demo_repo()
    relations = repo.list_relations("DEMO_SS_001")
    material_rels = [
        r for r in relations if r.relation_type == RelationType.HAS_MATERIAL
    ]
    assert any(
        r.target_type == TargetType.MATERIAL and r.target_id == "mat-id-card"
        for r in material_rels
    )


def test_internal_relations_include_to_confirm_conditions() -> None:
    repo = _demo_repo()
    relations = repo.list_relations(
        "DEMO_SS_001", consumption=ConsumptionMode.INTERNAL
    )
    condition_rels = [
        r
        for r in relations
        if r.relation_type == RelationType.HAS_CONDITION
    ]
    assert len(condition_rels) == 7


def test_has_condition() -> None:
    repo = _demo_repo()
    assert repo.has_condition("DEMO_SS_001", "cond-applicant-01") is True
    assert repo.has_condition("DEMO_SS_001", "missing") is False


def test_graph_and_repo_cross_validation() -> None:
    graph = load_decision_graph(GRAPH_PATH)
    repo = _demo_repo()
    validate_graph_business_refs(graph, repo)


def test_public_channels_and_legal_basis_present() -> None:
    repo = _demo_repo()
    channels = repo.get_channels("DEMO_SS_001")
    assert len(channels) == 6
    legal = repo.get_legal_basis("DEMO_SS_001")
    assert len(legal) == 1
    assert legal[0].legal_basis_id == "legal-social-insurance-law-60"


def test_snapshot_file_unchanged_after_repository_reads() -> None:
    """Ensure F02 demo still loads; repository does not mutate snapshot file."""
    before = load_snapshot(DEMO_SS_001_PATH)
    repo = _demo_repo()
    _ = repo.get_conditions("DEMO_SS_001")
    after = load_snapshot(DEMO_SS_001_PATH)
    assert before.business.business_id == after.business.business_id
    assert len(before.conditions) == len(after.conditions) == 7
