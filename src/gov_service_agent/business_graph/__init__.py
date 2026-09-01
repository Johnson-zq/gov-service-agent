"""Business Decision Graph package (F03 Domain + F04 Transition)."""

from gov_service_agent.business_graph.loader import load_decision_graph
from gov_service_agent.business_graph.models import (
    DecisionEdge,
    DecisionGraph,
    DecisionNode,
    DesignBasis,
    EdgeKind,
    NodeType,
    SlotMatch,
    SlotMatchOperator,
    SourceConditionRef,
)
from gov_service_agent.business_graph.transition import (
    TransitionInvariantError,
    TransitionNodeNotFoundError,
    TransitionResult,
    TransitionStatus,
    advance_until_blocked,
    step,
)
from gov_service_agent.business_graph.validation import (
    GraphBusinessRefError,
    GraphStructureError,
    validate_graph_business_refs,
    validate_graph_structure,
)

__all__ = [
    "DecisionEdge",
    "DecisionGraph",
    "DecisionNode",
    "DesignBasis",
    "EdgeKind",
    "GraphBusinessRefError",
    "GraphStructureError",
    "NodeType",
    "SlotMatch",
    "SlotMatchOperator",
    "SourceConditionRef",
    "TransitionInvariantError",
    "TransitionNodeNotFoundError",
    "TransitionResult",
    "TransitionStatus",
    "advance_until_blocked",
    "load_decision_graph",
    "step",
    "validate_graph_business_refs",
    "validate_graph_structure",
]
