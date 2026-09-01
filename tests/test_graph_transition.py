"""F04 Deterministic Graph Transition tests (written in Code; run in Test)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from gov_service_agent.business_graph import (
    DesignBasis,
    TransitionNodeNotFoundError,
    TransitionResult,
    TransitionStatus,
    advance_until_blocked,
    load_decision_graph,
    step,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = REPO_ROOT / "data" / "graphs" / "demo" / "social_security.json"


@pytest.fixture
def graph():
    return load_decision_graph(GRAPH_PATH)


def test_entry_step_advances_to_action(graph) -> None:
    result = step(graph, "social_security_entry", {})
    assert result.status == TransitionStatus.ADVANCED
    assert result.current_node_id == "social_security_action"
    assert result.visited_node_ids == [
        "social_security_entry",
        "social_security_action",
    ]
    assert result.traversed_edge_ids == ["e-entry-action"]


def test_missing_service_action_need_slot(graph) -> None:
    result = step(graph, "social_security_action", {})
    assert result.status == TransitionStatus.NEED_SLOT
    assert result.required_slot == "service_action"
    assert result.allowed_values is not None
    assert "payment" in result.allowed_values
    assert result.question_text
    assert result.invalid_value is None
    assert result.candidate_business_id is None
    assert result.visited_node_ids == ["social_security_action"]
    assert result.traversed_edge_ids == []


def test_invalid_service_action(graph) -> None:
    result = step(
        graph,
        "social_security_action",
        {"service_action": "not_a_valid_value"},
    )
    assert result.status == TransitionStatus.INVALID_SLOT
    assert result.required_slot == "service_action"
    assert result.invalid_value == "not_a_valid_value"
    assert result.allowed_values is not None
    assert result.question_text
    assert result.candidate_business_id is None


def test_payment_advances_to_payment_actor(graph) -> None:
    result = step(
        graph,
        "social_security_action",
        {"service_action": "payment"},
    )
    assert result.status == TransitionStatus.ADVANCED
    assert result.current_node_id == "payment_actor"
    assert result.traversed_edge_ids == ["e-action-payment"]


def test_complete_slots_advance_to_terminal(graph) -> None:
    slots = {
        "service_action": "payment",
        "payment_actor": "self_payment",
        "employment_type": "other_flexible_employment",
    }
    result = advance_until_blocked(graph, "social_security_entry", slots)
    assert result.status == TransitionStatus.TERMINAL_CANDIDATE
    assert result.candidate_business_id == "DEMO_SS_001"
    assert result.current_node_id == "terminal_demo_ss_001"
    # TransitionResult must not carry Rule Selection fields
    assert not hasattr(result, "rule_selection_status")
    assert not hasattr(result, "selected_rule_ids")


def test_transfer_unsupported(graph) -> None:
    result = advance_until_blocked(
        graph,
        "social_security_entry",
        {"service_action": "transfer"},
    )
    assert result.status == TransitionStatus.UNSUPPORTED
    assert result.unsupported_reason
    assert result.candidate_business_id is None
    assert result.current_node_id == "unsupported_transfer"
    assert result.visited_node_ids == [
        "social_security_entry",
        "social_security_action",
        "unsupported_transfer",
    ]
    assert result.traversed_edge_ids == [
        "e-entry-action",
        "e-action-transfer",
    ]


def test_inquiry_fallback(graph) -> None:
    result = advance_until_blocked(
        graph,
        "social_security_entry",
        {"service_action": "inquiry"},
    )
    assert result.status == TransitionStatus.FALLBACK
    assert result.current_node_id == "social_security_fallback"
    assert result.candidate_business_id is None


def test_employer_payment_fallback(graph) -> None:
    result = advance_until_blocked(
        graph,
        "social_security_entry",
        {
            "service_action": "payment",
            "payment_actor": "employer_payment",
        },
    )
    assert result.status == TransitionStatus.FALLBACK
    assert result.current_node_id == "social_security_fallback"


def test_partial_slots_need_employment_type(graph) -> None:
    result = advance_until_blocked(
        graph,
        "social_security_entry",
        {
            "service_action": "payment",
            "payment_actor": "self_payment",
        },
    )
    assert result.status == TransitionStatus.NEED_SLOT
    assert result.required_slot == "employment_type"
    assert result.current_node_id == "employment_type"
    assert result.visited_node_ids == [
        "social_security_entry",
        "social_security_action",
        "payment_actor",
        "employment_type",
    ]
    assert result.traversed_edge_ids == [
        "e-entry-action",
        "e-action-payment",
        "e-payment-self",
    ]


def test_complete_path_trace_order(graph) -> None:
    slots = {
        "service_action": "payment",
        "payment_actor": "self_payment",
        "employment_type": "other_flexible_employment",
    }
    result = advance_until_blocked(graph, "social_security_entry", slots)
    assert result.visited_node_ids == [
        "social_security_entry",
        "social_security_action",
        "payment_actor",
        "employment_type",
        "terminal_demo_ss_001",
    ]
    assert result.traversed_edge_ids == [
        "e-entry-action",
        "e-action-payment",
        "e-payment-self",
        "e-emp-other-flex",
    ]


def test_partial_advance_trace_keeps_history(graph) -> None:
    result = advance_until_blocked(
        graph,
        "social_security_entry",
        {"service_action": "payment"},
    )
    assert result.status == TransitionStatus.NEED_SLOT
    assert result.required_slot == "payment_actor"
    assert result.visited_node_ids == [
        "social_security_entry",
        "social_security_action",
        "payment_actor",
    ]
    assert result.traversed_edge_ids == [
        "e-entry-action",
        "e-action-payment",
    ]


def test_unknown_node_raises(graph) -> None:
    with pytest.raises(TransitionNodeNotFoundError):
        step(graph, "does_not_exist", {})


def test_graph_immutable(graph) -> None:
    before = graph.model_dump(mode="json")
    advance_until_blocked(
        graph,
        "social_security_entry",
        {
            "service_action": "payment",
            "payment_actor": "self_payment",
            "employment_type": "self_employed_without_employees",
        },
    )
    after = graph.model_dump(mode="json")
    assert before == after


def test_slots_immutable(graph) -> None:
    slots = {
        "service_action": "payment",
        "payment_actor": "self_payment",
        "employment_type": "other_flexible_employment",
    }
    before = dict(slots)
    advance_until_blocked(graph, "social_security_entry", slots)
    assert dict(slots) == before


def test_extra_slot_keys_ignored(graph) -> None:
    result = step(
        graph,
        "social_security_action",
        {
            "service_action": "payment",
            "unrelated_future_slot": "x",
        },
    )
    assert result.status == TransitionStatus.ADVANCED
    assert result.current_node_id == "payment_actor"


def test_already_on_terminal(graph) -> None:
    result = step(graph, "terminal_demo_ss_001", {})
    assert result.status == TransitionStatus.TERMINAL_CANDIDATE
    assert result.candidate_business_id == "DEMO_SS_001"
    assert result.visited_node_ids == ["terminal_demo_ss_001"]
    assert result.traversed_edge_ids == []


def test_step_on_unsupported_current_node(graph) -> None:
    result = step(graph, "unsupported_transfer", {})
    assert result.status == TransitionStatus.UNSUPPORTED
    assert result.current_node_id == "unsupported_transfer"
    assert result.unsupported_reason
    assert result.visited_node_ids == ["unsupported_transfer"]
    assert result.traversed_edge_ids == []
    assert result.candidate_business_id is None


def test_step_on_fallback_current_node(graph) -> None:
    result = step(graph, "social_security_fallback", {})
    assert result.status == TransitionStatus.FALLBACK
    assert result.current_node_id == "social_security_fallback"
    assert result.visited_node_ids == ["social_security_fallback"]
    assert result.traversed_edge_ids == []
    assert result.candidate_business_id is None
    assert result.unsupported_reason is None


def test_partial_advance_invalid_slot_trace_keeps_history(graph) -> None:
    invalid_value = "not_a_valid_payment_actor"
    result = advance_until_blocked(
        graph,
        "social_security_entry",
        {
            "service_action": "payment",
            "payment_actor": invalid_value,
        },
    )
    assert result.status == TransitionStatus.INVALID_SLOT
    assert result.current_node_id == "payment_actor"
    assert result.required_slot == "payment_actor"
    assert result.invalid_value == invalid_value
    assert result.allowed_values is not None
    assert set(result.allowed_values) == {
        "self_payment",
        "employer_payment",
        "other",
    }
    assert result.question_text
    assert result.visited_node_ids == [
        "social_security_entry",
        "social_security_action",
        "payment_actor",
    ]
    assert result.traversed_edge_ids == [
        "e-entry-action",
        "e-action-payment",
    ]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            {
                "status": TransitionStatus.NEED_SLOT,
                "current_node_id": "gate",
                "visited_node_ids": ["gate"],
                "traversed_edge_ids": [],
                "required_slot": None,
                "allowed_values": ["x"],
                "question_text": "q?",
            },
            id="need_slot_missing_required_slot",
        ),
        pytest.param(
            {
                "status": TransitionStatus.INVALID_SLOT,
                "current_node_id": "gate",
                "visited_node_ids": ["gate"],
                "traversed_edge_ids": [],
                "required_slot": "slot",
                "invalid_value": None,
                "allowed_values": ["x"],
                "question_text": "q?",
            },
            id="invalid_slot_missing_invalid_value",
        ),
        pytest.param(
            {
                "status": TransitionStatus.TERMINAL_CANDIDATE,
                "current_node_id": "terminal",
                "visited_node_ids": ["terminal"],
                "traversed_edge_ids": [],
                "candidate_business_id": None,
            },
            id="terminal_missing_candidate",
        ),
        pytest.param(
            {
                "status": TransitionStatus.UNSUPPORTED,
                "current_node_id": "unsupported",
                "visited_node_ids": ["unsupported"],
                "traversed_edge_ids": [],
                "unsupported_reason": None,
            },
            id="unsupported_missing_reason",
        ),
        pytest.param(
            {
                "status": TransitionStatus.FALLBACK,
                "current_node_id": "fallback",
                "visited_node_ids": ["fallback"],
                "traversed_edge_ids": [],
                "candidate_business_id": "DEMO_SS_001",
            },
            id="fallback_with_candidate",
        ),
        pytest.param(
            {
                "status": TransitionStatus.ADVANCED,
                "current_node_id": "c",
                "visited_node_ids": ["a", "b"],
                "traversed_edge_ids": ["e1"],
            },
            id="current_not_equal_last_visited",
        ),
        pytest.param(
            {
                "status": TransitionStatus.ADVANCED,
                "current_node_id": "b",
                "visited_node_ids": ["a", "b"],
                "traversed_edge_ids": [],
            },
            id="trace_edge_count_mismatch",
        ),
        pytest.param(
            {
                "status": TransitionStatus.TERMINAL_CANDIDATE,
                "current_node_id": "terminal",
                "visited_node_ids": ["terminal"],
                "traversed_edge_ids": [],
                "candidate_business_id": "DEMO_SS_001",
                "required_slot": "slot",
            },
            id="terminal_with_required_slot",
        ),
        pytest.param(
            {
                "status": TransitionStatus.TERMINAL_CANDIDATE,
                "current_node_id": "terminal",
                "visited_node_ids": ["terminal"],
                "traversed_edge_ids": [],
                "candidate_business_id": "DEMO_SS_001",
                "unsupported_reason": "reason",
            },
            id="terminal_with_unsupported_reason",
        ),
    ],
)
def test_transition_result_contract_rejects_invalid_payload(payload) -> None:
    with pytest.raises(ValidationError):
        TransitionResult(**payload)


def test_source_supported_edges_exist_but_unused_by_transition_status(
    graph,
) -> None:
    """SOURCE_SUPPORTED is design metadata; Transition still uses EdgeKind only."""
    supported = [
        e
        for e in graph.edges
        if e.design_basis == DesignBasis.SOURCE_SUPPORTED
    ]
    assert len(supported) >= 1
    result = advance_until_blocked(
        graph,
        "social_security_entry",
        {
            "service_action": "payment",
            "payment_actor": "self_payment",
            "employment_type": "other_flexible_employment",
        },
    )
    assert result.status == TransitionStatus.TERMINAL_CANDIDATE
