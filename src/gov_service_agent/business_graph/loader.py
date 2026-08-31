"""F03 Decision Graph JSON loader (structure only; no Business Repository)."""

from __future__ import annotations

from pathlib import Path

from gov_service_agent.business_graph.models import DecisionGraph
from gov_service_agent.business_graph.validation import (
    GraphStructureError,
    validate_graph_structure,
)

SUPPORTED_SCHEMA_VERSION = "1"


def load_decision_graph(path: Path | str) -> DecisionGraph:
    """Load and structurally validate a DecisionGraph JSON file.

    Does not perform Graph+Business cross validation. Call
    ``validate_graph_business_refs(graph, repository)`` explicitly when needed.
    """
    file_path = Path(path)
    graph = DecisionGraph.model_validate_json(
        file_path.read_text(encoding="utf-8")
    )
    if graph.schema_version != SUPPORTED_SCHEMA_VERSION:
        raise GraphStructureError(
            f"unsupported Decision Graph schema_version: "
            f"{graph.schema_version!r}; expected {SUPPORTED_SCHEMA_VERSION!r}"
        )
    validate_graph_structure(graph)
    return graph
