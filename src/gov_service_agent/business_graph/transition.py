"""F04 Deterministic Graph Transition (pure functions; no Rule Selection)."""

from __future__ import annotations

from enum import Enum
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gov_service_agent.business_graph.models import (
    DecisionEdge,
    DecisionGraph,
    DecisionNode,
    EdgeKind,
    NodeType,
)


class TransitionStatus(str, Enum):
    NEED_SLOT = "NEED_SLOT"
    INVALID_SLOT = "INVALID_SLOT"
    ADVANCED = "ADVANCED"
    TERMINAL_CANDIDATE = "TERMINAL_CANDIDATE"
    UNSUPPORTED = "UNSUPPORTED"
    FALLBACK = "FALLBACK"


class TransitionNodeNotFoundError(LookupError):
    """Raised when current_node_id is not in the DecisionGraph."""


class TransitionInvariantError(ValueError):
    """Raised when a structural invariant assumed by Transition is violated."""


class TransitionResult(BaseModel):
    """Single result model for step and advance_until_blocked."""

    model_config = ConfigDict(extra="forbid")

    status: TransitionStatus
    current_node_id: str

    required_slot: str | None = None
    invalid_value: str | None = None
    allowed_values: list[str] | None = None
    question_text: str | None = None

    candidate_business_id: str | None = None
    unsupported_reason: str | None = None

    visited_node_ids: list[str] = Field(min_length=1)
    traversed_edge_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_result_invariants(self) -> TransitionResult:
        if self.current_node_id != self.visited_node_ids[-1]:
            raise ValueError(
                "current_node_id must equal visited_node_ids[-1]"
            )
        if len(self.traversed_edge_ids) != len(self.visited_node_ids) - 1:
            raise ValueError(
                "len(traversed_edge_ids) must equal "
                "len(visited_node_ids) - 1"
            )

        status = self.status
        if status == TransitionStatus.NEED_SLOT:
            self._require_slot_clarification(invalid_required=False)
            self._forbid_terminal_fields()
        elif status == TransitionStatus.INVALID_SLOT:
            self._require_slot_clarification(invalid_required=True)
            self._forbid_terminal_fields()
        elif status == TransitionStatus.ADVANCED:
            self._forbid_slot_fields()
            self._forbid_terminal_fields()
        elif status == TransitionStatus.TERMINAL_CANDIDATE:
            self._forbid_slot_fields()
            if (
                not self.candidate_business_id
                or not self.candidate_business_id.strip()
            ):
                raise ValueError(
                    "TERMINAL_CANDIDATE requires candidate_business_id"
                )
            if self.unsupported_reason is not None:
                raise ValueError(
                    "TERMINAL_CANDIDATE must not set unsupported_reason"
                )
        elif status == TransitionStatus.UNSUPPORTED:
            self._forbid_slot_fields()
            if self.candidate_business_id is not None:
                raise ValueError("UNSUPPORTED must not set candidate_business_id")
            if (
                not self.unsupported_reason
                or not self.unsupported_reason.strip()
            ):
                raise ValueError("UNSUPPORTED requires unsupported_reason")
        elif status == TransitionStatus.FALLBACK:
            self._forbid_slot_fields()
            if self.candidate_business_id is not None:
                raise ValueError("FALLBACK must not set candidate_business_id")
            if self.unsupported_reason is not None:
                raise ValueError("FALLBACK must not set unsupported_reason")
        else:
            raise ValueError(f"unsupported TransitionStatus: {status}")

        return self

    def _require_slot_clarification(self, *, invalid_required: bool) -> None:
        if not self.required_slot or not self.required_slot.strip():
            raise ValueError("required_slot must be non-empty")
        if not self.allowed_values:
            raise ValueError("allowed_values must be non-empty")
        if not self.question_text or not self.question_text.strip():
            raise ValueError("question_text must be non-empty")
        if invalid_required:
            if self.invalid_value is None:
                raise ValueError("INVALID_SLOT requires invalid_value")
        else:
            if self.invalid_value is not None:
                raise ValueError("NEED_SLOT must not set invalid_value")

    def _forbid_slot_fields(self) -> None:
        for name, value in (
            ("required_slot", self.required_slot),
            ("invalid_value", self.invalid_value),
            ("allowed_values", self.allowed_values),
            ("question_text", self.question_text),
        ):
            if value is not None:
                raise ValueError(f"{self.status.value} must not set {name}")

    def _forbid_terminal_fields(self) -> None:
        if self.candidate_business_id is not None:
            raise ValueError(
                f"{self.status.value} must not set candidate_business_id"
            )
        if self.unsupported_reason is not None:
            raise ValueError(
                f"{self.status.value} must not set unsupported_reason"
            )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _require_node(graph: DecisionGraph, node_id: str) -> DecisionNode:
    for node in graph.nodes:
        if node.node_id == node_id:
            return node
    raise TransitionNodeNotFoundError(
        f"unknown current_node_id: {node_id}"
    )


def _outgoing(graph: DecisionGraph, node_id: str) -> list[DecisionEdge]:
    return [e for e in graph.edges if e.from_node_id == node_id]


def _result_for_settled_node(
    node: DecisionNode,
    *,
    visited_node_ids: list[str],
    traversed_edge_ids: list[str],
) -> TransitionResult:
    """Build result for resting on ``node`` (after hop or already terminal)."""
    nt = node.node_type
    if nt == NodeType.TERMINAL_CANDIDATE:
        assert node.candidate_business_id is not None
        return TransitionResult(
            status=TransitionStatus.TERMINAL_CANDIDATE,
            current_node_id=node.node_id,
            candidate_business_id=node.candidate_business_id,
            visited_node_ids=visited_node_ids,
            traversed_edge_ids=traversed_edge_ids,
        )
    if nt == NodeType.UNSUPPORTED:
        assert node.unsupported_reason is not None
        return TransitionResult(
            status=TransitionStatus.UNSUPPORTED,
            current_node_id=node.node_id,
            unsupported_reason=node.unsupported_reason,
            visited_node_ids=visited_node_ids,
            traversed_edge_ids=traversed_edge_ids,
        )
    if nt == NodeType.FALLBACK:
        return TransitionResult(
            status=TransitionStatus.FALLBACK,
            current_node_id=node.node_id,
            visited_node_ids=visited_node_ids,
            traversed_edge_ids=traversed_edge_ids,
        )
    if nt in (NodeType.ENTRY, NodeType.SLOT_GATE):
        return TransitionResult(
            status=TransitionStatus.ADVANCED,
            current_node_id=node.node_id,
            visited_node_ids=visited_node_ids,
            traversed_edge_ids=traversed_edge_ids,
        )
    raise TransitionInvariantError(f"unsupported node_type: {nt}")


def _advance_along_edge(
    graph: DecisionGraph,
    from_node: DecisionNode,
    edge: DecisionEdge,
) -> TransitionResult:
    target = _require_node(graph, edge.to_node_id)
    return _result_for_settled_node(
        target,
        visited_node_ids=[from_node.node_id, target.node_id],
        traversed_edge_ids=[edge.edge_id],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def step(
    graph: DecisionGraph,
    current_node_id: str,
    slots: Mapping[str, str],
) -> TransitionResult:
    """Single deterministic transition step. Does not mutate graph or slots."""
    node = _require_node(graph, current_node_id)
    nt = node.node_type

    if nt == NodeType.TERMINAL_CANDIDATE:
        assert node.candidate_business_id is not None
        return TransitionResult(
            status=TransitionStatus.TERMINAL_CANDIDATE,
            current_node_id=node.node_id,
            candidate_business_id=node.candidate_business_id,
            visited_node_ids=[node.node_id],
            traversed_edge_ids=[],
        )
    if nt == NodeType.UNSUPPORTED:
        assert node.unsupported_reason is not None
        return TransitionResult(
            status=TransitionStatus.UNSUPPORTED,
            current_node_id=node.node_id,
            unsupported_reason=node.unsupported_reason,
            visited_node_ids=[node.node_id],
            traversed_edge_ids=[],
        )
    if nt == NodeType.FALLBACK:
        return TransitionResult(
            status=TransitionStatus.FALLBACK,
            current_node_id=node.node_id,
            visited_node_ids=[node.node_id],
            traversed_edge_ids=[],
        )

    if nt == NodeType.ENTRY:
        outs = _outgoing(graph, node.node_id)
        forwards = [e for e in outs if e.edge_kind == EdgeKind.ENTRY_FORWARD]
        if len(forwards) != 1:
            raise TransitionInvariantError(
                f"ENTRY {node.node_id} must have exactly one ENTRY_FORWARD, "
                f"found {len(forwards)}"
            )
        return _advance_along_edge(graph, node, forwards[0])

    if nt == NodeType.SLOT_GATE:
        assert node.slot_name is not None
        assert node.allowed_values is not None
        assert node.question_text is not None
        slot_name = node.slot_name
        if slot_name not in slots:
            return TransitionResult(
                status=TransitionStatus.NEED_SLOT,
                current_node_id=node.node_id,
                required_slot=slot_name,
                allowed_values=list(node.allowed_values),
                question_text=node.question_text,
                visited_node_ids=[node.node_id],
                traversed_edge_ids=[],
            )
        value = slots[slot_name]
        if value not in node.allowed_values:
            return TransitionResult(
                status=TransitionStatus.INVALID_SLOT,
                current_node_id=node.node_id,
                required_slot=slot_name,
                invalid_value=value,
                allowed_values=list(node.allowed_values),
                question_text=node.question_text,
                visited_node_ids=[node.node_id],
                traversed_edge_ids=[],
            )
        matches = [
            e
            for e in _outgoing(graph, node.node_id)
            if e.edge_kind == EdgeKind.SLOT_MATCH
            and e.match is not None
            and e.match.value == value
        ]
        if len(matches) != 1:
            raise TransitionInvariantError(
                f"SLOT_GATE {node.node_id}: expected exactly one SLOT_MATCH "
                f"for value {value!r}, found {len(matches)}"
            )
        return _advance_along_edge(graph, node, matches[0])

    raise TransitionInvariantError(f"unsupported node_type: {nt}")


def advance_until_blocked(
    graph: DecisionGraph,
    current_node_id: str,
    slots: Mapping[str, str],
) -> TransitionResult:
    """Repeatedly call step until blocked or terminal-like."""
    first = step(graph, current_node_id, slots)
    visited = list(first.visited_node_ids)
    traversed = list(first.traversed_edge_ids)
    result = first
    hop_count = 0
    max_hops = len(graph.nodes)

    while result.status == TransitionStatus.ADVANCED:
        hop_count += 1
        if hop_count > max_hops:
            raise TransitionInvariantError(
                "advance_until_blocked exceeded len(graph.nodes) hops"
            )
        nxt = step(graph, result.current_node_id, slots)
        visited.extend(nxt.visited_node_ids[1:])
        traversed.extend(nxt.traversed_edge_ids)
        result = nxt

    return TransitionResult(
        status=result.status,
        current_node_id=result.current_node_id,
        required_slot=result.required_slot,
        invalid_value=result.invalid_value,
        allowed_values=result.allowed_values,
        question_text=result.question_text,
        candidate_business_id=result.candidate_business_id,
        unsupported_reason=result.unsupported_reason,
        visited_node_ids=visited,
        traversed_edge_ids=traversed,
    )
