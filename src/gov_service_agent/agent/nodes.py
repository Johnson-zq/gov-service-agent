"""Private LangGraph orchestration nodes (F08). Not public API."""

from __future__ import annotations

from typing import Any

from gov_service_agent.agent.state import (
    AgentPhase,
    AgentState,
    WorkflowStatus,
    validate_agent_state,
)


def _prepare_node(state: AgentState) -> dict[str, Any]:
    """Advance RECEIVED → ORCHESTRATING; append orchestration trace delta."""
    validate_agent_state(state)
    return {
        "phase": AgentPhase.ORCHESTRATING,
        "orchestration_trace": ["prepare"],
    }


def _complete_node(state: AgentState) -> dict[str, Any]:
    """Advance ORCHESTRATING → COMPLETED; append orchestration trace delta."""
    validate_agent_state(state)
    return {
        "phase": AgentPhase.COMPLETED,
        "status": WorkflowStatus.COMPLETED,
        "error": None,
        "orchestration_trace": ["complete"],
    }
