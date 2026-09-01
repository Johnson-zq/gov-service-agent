"""F04 Rule Selection / Readiness tests (written in Code; run in Test)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from gov_service_agent.business_data.models import (
    VerificationStatus,
    load_snapshot,
    snapshot_from_dict,
)
from gov_service_agent.business_data.repository import (
    BusinessNotFoundError,
    JsonBusinessRepository,
)
from gov_service_agent.business_graph import (
    DesignBasis,
    load_decision_graph,
)
from gov_service_agent.business_rules import (
    RuleSelectionStatus,
    select_executable_rules,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_SS_001_PATH = REPO_ROOT / "data" / "demo" / "demo_ss_001.json"
GRAPH_PATH = REPO_ROOT / "data" / "graphs" / "demo" / "social_security.json"


def _demo_repo() -> JsonBusinessRepository:
    return JsonBusinessRepository.from_paths([DEMO_SS_001_PATH])


def test_demo_ss_001_no_rules() -> None:
    result = select_executable_rules("DEMO_SS_001", _demo_repo())
    assert result.business_id == "DEMO_SS_001"
    assert result.status == RuleSelectionStatus.NO_RULES
    assert result.selected_rule_ids == []
    assert result.skipped_non_executable_count == 7


def test_verified_executable_fixture_selected() -> None:
    """Layer1/Layer2 need not be VERIFIED for Layer3 selection."""
    data = load_snapshot(DEMO_SS_001_PATH).model_dump(mode="json")
    cond = deepcopy(data["conditions"][0])
    cond["condition_id"] = "cond-fixture-verified-exec"
    assert cond["source_status"] == VerificationStatus.SOURCE_EXPLICIT.value
    assert cond["normalized_status"] == VerificationStatus.SYSTEM_DERIVED.value
    cond["executable"] = {
        "operator": "in",
        "verification_status": "VERIFIED",
        "usable_by_rule_engine": True,
    }
    data["conditions"].append(cond)
    snapshot = snapshot_from_dict(data)
    repo = JsonBusinessRepository(
        {snapshot.business.business_id: snapshot}
    )
    result = select_executable_rules("DEMO_SS_001", repo)
    assert result.status == RuleSelectionStatus.RULES_AVAILABLE_UNEVALUATED
    assert result.selected_rule_ids == ["cond-fixture-verified-exec"]
    assert result.skipped_non_executable_count == 7


def test_null_executable_skipped() -> None:
    snapshot = load_snapshot(DEMO_SS_001_PATH)
    assert all(c.executable is None for c in snapshot.conditions)
    result = select_executable_rules("DEMO_SS_001", _demo_repo())
    assert result.status == RuleSelectionStatus.NO_RULES


def test_to_confirm_conditions_not_selected() -> None:
    snapshot = load_snapshot(DEMO_SS_001_PATH)
    to_confirm = [
        c
        for c in snapshot.conditions
        if c.source_status == VerificationStatus.TO_CONFIRM
    ]
    assert len(to_confirm) == 4
    assert all(c.executable is None for c in to_confirm)
    result = select_executable_rules("DEMO_SS_001", _demo_repo())
    assert result.selected_rule_ids == []


def test_unknown_business_raises() -> None:
    with pytest.raises(BusinessNotFoundError):
        select_executable_rules("DOES_NOT_EXIST", _demo_repo())


def test_source_supported_graph_edges_do_not_create_rules() -> None:
    graph = load_decision_graph(GRAPH_PATH)
    supported_edges = [
        e
        for e in graph.edges
        if e.design_basis == DesignBasis.SOURCE_SUPPORTED
    ]
    assert len(supported_edges) >= 1
    result = select_executable_rules("DEMO_SS_001", _demo_repo())
    assert result.status == RuleSelectionStatus.NO_RULES
    assert result.selected_rule_ids == []
    assert result.skipped_non_executable_count == 7


def test_selection_has_no_pass_fail_attributes() -> None:
    result = select_executable_rules("DEMO_SS_001", _demo_repo())
    assert not hasattr(result, "pass_fail")
    dumped = result.model_dump()
    assert "PASS" not in dumped.values()
    assert set(dumped.keys()) == {
        "business_id",
        "status",
        "selected_rule_ids",
        "skipped_non_executable_count",
    }
