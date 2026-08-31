"""F03 Decision Graph structural and business-ref validation."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import TYPE_CHECKING

from gov_service_agent.business_data.models import LifecycleStatus
from gov_service_agent.business_graph.models import (
    DecisionGraph,
    EdgeKind,
    NodeType,
)

if TYPE_CHECKING:
    from gov_service_agent.business_data.repository import JsonBusinessRepository


class GraphStructureError(ValueError):
    """Raised when DecisionGraph fails structural integrity checks."""


class GraphBusinessRefError(ValueError):
    """Raised when DecisionGraph fails business / condition reference checks."""


def validate_graph_structure(graph: DecisionGraph) -> None:
    """Fail-fast structural validation (no Repository dependency)."""

    node_ids = [n.node_id for n in graph.nodes]
    if len(node_ids) != len(set(node_ids)):
        dupes = sorted({i for i in node_ids if node_ids.count(i) > 1})
        raise GraphStructureError(f"duplicate node_id: {', '.join(dupes)}")

    edge_ids = [e.edge_id for e in graph.edges]
    if len(edge_ids) != len(set(edge_ids)):
        dupes = sorted({i for i in edge_ids if edge_ids.count(i) > 1})
        raise GraphStructureError(f"duplicate edge_id: {', '.join(dupes)}")

    by_id = {n.node_id: n for n in graph.nodes}

    entry_nodes = [n for n in graph.nodes if n.node_type == NodeType.ENTRY]
    if len(entry_nodes) != 1:
        raise GraphStructureError(
            f"DecisionGraph must have exactly one ENTRY node, found {len(entry_nodes)}"
        )
    entry = entry_nodes[0]
    if graph.entry_node_id not in by_id:
        raise GraphStructureError(
            f"entry_node_id not found: {graph.entry_node_id}"
        )
    if entry.node_id != graph.entry_node_id:
        raise GraphStructureError(
            f"entry_node_id {graph.entry_node_id!r} must equal the sole "
            f"ENTRY node_id {entry.node_id!r}"
        )

    outgoing: dict[str, list] = defaultdict(list)
    incoming: dict[str, list] = defaultdict(list)
    for edge in graph.edges:
        if edge.from_node_id not in by_id:
            raise GraphStructureError(
                f"edge {edge.edge_id}: unknown from_node_id {edge.from_node_id}"
            )
        if edge.to_node_id not in by_id:
            raise GraphStructureError(
                f"edge {edge.edge_id}: unknown to_node_id {edge.to_node_id}"
            )
        outgoing[edge.from_node_id].append(edge)
        incoming[edge.to_node_id].append(edge)

    if incoming.get(entry.node_id):
        raise GraphStructureError("ENTRY must have no incoming edges")

    entry_out = outgoing.get(entry.node_id, [])
    if len(entry_out) != 1:
        raise GraphStructureError(
            f"ENTRY must have exactly one outgoing edge, found {len(entry_out)}"
        )
    entry_edge = entry_out[0]
    if entry_edge.edge_kind != EdgeKind.ENTRY_FORWARD:
        raise GraphStructureError(
            "ENTRY outgoing edge must be ENTRY_FORWARD"
        )

    terminal_like = {
        NodeType.TERMINAL_CANDIDATE,
        NodeType.UNSUPPORTED,
        NodeType.FALLBACK,
    }

    for edge in graph.edges:
        from_node = by_id[edge.from_node_id]

        if edge.edge_kind == EdgeKind.ENTRY_FORWARD:
            if from_node.node_type != NodeType.ENTRY:
                raise GraphStructureError(
                    f"edge {edge.edge_id}: ENTRY_FORWARD from must be ENTRY"
                )
            if edge.match is not None:
                raise GraphStructureError(
                    f"edge {edge.edge_id}: ENTRY_FORWARD must have match=null"
                )

        elif edge.edge_kind == EdgeKind.SLOT_MATCH:
            if from_node.node_type != NodeType.SLOT_GATE:
                raise GraphStructureError(
                    f"edge {edge.edge_id}: SLOT_MATCH from must be SLOT_GATE"
                )
            if edge.match is None:
                raise GraphStructureError(
                    f"edge {edge.edge_id}: SLOT_MATCH requires match"
                )
            if edge.match.slot != from_node.slot_name:
                raise GraphStructureError(
                    f"edge {edge.edge_id}: match.slot {edge.match.slot!r} "
                    f"!= from slot_name {from_node.slot_name!r}"
                )
            assert from_node.allowed_values is not None
            if edge.match.value not in from_node.allowed_values:
                raise GraphStructureError(
                    f"edge {edge.edge_id}: match.value {edge.match.value!r} "
                    f"not in allowed_values"
                )
        else:
            raise GraphStructureError(
                f"edge {edge.edge_id}: unsupported edge_kind {edge.edge_kind}"
            )

        if from_node.node_type in terminal_like:
            raise GraphStructureError(
                f"edge {edge.edge_id}: {from_node.node_type.value} "
                "must not have outgoing edges"
            )

    for node in graph.nodes:
        if node.node_type in terminal_like:
            if outgoing.get(node.node_id):
                raise GraphStructureError(
                    f"{node.node_type.value} node {node.node_id} "
                    "must have no outgoing edges"
                )

        if node.node_type == NodeType.SLOT_GATE:
            assert node.allowed_values is not None
            slot_edges = [
                e
                for e in outgoing.get(node.node_id, [])
                if e.edge_kind == EdgeKind.SLOT_MATCH
            ]
            values = [e.match.value for e in slot_edges if e.match is not None]
            value_set = set(values)
            if len(values) != len(value_set):
                raise GraphStructureError(
                    f"SLOT_GATE {node.node_id}: duplicate match.value "
                    "among outgoing edges"
                )
            allowed_set = set(node.allowed_values)
            if value_set != allowed_set:
                missing = sorted(allowed_set - value_set)
                extra = sorted(value_set - allowed_set)
                raise GraphStructureError(
                    f"SLOT_GATE {node.node_id}: outgoing match values must "
                    f"exactly equal allowed_values; missing={missing}; "
                    f"extra={extra}"
                )

    # Cycle detection (DFS) and reachability (BFS) from entry
    adj: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        adj[edge.from_node_id].append(edge.to_node_id)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n.node_id: WHITE for n in graph.nodes}

    def dfs(u: str) -> None:
        color[u] = GRAY
        for v in adj.get(u, []):
            if color[v] == GRAY:
                raise GraphStructureError(
                    f"cycle detected involving edge to {v}"
                )
            if color[v] == WHITE:
                dfs(v)
        color[u] = BLACK

    dfs(entry.node_id)

    reachable: set[str] = set()
    queue: deque[str] = deque([entry.node_id])
    reachable.add(entry.node_id)
    while queue:
        u = queue.popleft()
        for v in adj.get(u, []):
            if v not in reachable:
                reachable.add(v)
                queue.append(v)

    all_ids = set(by_id.keys())
    unreachable = sorted(all_ids - reachable)
    if unreachable:
        raise GraphStructureError(
            f"unreachable nodes from entry: {', '.join(unreachable)}"
        )


def validate_graph_business_refs(
    graph: DecisionGraph,
    repository: JsonBusinessRepository,
) -> None:
    """Cross-validate terminal candidates and SourceConditionRefs via Repository."""

    for node in graph.nodes:
        if node.node_type != NodeType.TERMINAL_CANDIDATE:
            continue
        bid = node.candidate_business_id
        assert bid is not None
        if not repository.has_business(bid):
            raise GraphBusinessRefError(
                f"terminal {node.node_id}: unknown candidate_business_id {bid}"
            )
        business = repository.get_business(bid)
        if business.status != LifecycleStatus.ACTIVE:
            raise GraphBusinessRefError(
                f"terminal {node.node_id}: candidate_business_id {bid} "
                f"status is {business.status.value}, expected ACTIVE"
            )

    refs: list[tuple[str, str, str]] = []
    for node in graph.nodes:
        if node.source_condition_refs:
            for ref in node.source_condition_refs:
                refs.append((f"node:{node.node_id}", ref.business_id, ref.condition_id))
    for edge in graph.edges:
        if edge.source_condition_refs:
            for ref in edge.source_condition_refs:
                refs.append((f"edge:{edge.edge_id}", ref.business_id, ref.condition_id))

    for owner, business_id, condition_id in refs:
        if not repository.has_business(business_id):
            raise GraphBusinessRefError(
                f"{owner}: unknown business_id in SourceConditionRef: "
                f"{business_id}"
            )
        if not repository.has_condition(business_id, condition_id):
            raise GraphBusinessRefError(
                f"{owner}: unknown condition_id {condition_id!r} "
                f"for business {business_id}"
            )
