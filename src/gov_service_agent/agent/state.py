"""Agent State contract, validation, and initial-state factory (F08)."""

from __future__ import annotations

import copy
import math
import operator
from enum import Enum, StrEnum
from typing import Annotated, Any, TypedDict, TypeAlias

JsonValue: TypeAlias = (
    None | str | bool | int | float | list["JsonValue"] | dict[str, "JsonValue"]
)


class AgentPhase(StrEnum):
    RECEIVED = "received"
    ORCHESTRATING = "orchestrating"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowErrorCode(StrEnum):
    INVALID_STATE = "invalid_state"


class WorkflowError(TypedDict):
    code: WorkflowErrorCode
    message: str


class AgentState(TypedDict):
    request_id: str
    input_text: str
    phase: AgentPhase
    status: WorkflowStatus
    artifacts: dict[str, JsonValue]
    error: WorkflowError | None
    orchestration_trace: Annotated[list[str], operator.add]


_ALLOWED_STATE_KEYS = frozenset(
    {
        "request_id",
        "input_text",
        "phase",
        "status",
        "artifacts",
        "error",
        "orchestration_trace",
    }
)

_REQUEST_ID_MAX_LEN = 128

_LEGAL_LIFECYCLES: frozenset[tuple[AgentPhase, WorkflowStatus, bool]] = frozenset(
    {
        (AgentPhase.RECEIVED, WorkflowStatus.RUNNING, False),
        (AgentPhase.ORCHESTRATING, WorkflowStatus.RUNNING, False),
        (AgentPhase.COMPLETED, WorkflowStatus.COMPLETED, False),
        (AgentPhase.FAILED, WorkflowStatus.FAILED, True),
    }
)


class AgentStateValidationError(ValueError):
    """Controlled Agent State contract failure (safe message only)."""

    def __init__(self, message: str) -> None:
        self.code = WorkflowErrorCode.INVALID_STATE
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        return f"AgentStateValidationError(code={self.code.value}): {self.message}"

    def __repr__(self) -> str:
        return f"AgentStateValidationError(message={self.message!r})"


def _reject(message: str) -> None:
    raise AgentStateValidationError(message)


def _validate_json_value(value: Any, *, path: str) -> None:
    if isinstance(value, Enum):
        _reject(f"non-JSON-safe Enum at {path}")
    if value is None:
        return
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            _reject(f"non-finite float at {path}")
        return
    if isinstance(value, str):
        if type(value) is not str:
            _reject(f"non-plain str at {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if type(key) is not str:
                _reject(f"non-str dict key at {path}")
            _validate_json_value(item, path=f"{path}.{key}")
        return
    _reject(f"non-JSON-safe value at {path}")


def _validate_artifacts(artifacts: Any) -> None:
    if not isinstance(artifacts, dict):
        _reject("artifacts must be a dict")
    for key, item in artifacts.items():
        if type(key) is not str:
            _reject("artifacts keys must be plain str")
        _validate_json_value(item, path=f"artifacts.{key}")


def _validate_error(error: Any) -> None:
    if error is None:
        return
    if not isinstance(error, dict):
        _reject("error must be None or WorkflowError mapping")
    keys = set(error.keys())
    if keys != {"code", "message"}:
        _reject("error must contain exactly code and message")
    code = error["code"]
    message = error["message"]
    if not isinstance(code, WorkflowErrorCode):
        _reject("error.code must be WorkflowErrorCode")
    if not isinstance(message, str) or not message.strip():
        _reject("error.message must be a non-empty str")


def _validate_trace(trace: Any) -> None:
    if not isinstance(trace, list) or isinstance(trace, tuple):
        _reject("orchestration_trace must be a list")
    for index, entry in enumerate(trace):
        if not isinstance(entry, str) or type(entry) is not str:
            _reject(f"orchestration_trace[{index}] must be a plain str")
        if not entry.strip():
            _reject(f"orchestration_trace[{index}] must be non-empty")


def validate_agent_state(state: Any) -> AgentState:
    """Fail-closed Agent State contract validation."""
    if not isinstance(state, dict):
        _reject("AgentState must be a mapping")

    keys = set(state.keys())
    if keys != _ALLOWED_STATE_KEYS:
        _reject("AgentState keys must equal the seven allowed fields")

    request_id = state["request_id"]
    if not isinstance(request_id, str) or type(request_id) is not str:
        _reject("request_id must be a plain str")
    if not request_id.strip():
        _reject("request_id must be non-empty after strip")
    if len(request_id) > _REQUEST_ID_MAX_LEN:
        _reject("request_id exceeds max length 128")

    input_text = state["input_text"]
    if not isinstance(input_text, str) or type(input_text) is not str:
        _reject("input_text must be a plain str")
    if not input_text.strip():
        _reject("input_text must be non-empty after strip")

    phase = state["phase"]
    status = state["status"]
    if not isinstance(phase, AgentPhase):
        _reject("phase must be AgentPhase")
    if not isinstance(status, WorkflowStatus):
        _reject("status must be WorkflowStatus")

    _validate_artifacts(state["artifacts"])
    _validate_error(state["error"])
    _validate_trace(state["orchestration_trace"])

    has_error = state["error"] is not None
    if (phase, status, has_error) not in _LEGAL_LIFECYCLES:
        _reject("invalid phase/status/error lifecycle combination")

    return state  # type: ignore[return-value]


def create_initial_state(
    request_id: str,
    input_text: str,
    *,
    artifacts: dict[str, JsonValue] | None = None,
) -> AgentState:
    """Create a validated RECEIVED/RUNNING AgentState with owned artifacts."""
    if artifacts is None:
        owned_artifacts: dict[str, JsonValue] = {}
    else:
        _validate_artifacts(artifacts)
        owned_artifacts = copy.deepcopy(artifacts)

    state: AgentState = {
        "request_id": request_id,
        "input_text": input_text,
        "phase": AgentPhase.RECEIVED,
        "status": WorkflowStatus.RUNNING,
        "artifacts": owned_artifacts,
        "error": None,
        "orchestration_trace": [],
    }
    return validate_agent_state(state)
