"""F08 Agent State contract tests (no network / DB / Redis / LLM)."""

from __future__ import annotations

import copy
import json
from datetime import datetime
from enum import Enum
from pathlib import Path

import pytest

from gov_service_agent.agent import (
    AgentPhase,
    AgentStateValidationError,
    WorkflowErrorCode,
    WorkflowStatus,
    create_initial_state,
    validate_agent_state,
)


def _valid_base(**overrides):
    state = create_initial_state("req-001", "synthetic input")
    state = dict(state)
    state.update(overrides)
    return state


def test_agent_phase_values():
    assert AgentPhase.RECEIVED.value == "received"
    assert AgentPhase.ORCHESTRATING.value == "orchestrating"
    assert AgentPhase.COMPLETED.value == "completed"
    assert AgentPhase.FAILED.value == "failed"


def test_workflow_status_values():
    assert WorkflowStatus.RUNNING.value == "running"
    assert WorkflowStatus.COMPLETED.value == "completed"
    assert WorkflowStatus.FAILED.value == "failed"


def test_workflow_error_code_values():
    assert WorkflowErrorCode.INVALID_STATE.value == "invalid_state"


def test_create_initial_state_defaults():
    state = create_initial_state("req-001", "synthetic input")
    assert state["request_id"] == "req-001"
    assert state["input_text"] == "synthetic input"
    assert state["phase"] is AgentPhase.RECEIVED
    assert state["status"] is WorkflowStatus.RUNNING
    assert state["artifacts"] == {}
    assert state["error"] is None
    assert state["orchestration_trace"] == []


def test_default_artifacts_and_trace_are_fresh():
    a = create_initial_state("req-a", "synthetic a")
    b = create_initial_state("req-b", "synthetic b")
    assert a["artifacts"] is not b["artifacts"]
    assert a["orchestration_trace"] is not b["orchestration_trace"]
    a["artifacts"]["x"] = 1
    a["orchestration_trace"].append("prepare")
    assert "x" not in b["artifacts"]
    assert b["orchestration_trace"] == []


def test_request_id_valid_and_max_len():
    create_initial_state("a" * 128, "synthetic input")
    with pytest.raises(AgentStateValidationError):
        create_initial_state("", "synthetic input")
    with pytest.raises(AgentStateValidationError):
        create_initial_state("   ", "synthetic input")
    with pytest.raises(AgentStateValidationError):
        create_initial_state("a" * 129, "synthetic input")
    with pytest.raises(AgentStateValidationError):
        validate_agent_state(_valid_base(request_id=123))  # type: ignore[arg-type]


def test_input_text_validation():
    create_initial_state("req-001", "ok")
    with pytest.raises(AgentStateValidationError):
        create_initial_state("req-001", "")
    with pytest.raises(AgentStateValidationError):
        create_initial_state("req-001", "   ")
    with pytest.raises(AgentStateValidationError):
        validate_agent_state(_valid_base(input_text=1))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field",
    [
        "request_id",
        "input_text",
        "phase",
        "status",
        "artifacts",
        "error",
        "orchestration_trace",
    ],
)
def test_missing_required_fields_reject(field: str):
    state = _valid_base()
    del state[field]
    with pytest.raises(AgentStateValidationError):
        validate_agent_state(state)


@pytest.mark.parametrize(
    "extra_key,extra_value",
    [
        ("unexpected_field", "x"),
        ("api_key", "FAKE_API_KEY"),
        ("reasoning", "FAKE_REASONING"),
        ("business_id", "FAKE_BUSINESS_ID"),
    ],
)
def test_unknown_top_level_keys_reject(extra_key: str, extra_value: str):
    state = _valid_base()
    state[extra_key] = extra_value
    with pytest.raises(AgentStateValidationError):
        validate_agent_state(state)


def test_plain_string_phase_and_status_reject():
    with pytest.raises(AgentStateValidationError):
        validate_agent_state(_valid_base(phase="received"))
    with pytest.raises(AgentStateValidationError):
        validate_agent_state(_valid_base(status="running"))


def test_lifecycle_valid_combinations():
    validate_agent_state(
        _valid_base(
            phase=AgentPhase.RECEIVED,
            status=WorkflowStatus.RUNNING,
            error=None,
        )
    )
    validate_agent_state(
        _valid_base(
            phase=AgentPhase.ORCHESTRATING,
            status=WorkflowStatus.RUNNING,
            error=None,
            orchestration_trace=["prepare"],
        )
    )
    validate_agent_state(
        _valid_base(
            phase=AgentPhase.COMPLETED,
            status=WorkflowStatus.COMPLETED,
            error=None,
            orchestration_trace=["prepare", "complete"],
        )
    )
    validate_agent_state(
        _valid_base(
            phase=AgentPhase.FAILED,
            status=WorkflowStatus.FAILED,
            error={
                "code": WorkflowErrorCode.INVALID_STATE,
                "message": "synthetic safe failure",
            },
        )
    )


@pytest.mark.parametrize(
    "phase,status,error",
    [
        (AgentPhase.COMPLETED, WorkflowStatus.RUNNING, None),
        (AgentPhase.RECEIVED, WorkflowStatus.COMPLETED, None),
        (AgentPhase.FAILED, WorkflowStatus.RUNNING, None),
        (AgentPhase.ORCHESTRATING, WorkflowStatus.FAILED, None),
        (AgentPhase.FAILED, WorkflowStatus.FAILED, None),
        (
            AgentPhase.COMPLETED,
            WorkflowStatus.COMPLETED,
            {
                "code": WorkflowErrorCode.INVALID_STATE,
                "message": "synthetic safe failure",
            },
        ),
    ],
)
def test_lifecycle_invalid_combinations_reject(phase, status, error):
    with pytest.raises(AgentStateValidationError):
        validate_agent_state(_valid_base(phase=phase, status=status, error=error))


def test_workflow_error_shape_invalid():
    base_failed = dict(
        _valid_base(
            phase=AgentPhase.FAILED,
            status=WorkflowStatus.FAILED,
            error={
                "code": WorkflowErrorCode.INVALID_STATE,
                "message": "synthetic safe failure",
            },
        )
    )
    with pytest.raises(AgentStateValidationError):
        bad = dict(base_failed)
        bad["error"] = {"message": "synthetic safe failure"}
        validate_agent_state(bad)
    with pytest.raises(AgentStateValidationError):
        bad = dict(base_failed)
        bad["error"] = {"code": WorkflowErrorCode.INVALID_STATE}
        validate_agent_state(bad)
    with pytest.raises(AgentStateValidationError):
        bad = dict(base_failed)
        bad["error"] = {
            "code": WorkflowErrorCode.INVALID_STATE,
            "message": "synthetic safe failure",
            "extra": "x",
        }
        validate_agent_state(bad)
    with pytest.raises(AgentStateValidationError):
        bad = dict(base_failed)
        bad["error"] = {"code": "invalid_state", "message": "synthetic safe failure"}
        validate_agent_state(bad)
    with pytest.raises(AgentStateValidationError):
        bad = dict(base_failed)
        bad["error"] = {"code": WorkflowErrorCode.INVALID_STATE, "message": "   "}
        validate_agent_state(bad)
    with pytest.raises(AgentStateValidationError):
        bad = dict(base_failed)
        bad["error"] = {"code": WorkflowErrorCode.INVALID_STATE, "message": 1}
        validate_agent_state(bad)


@pytest.mark.parametrize(
    "value",
    [None, "abc", True, False, 0, 123, -10, 0.0, 1.25, -9.5],
)
def test_artifacts_scalar_pass(value):
    validate_agent_state(_valid_base(artifacts={"v": value}))


def test_finite_and_non_finite_floats():
    validate_agent_state(_valid_base(artifacts={"v": 1.0}))
    with pytest.raises(AgentStateValidationError):
        validate_agent_state(_valid_base(artifacts={"v": float("nan")}))
    with pytest.raises(AgentStateValidationError):
        validate_agent_state(_valid_base(artifacts={"v": float("inf")}))
    with pytest.raises(AgentStateValidationError):
        validate_agent_state(_valid_base(artifacts={"v": float("-inf")}))


def test_nested_json_safe_pass():
    artifacts = {
        "level1": {
            "items": [1, "x", True, None, {"score": 0.5}],
        }
    }
    validate_agent_state(_valid_base(artifacts=artifacts))


@pytest.mark.parametrize(
    "bad",
    [
        (1, 2),
        {1, 2},
        b"x",
        bytearray(b"x"),
        Path("."),
        datetime(2026, 1, 1),
        ValueError("x"),
        object(),
    ],
)
def test_json_safe_fail_types(bad):
    with pytest.raises(AgentStateValidationError):
        validate_agent_state(_valid_base(artifacts={"v": bad}))


def test_dummy_class_instance_reject():
    class Dummy:
        pass

    with pytest.raises(AgentStateValidationError):
        validate_agent_state(_valid_base(artifacts={"v": Dummy()}))


def test_arbitrary_enum_in_artifacts_reject():
    class DemoEnum(Enum):
        A = "a"

    with pytest.raises(AgentStateValidationError):
        validate_agent_state(_valid_base(artifacts={"v": DemoEnum.A}))
    with pytest.raises(AgentStateValidationError):
        validate_agent_state(_valid_base(artifacts={"v": AgentPhase.RECEIVED}))


def test_dict_key_strictness():
    with pytest.raises(AgentStateValidationError):
        validate_agent_state(_valid_base(artifacts={1: "x"}))  # type: ignore[dict-item]
    with pytest.raises(AgentStateValidationError):
        validate_agent_state(_valid_base(artifacts={AgentPhase.RECEIVED: "x"}))
    validate_agent_state(_valid_base(artifacts={"ok": "x"}))


def test_list_allowed_tuple_rejected():
    validate_agent_state(_valid_base(artifacts={"items": [1, 2]}))
    with pytest.raises(AgentStateValidationError):
        validate_agent_state(_valid_base(artifacts={"items": (1, 2)}))


def test_json_dumps_allow_nan_false():
    state = create_initial_state("req-001", "synthetic input", artifacts={"n": 1.5})
    payload = json.dumps(state, allow_nan=False)
    assert isinstance(payload, str)
    assert "nan" not in payload.lower()


def test_artifacts_defensive_deep_copy_both_directions():
    caller = {"nested": {"items": [1, 2]}}
    state = create_initial_state("req-001", "synthetic input", artifacts=caller)
    caller["nested"]["items"].append(3)
    assert state["artifacts"]["nested"]["items"] == [1, 2]
    state["artifacts"]["nested"]["items"].append(9)
    assert caller["nested"]["items"] == [1, 2, 3]


@pytest.mark.parametrize(
    "trace",
    [
        [],
        ["prepare"],
        ["prepare", "complete"],
    ],
)
def test_trace_valid(trace):
    phase = AgentPhase.RECEIVED if not trace else (
        AgentPhase.ORCHESTRATING if trace == ["prepare"] else AgentPhase.COMPLETED
    )
    status = (
        WorkflowStatus.RUNNING
        if phase is not AgentPhase.COMPLETED
        else WorkflowStatus.COMPLETED
    )
    validate_agent_state(
        _valid_base(phase=phase, status=status, orchestration_trace=trace)
    )


@pytest.mark.parametrize(
    "trace",
    [
        ("prepare",),
        [""],
        ["   "],
        [1],
        ["prepare", 2],
    ],
)
def test_trace_invalid_reject(trace):
    with pytest.raises(AgentStateValidationError):
        validate_agent_state(_valid_base(orchestration_trace=trace))


def test_validation_error_does_not_leak_input_text():
    sentinel = "SENSITIVE_SENTINEL_SHOULD_NOT_LEAK"
    state = _valid_base(input_text=sentinel)
    state["unexpected_field"] = "x"
    with pytest.raises(AgentStateValidationError) as exc_info:
        validate_agent_state(state)
    text = f"{exc_info.value!s}{exc_info.value!r}"
    assert sentinel not in text


def test_validation_error_does_not_leak_artifacts():
    sentinel = "SENSITIVE_ARTIFACT_SENTINEL"
    state = _valid_base(artifacts={"secretish": sentinel})
    state["unexpected_field"] = "x"
    with pytest.raises(AgentStateValidationError) as exc_info:
        validate_agent_state(state)
    text = f"{exc_info.value!s}{exc_info.value!r}"
    assert sentinel not in text
