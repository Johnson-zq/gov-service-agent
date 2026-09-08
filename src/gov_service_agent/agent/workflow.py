"""LangGraph Agent workflow builder and sync runner (F08).

LangGraph END means this Agent orchestration invocation finished.
It is not Business Decision Graph TERMINAL_CANDIDATE.
"""

from __future__ import annotations

import copy
from typing import Any

from langgraph.graph import END, START, StateGraph

from gov_service_agent.agent.nodes import _complete_node, _prepare_node
from gov_service_agent.agent.state import AgentState, validate_agent_state


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
