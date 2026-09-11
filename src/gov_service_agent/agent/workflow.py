"""LangGraph Agent workflow builders and sync runners (F08 + F09 + F10).

LangGraph END means this Agent orchestration invocation finished.
It is not Business Decision Graph TERMINAL_CANDIDATE.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from langgraph.graph import END, START, StateGraph

from gov_service_agent.agent.explanation import ExplanationService
from gov_service_agent.agent.interaction import (
    AnswerMapper,
    MappingPolicy,
    SlotInteractionContext,
    empty_f09_namespace,
)
from gov_service_agent.agent.nodes import (
    _complete_node,
    _compose_terminal_response_node,
    _finalize_confirmation_node,
    _interpret_confirmation_node,
    _make_advance_business_graph_node,
    _make_explain_current_topic_node,
    _make_interpret_slot_input_node,
    _make_validate_slot_answer_node,
    _make_validate_terminal_candidate_node,
    _prepare_node,
    _resume_current_slot_node,
    _route_by_confirmation_intent,
    _route_by_interpretation,
    _route_by_terminal_validation,
    _route_by_validation,
)
from gov_service_agent.agent.state import AgentState, validate_agent_state
from gov_service_agent.agent.terminal import (
    TerminalCandidateContext,
    TerminalConfirmationDependencies,
    TerminalConfirmationMode,
    empty_f10_namespace,
)
from gov_service_agent.business_graph.models import DecisionGraph


def build_agent_workflow() -> Any:
    """Build and compile the fixed START → prepare → complete → END graph."""
    graph: StateGraph = StateGraph(AgentState)
    graph.add_node("prepare", _prepare_node)
    graph.add_node("complete", _complete_node)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "complete")
    graph.add_edge("complete", END)
    return graph.compile()


def run_agent_workflow(initial_state: AgentState) -> AgentState:
    """
    Validate, invoke (on a defensive copy), validate, and return final state.

    Does not mutate the caller-owned initial_state. Unexpected errors propagate.
    """
    validate_agent_state(initial_state)
    execution_state = copy.deepcopy(initial_state)
    compiled = build_agent_workflow()
    result = compiled.invoke(execution_state)
    return validate_agent_state(result)


@dataclass(frozen=True, slots=True)
class SlotInteractionDependencies:
    answer_mapper: AnswerMapper
    explanation_service: ExplanationService
    decision_graph: DecisionGraph
    mapping_policy: MappingPolicy = field(default_factory=MappingPolicy)


def build_slot_interaction_workflow(
    deps: SlotInteractionDependencies,
) -> Any:
    """Build F09 specialized missing-slot LangGraph workflow."""
    graph: StateGraph = StateGraph(AgentState)
    graph.add_node("prepare", _prepare_node)
    graph.add_node(
        "interpret_slot_input",
        _make_interpret_slot_input_node(deps),
    )
    graph.add_node(
        "explain_current_topic",
        _make_explain_current_topic_node(deps),
    )
    graph.add_node(
        "validate_slot_answer",
        _make_validate_slot_answer_node(deps),
    )
    graph.add_node(
        "advance_business_graph",
        _make_advance_business_graph_node(deps),
    )
    graph.add_node("resume_current_slot", _resume_current_slot_node)
    graph.add_node("complete", _complete_node)

    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "interpret_slot_input")
    graph.add_conditional_edges(
        "interpret_slot_input",
        _route_by_interpretation,
        {
            "explain_current_topic": "explain_current_topic",
            "validate_slot_answer": "validate_slot_answer",
            "resume_current_slot": "resume_current_slot",
        },
    )
    graph.add_edge("explain_current_topic", "resume_current_slot")
    graph.add_conditional_edges(
        "validate_slot_answer",
        _route_by_validation,
        {
            "advance_business_graph": "advance_business_graph",
            "resume_current_slot": "resume_current_slot",
        },
    )
    graph.add_edge("advance_business_graph", "complete")
    graph.add_edge("resume_current_slot", "complete")
    graph.add_edge("complete", END)
    return graph.compile()


def run_slot_interaction_workflow(
    initial_state: AgentState,
    slot_context: SlotInteractionContext,
    deps: SlotInteractionDependencies,
) -> AgentState:
    """
    Run one F09 slot-interaction invocation.

    Initializes a fresh artifacts['f09'] namespace while preserving other
    artifact namespaces. Does not mutate caller-owned state or slots.
    """
    validate_agent_state(initial_state)
    execution_state = copy.deepcopy(initial_state)
    owned_artifacts = copy.deepcopy(execution_state["artifacts"])
    # Refresh f09 namespace for this invocation; preserve other namespaces.
    owned_artifacts["f09"] = empty_f09_namespace(slot_context)
    execution_state["artifacts"] = owned_artifacts
    compiled = build_slot_interaction_workflow(deps)
    result = compiled.invoke(execution_state)
    return validate_agent_state(result)


def build_terminal_confirmation_workflow(
    deps: TerminalConfirmationDependencies,
) -> Any:
    """Build F10 specialized terminal confirmation LangGraph workflow."""
    graph: StateGraph = StateGraph(AgentState)
    graph.add_node("prepare", _prepare_node)
    graph.add_node(
        "validate_terminal_candidate",
        _make_validate_terminal_candidate_node(deps),
    )
    graph.add_node("interpret_confirmation", _interpret_confirmation_node)
    graph.add_node("finalize_confirmation", _finalize_confirmation_node)
    graph.add_node("compose_terminal_response", _compose_terminal_response_node)
    graph.add_node("complete", _complete_node)

    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "validate_terminal_candidate")
    graph.add_conditional_edges(
        "validate_terminal_candidate",
        _route_by_terminal_validation,
        {
            "compose_terminal_response": "compose_terminal_response",
            "interpret_confirmation": "interpret_confirmation",
        },
    )
    graph.add_conditional_edges(
        "interpret_confirmation",
        _route_by_confirmation_intent,
        {
            "finalize_confirmation": "finalize_confirmation",
            "compose_terminal_response": "compose_terminal_response",
        },
    )
    graph.add_edge("finalize_confirmation", "compose_terminal_response")
    graph.add_edge("compose_terminal_response", "complete")
    graph.add_edge("complete", END)
    return graph.compile()


def _run_terminal_confirmation(
    initial_state: AgentState,
    terminal_context: TerminalCandidateContext,
    deps: TerminalConfirmationDependencies,
    *,
    mode: TerminalConfirmationMode,
) -> AgentState:
    validate_agent_state(initial_state)
    owned_context = terminal_context.model_copy(deep=True)
    execution_state = copy.deepcopy(initial_state)
    owned_artifacts = copy.deepcopy(execution_state["artifacts"])
    owned_artifacts["f10"] = empty_f10_namespace(
        mode=mode,
        context=owned_context,
    )
    execution_state["artifacts"] = owned_artifacts
    compiled = build_terminal_confirmation_workflow(deps)
    result = compiled.invoke(execution_state)
    return validate_agent_state(result)


def prepare_terminal_confirmation(
    initial_state: AgentState,
    terminal_context: TerminalCandidateContext,
    deps: TerminalConfirmationDependencies,
) -> AgentState:
    """PREPARE: validate terminal candidate and ask for confirmation.

    Never interprets AgentState.input_text as a confirmation answer.
    """
    return _run_terminal_confirmation(
        initial_state,
        terminal_context,
        deps,
        mode=TerminalConfirmationMode.PREPARE,
    )


def resolve_terminal_confirmation(
    initial_state: AgentState,
    terminal_context: TerminalCandidateContext,
    deps: TerminalConfirmationDependencies,
) -> AgentState:
    """RESOLVE: revalidate terminal candidate and interpret new-turn input."""
    return _run_terminal_confirmation(
        initial_state,
        terminal_context,
        deps,
        mode=TerminalConfirmationMode.RESOLVE,
    )
