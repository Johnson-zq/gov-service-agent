"""F08 LangGraph workflow build/compile/invoke tests (local, deterministic)."""

from __future__ import annotations

import copy

import pytest

from gov_service_agent.agent import (
    AgentPhase,
    AgentStateValidationError,
    WorkflowStatus,
    build_agent_workflow,
    create_initial_state,
    run_agent_workflow,
)


def test_build_agent_workflow_compiles():
    compiled = build_agent_workflow()
    assert compiled is not None


def test_normal_workflow_result():
    initial = create_initial_state("req-001", "synthetic workflow input")
    final = run_agent_workflow(initial)
    assert final["phase"] is AgentPhase.COMPLETED
    assert final["status"] is WorkflowStatus.COMPLETED
    assert final["error"] is None
    assert final["orchestration_trace"] == ["prepare", "complete"]
    assert final["request_id"] == "req-001"
    assert final["input_text"] == "synthetic workflow input"
    assert set(final.keys()) == {
        "request_id",
        "input_text",
        "phase",
        "status",
        "artifacts",
        "error",
        "orchestration_trace",
    }
    assert "next_node" not in final
    assert "business_id" not in final
    assert "candidate_business_id" not in final
    assert "materials" not in final
    assert "rule_result" not in final


def test_artifacts_preserved():
    artifacts = {"source": "synthetic", "nested": {"value": 1}}
    initial = create_initial_state(
        "req-001",
        "synthetic workflow input",
        artifacts=artifacts,
    )
    final = run_agent_workflow(initial)
    assert final["artifacts"] == {"source": "synthetic", "nested": {"value": 1}}


def test_trace_exact_order_and_semantics():
    final = run_agent_workflow(
        create_initial_state("req-001", "synthetic workflow input")
    )
    assert final["orchestration_trace"] == ["prepare", "complete"]
    assert "START" not in final["orchestration_trace"]
    assert "END" not in final["orchestration_trace"]
    assert "validation" not in final["orchestration_trace"]


def test_workflow_determinism_independent_states():
    a = create_initial_state("req-001", "synthetic workflow input")
    b = create_initial_state("req-001", "synthetic workflow input")
    assert a is not b
    result_a = run_agent_workflow(a)
    result_b = run_agent_workflow(b)
    assert result_a == result_b


def test_repeated_invocation_isolation():
    first = run_agent_workflow(
        create_initial_state("req-001", "synthetic workflow input")
    )
    second = run_agent_workflow(
        create_initial_state("req-002", "synthetic workflow input two")
    )
    assert first["request_id"] == "req-001"
    assert second["request_id"] == "req-002"
    assert first["orchestration_trace"] == ["prepare", "complete"]
    assert second["orchestration_trace"] == ["prepare", "complete"]


def test_caller_initial_state_not_mutated():
    initial = create_initial_state(
        "req-001",
        "synthetic workflow input",
        artifacts={"nested": {"items": [1, 2]}},
    )
    before = copy.deepcopy(initial)
    final = run_agent_workflow(initial)
    assert initial == before
    assert initial["phase"] is AgentPhase.RECEIVED
    assert final["phase"] is AgentPhase.COMPLETED
    assert initial["artifacts"]["nested"]["items"] == [1, 2]
    assert final is not initial


def test_invalid_initial_state_controlled_reject():
    initial = create_initial_state("req-001", "synthetic workflow input")
    before = copy.deepcopy(initial)
    bad = dict(initial)
    bad["phase"] = AgentPhase.COMPLETED
    bad["status"] = WorkflowStatus.RUNNING
    with pytest.raises(AgentStateValidationError):
        run_agent_workflow(bad)  # type: ignore[arg-type]
    assert initial == before


def test_invalid_extra_key_rejected_before_invoke():
    initial = create_initial_state("req-001", "synthetic workflow input")
    before = copy.deepcopy(initial)
    bad = dict(initial)
    bad["business_id"] = "FAKE_BUSINESS_ID"
    with pytest.raises(AgentStateValidationError):
        run_agent_workflow(bad)  # type: ignore[arg-type]
    assert initial == before


def test_no_auto_repair_plain_string_phase():
    initial = create_initial_state("req-001", "synthetic workflow input")
    bad = dict(initial)
    bad["phase"] = "received"
    with pytest.raises(AgentStateValidationError):
        run_agent_workflow(bad)  # type: ignore[arg-type]
