"""F03 Decision Graph Domain tests (written in Code; execute in Test stage)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from gov_service_agent.business_data.models import (
    BusinessSnapshot,
    snapshot_from_dict,
)
from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.business_graph import (
    DecisionEdge,
    DecisionGraph,
    DecisionNode,
    GraphBusinessRefError,
    GraphStructureError,
    SlotMatch,
    load_decision_graph,
    validate_graph_business_refs,
    validate_graph_structure,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = REPO_ROOT / "data" / "graphs" / "demo" / "social_security.json"
DEMO_SS_001_PATH = REPO_ROOT / "data" / "demo" / "demo_ss_001.json"


def _graph_dict() -> dict:
    return DecisionGraph.model_validate_json(
        GRAPH_PATH.read_text(encoding="utf-8")
    ).model_dump(mode="json")


def _validate_dict(data: dict) -> None:
    graph = DecisionGraph.model_validate(data)
    validate_graph_structure(graph)


def test_demo_social_security_graph_loads() -> None:
    graph = load_decision_graph(GRAPH_PATH)
    assert graph.schema_version == "1"
    assert graph.graph_id == "social_security"
    assert graph.graph_version == 1
    assert len(graph.nodes) == 7
    assert len(graph.edges) == 11
    terminal = next(
        n for n in graph.nodes if n.node_type.value == "TERMINAL_CANDIDATE"
    )
    assert terminal.candidate_business_id == "DEMO_SS_001"
    assert "DEMO_SS_002" not in GRAPH_PATH.read_text(encoding="utf-8")
    assert "政务服务中心" not in GRAPH_PATH.read_text(encoding="utf-8")
    assert "confirmed_business_id" not in GRAPH_PATH.read_text(encoding="utf-8")


def test_unknown_field_fails() -> None:
    data = _graph_dict()
    data["nodes"][0]["unexpected_field"] = "x"
    with pytest.raises(ValidationError):
        DecisionGraph.model_validate(data)


def test_duplicate_node_id_fails() -> None:
    data = _graph_dict()
    data["nodes"].append(deepcopy(data["nodes"][0]))
    with pytest.raises(GraphStructureError, match="duplicate node_id"):
        _validate_dict(data)


def test_duplicate_edge_id_fails() -> None:
    data = _graph_dict()
    data["edges"].append(deepcopy(data["edges"][0]))
    with pytest.raises(GraphStructureError, match="duplicate edge_id"):
        _validate_dict(data)


def test_second_entry_fails() -> None:
    data = _graph_dict()
    extra = deepcopy(data["nodes"][0])
    extra["node_id"] = "second_entry"
    data["nodes"].append(extra)
    with pytest.raises(GraphStructureError, match="exactly one ENTRY"):
        _validate_dict(data)


def test_dangling_edge_fails() -> None:
    data = _graph_dict()
    data["edges"][0]["to_node_id"] = "missing_node"
    with pytest.raises(GraphStructureError, match="unknown to_node_id"):
        _validate_dict(data)


def test_entry_incoming_fails() -> None:
    data = _graph_dict()
    for edge in data["edges"]:
        if edge["edge_id"] == "e-action-inquiry":
            edge["to_node_id"] = "social_security_entry"
            break
    with pytest.raises(GraphStructureError, match="no incoming"):
        _validate_dict(data)


@pytest.mark.parametrize("count", [0, 2])
def test_entry_forward_count_fails(count: int) -> None:
    data = _graph_dict()
    data["edges"] = [
        e for e in data["edges"] if e["edge_id"] != "e-entry-action"
    ]
    if count == 2:
        data["edges"].insert(
            0,
            {
                "edge_id": "e-entry-action-a",
                "from_node_id": "social_security_entry",
                "to_node_id": "social_security_action",
                "edge_kind": "ENTRY_FORWARD",
                "design_basis": "SYSTEM_DESIGNED",
                "match": None,
                "source_condition_refs": None,
            },
        )
        data["edges"].insert(
            1,
            {
                "edge_id": "e-entry-action-b",
                "from_node_id": "social_security_entry",
                "to_node_id": "social_security_action",
                "edge_kind": "ENTRY_FORWARD",
                "design_basis": "SYSTEM_DESIGNED",
                "match": None,
                "source_condition_refs": None,
            },
        )
    with pytest.raises(GraphStructureError, match="exactly one outgoing"):
        _validate_dict(data)


def test_terminal_outgoing_fails() -> None:
    data = _graph_dict()
    data["edges"].append(
        {
            "edge_id": "e-terminal-out",
            "from_node_id": "terminal_demo_ss_001",
            "to_node_id": "social_security_fallback",
            "edge_kind": "ENTRY_FORWARD",
            "design_basis": "SYSTEM_DESIGNED",
            "match": None,
            "source_condition_refs": None,
        }
    )
    with pytest.raises(GraphStructureError):
        _validate_dict(data)


def test_slot_mismatch_fails() -> None:
    data = _graph_dict()
    for edge in data["edges"]:
        if edge["edge_id"] == "e-action-payment":
            edge["match"]["slot"] = "wrong_slot"
            break
    with pytest.raises(GraphStructureError, match="match.slot"):
        _validate_dict(data)


def test_invalid_allowed_value_fails() -> None:
    data = _graph_dict()
    for edge in data["edges"]:
        if edge["edge_id"] == "e-action-payment":
            edge["match"]["value"] = "not_allowed"
            break
    with pytest.raises(GraphStructureError, match="not in allowed_values"):
        _validate_dict(data)


def test_allowed_value_without_edge_fails() -> None:
    data = _graph_dict()
    data["edges"] = [
        e for e in data["edges"] if e["edge_id"] != "e-action-other"
    ]
    with pytest.raises(GraphStructureError, match="exactly equal allowed_values"):
        _validate_dict(data)


def test_overlapping_match_value_fails() -> None:
    data = _graph_dict()
    data["edges"].append(
        {
            "edge_id": "e-action-payment-dup",
            "from_node_id": "social_security_action",
            "to_node_id": "payment_actor",
            "edge_kind": "SLOT_MATCH",
            "design_basis": "SYSTEM_DESIGNED",
            "match": {
                "slot": "service_action",
                "operator": "EQ",
                "value": "payment",
            },
            "source_condition_refs": None,
        }
    )
    with pytest.raises(GraphStructureError, match="duplicate match.value"):
        _validate_dict(data)


def test_cycle_fails() -> None:
    data = _graph_dict()
    # Add edge employment_type -> social_security_action would need a new
    # allowed value; instead redirect self_payment edge back creating cycle:
    # entry->action->payment_actor->employment_type, then add edge from
    # employment_type value to payment_actor — still DAG-ish.
    # Create: payment_actor -> social_security_action via replacing
    # e-payment-self target and adding edge action<-payment that cycles.
    for edge in data["edges"]:
        if edge["edge_id"] == "e-payment-self":
            edge["to_node_id"] = "social_security_action"
            break
    with pytest.raises(GraphStructureError, match="cycle"):
        _validate_dict(data)


def test_unreachable_node_fails() -> None:
    data = _graph_dict()
    data["nodes"].append(
        {
            "node_id": "orphan_fallback",
            "node_type": "FALLBACK",
            "design_basis": "SYSTEM_DESIGNED",
            "slot_name": None,
            "allowed_values": None,
            "question_text": None,
            "candidate_business_id": None,
            "unsupported_reason": None,
            "source_condition_refs": None,
        }
    )
    with pytest.raises(GraphStructureError, match="unreachable"):
        _validate_dict(data)


def test_cross_validation_terminal_pass() -> None:
    graph = load_decision_graph(GRAPH_PATH)
    repo = JsonBusinessRepository.from_paths([DEMO_SS_001_PATH])
    validate_graph_business_refs(graph, repo)


def test_cross_validation_unknown_terminal_fails() -> None:
    data = _graph_dict()
    for node in data["nodes"]:
        if node["node_id"] == "terminal_demo_ss_001":
            node["candidate_business_id"] = "DEMO_UNKNOWN_999"
            break
    graph = DecisionGraph.model_validate(data)
    validate_graph_structure(graph)
    repo = JsonBusinessRepository.from_paths([DEMO_SS_001_PATH])
    with pytest.raises(GraphBusinessRefError, match="unknown candidate"):
        validate_graph_business_refs(graph, repo)


def test_cross_validation_known_source_condition_pass() -> None:
    graph = load_decision_graph(GRAPH_PATH)
    repo = JsonBusinessRepository.from_paths([DEMO_SS_001_PATH])
    validate_graph_business_refs(graph, repo)


def test_cross_validation_unknown_condition_ref_fails() -> None:
    data = _graph_dict()
    for node in data["nodes"]:
        if node["node_id"] == "employment_type":
            node["source_condition_refs"][0]["condition_id"] = "cond-missing"
            break
    graph = DecisionGraph.model_validate(data)
    validate_graph_structure(graph)
    repo = JsonBusinessRepository.from_paths([DEMO_SS_001_PATH])
    with pytest.raises(GraphBusinessRefError, match="unknown condition_id"):
        validate_graph_business_refs(graph, repo)


def test_unsupported_schema_version_fails(tmp_path: Path) -> None:
    import json

    data = _graph_dict()
    data["schema_version"] = "99"
    path = tmp_path / "bad_schema.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(GraphStructureError, match="unsupported"):
        load_decision_graph(path)


def test_entry_forward_from_non_entry_fails() -> None:
    """RF-F03-001: ENTRY_FORWARD may only originate from ENTRY."""
    data = _graph_dict()
    data["edges"].append(
        {
            "edge_id": "e-bad-entry-forward-from-gate",
            "from_node_id": "social_security_action",
            "to_node_id": "payment_actor",
            "edge_kind": "ENTRY_FORWARD",
            "design_basis": "SYSTEM_DESIGNED",
            "match": None,
            "source_condition_refs": None,
        }
    )
    with pytest.raises(
        GraphStructureError, match="ENTRY_FORWARD from must be ENTRY"
    ):
        _validate_dict(data)


def test_slot_match_from_non_slot_gate_fails() -> None:
    """RF-F03-002: SLOT_MATCH may only originate from SLOT_GATE."""
    data = _graph_dict()
    data["edges"].append(
        {
            "edge_id": "e-bad-slot-match-from-fallback",
            "from_node_id": "social_security_fallback",
            "to_node_id": "unsupported_transfer",
            "edge_kind": "SLOT_MATCH",
            "design_basis": "SYSTEM_DESIGNED",
            "match": {
                "slot": "service_action",
                "operator": "EQ",
                "value": "payment",
            },
            "source_condition_refs": None,
        }
    )
    with pytest.raises(
        GraphStructureError, match="SLOT_MATCH from must be SLOT_GATE"
    ):
        _validate_dict(data)


@pytest.mark.parametrize(
    "kind,payload,refs",
    [
        (
            "node",
            {
                "node_id": "n-src-supported",
                "node_type": "SLOT_GATE",
                "design_basis": "SOURCE_SUPPORTED",
                "slot_name": "service_action",
                "allowed_values": ["payment"],
                "question_text": "测试提问？",
                "candidate_business_id": None,
                "unsupported_reason": None,
            },
            None,
        ),
        (
            "node",
            {
                "node_id": "n-src-supported",
                "node_type": "SLOT_GATE",
                "design_basis": "SOURCE_SUPPORTED",
                "slot_name": "service_action",
                "allowed_values": ["payment"],
                "question_text": "测试提问？",
                "candidate_business_id": None,
                "unsupported_reason": None,
            },
            [],
        ),
        (
            "edge",
            {
                "edge_id": "e-src-supported",
                "from_node_id": "a",
                "to_node_id": "b",
                "edge_kind": "SLOT_MATCH",
                "design_basis": "SOURCE_SUPPORTED",
                "match": {
                    "slot": "service_action",
                    "operator": "EQ",
                    "value": "payment",
                },
            },
            None,
        ),
        (
            "edge",
            {
                "edge_id": "e-src-supported",
                "from_node_id": "a",
                "to_node_id": "b",
                "edge_kind": "SLOT_MATCH",
                "design_basis": "SOURCE_SUPPORTED",
                "match": {
                    "slot": "service_action",
                    "operator": "EQ",
                    "value": "payment",
                },
            },
            [],
        ),
    ],
)
def test_source_supported_requires_refs(
    kind: str, payload: dict, refs: list | None
) -> None:
    """RF-F03-003: SOURCE_SUPPORTED rejects null and empty source_condition_refs."""
    payload = deepcopy(payload)
    payload["source_condition_refs"] = refs
    with pytest.raises(ValidationError):
        if kind == "node":
            DecisionNode.model_validate(payload)
        else:
            DecisionEdge.model_validate(payload)


def test_slot_match_non_eq_operator_fails() -> None:
    """RF-F03-004: phase-1 SlotMatch accepts EQ only."""
    with pytest.raises(ValidationError):
        SlotMatch.model_validate(
            {
                "slot": "service_action",
                "operator": "IN",
                "value": "payment",
            }
        )


def test_cross_validation_inactive_terminal_fails() -> None:
    """RF-F03-006: terminal candidate must reference ACTIVE business."""
    from gov_service_agent.business_data.models import load_snapshot

    demo = BusinessSnapshot.model_validate_json(
        DEMO_SS_001_PATH.read_text(encoding="utf-8")
    ).model_dump(mode="json")
    inactive = deepcopy(demo)
    inactive["business"]["business_id"] = "TEST_INACTIVE_001"
    inactive["business"]["status"] = "INACTIVE"
    inactive["business"]["data_scope"] = "TEST"
    inactive_snap = snapshot_from_dict(inactive)

    active = load_snapshot(DEMO_SS_001_PATH)
    repo = JsonBusinessRepository(
        {
            active.business.business_id: active,
            inactive_snap.business.business_id: inactive_snap,
        }
    )
    assert repo.has_business("TEST_INACTIVE_001") is True
    assert repo.get_business("TEST_INACTIVE_001").status.value == "INACTIVE"

    data = _graph_dict()
    for node in data["nodes"]:
        if node["node_id"] == "terminal_demo_ss_001":
            node["candidate_business_id"] = "TEST_INACTIVE_001"
            break
    # employment_type SOURCE_SUPPORTED refs still point at DEMO_SS_001 (ACTIVE).
    graph = DecisionGraph.model_validate(data)
    validate_graph_structure(graph)
    with pytest.raises(GraphBusinessRefError, match="expected ACTIVE"):
        validate_graph_business_refs(graph, repo)
