"""Matter registry: map business_id to Business Data and Decision Graph sources."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from gov_service_agent.business_graph.loader import load_decision_graph
from gov_service_agent.business_graph.models import DecisionGraph, NodeType
from gov_service_agent.guide_knowledge.models import GuideDocument, load_guide_document


class MatterRegistryError(ValueError):
    """Registry definition or resolution failure."""


@dataclass(frozen=True, slots=True)
class MatterRegistration:
    business_id: str
    business_data_path: Path
    decision_graph_path: Path | None
    guide_path: Path | None = None
    """Optional on-disk guide; None when graph is supplied only in memory."""


@dataclass(frozen=True, slots=True)
class _LoadedMatter:
    business_id: str
    graph: DecisionGraph
    business_data_path: Path | None
    decision_graph_path: Path | None
    guide_path: Path | None


class MatterRegistry:
    """Resolve Decision Graphs and guide paths by business_id."""

    def __init__(self, loaded: Mapping[str, _LoadedMatter]) -> None:
        if not loaded:
            raise MatterRegistryError("matter registry must contain at least one entry")
        self._loaded = dict(loaded)

    @classmethod
    def from_registrations(
        cls,
        registrations: list[MatterRegistration],
        *,
        repo_root: Path | None = None,
    ) -> MatterRegistry:
        if not registrations:
            raise MatterRegistryError("matter registry must contain at least one entry")
        loaded: dict[str, _LoadedMatter] = {}
        for item in registrations:
            business_id = item.business_id.strip()
            if not business_id:
                raise MatterRegistryError("business_id must be non-empty")
            if business_id in loaded:
                raise MatterRegistryError(f"duplicate business_id: {business_id}")
            if item.decision_graph_path is None:
                raise MatterRegistryError(
                    f"decision_graph_path required for {business_id}"
                )
            graph_path = _resolve_path(item.decision_graph_path, repo_root)
            graph = load_decision_graph(graph_path)
            _assert_terminal(graph, business_id)
            loaded[business_id] = _LoadedMatter(
                business_id=business_id,
                graph=graph,
                business_data_path=_resolve_path(item.business_data_path, repo_root),
                decision_graph_path=graph_path,
                guide_path=(
                    _resolve_path(item.guide_path, repo_root)
                    if item.guide_path is not None
                    else None
                ),
            )
        return cls(loaded)

    @classmethod
    def from_single_graph(cls, graph: DecisionGraph) -> MatterRegistry:
        """Backward-compatible wrap: every terminal on the graph shares it."""
        terminal_ids = _terminal_business_ids(graph)
        if not terminal_ids:
            raise MatterRegistryError("decision graph has no TERMINAL_CANDIDATE")
        loaded = {
            business_id: _LoadedMatter(
                business_id=business_id,
                graph=graph,
                business_data_path=None,
                decision_graph_path=None,
                guide_path=None,
            )
            for business_id in sorted(terminal_ids)
        }
        return cls(loaded)

    @classmethod
    def from_loaded(
        cls,
        graphs_by_business_id: Mapping[str, DecisionGraph],
        *,
        business_data_paths: Mapping[str, Path] | None = None,
        guide_paths: Mapping[str, Path] | None = None,
    ) -> MatterRegistry:
        """Test helper: bind preloaded graphs without reading registry JSON."""
        if not graphs_by_business_id:
            raise MatterRegistryError("matter registry must contain at least one entry")
        data_paths = business_data_paths or {}
        guides = guide_paths or {}
        loaded: dict[str, _LoadedMatter] = {}
        for business_id, graph in graphs_by_business_id.items():
            key = business_id.strip()
            if not key:
                raise MatterRegistryError("business_id must be non-empty")
            _assert_terminal(graph, key)
            loaded[key] = _LoadedMatter(
                business_id=key,
                graph=graph,
                business_data_path=data_paths.get(key),
                decision_graph_path=None,
                guide_path=guides.get(key),
            )
        return cls(loaded)

    def registered_ids(self) -> frozenset[str]:
        return frozenset(self._loaded)

    def has(self, business_id: str) -> bool:
        return business_id.strip() in self._loaded

    def get_graph(self, business_id: str) -> DecisionGraph | None:
        item = self._loaded.get(business_id.strip())
        return None if item is None else item.graph

    def require_graph(self, business_id: str) -> DecisionGraph:
        graph = self.get_graph(business_id)
        if graph is None:
            raise MatterRegistryError(f"business_id is not registered: {business_id}")
        return graph

    def require_graph_consistent(
        self,
        business_id: str,
        *,
        expected_graph_id: str | None,
    ) -> DecisionGraph:
        graph = self.require_graph(business_id)
        if (
            isinstance(expected_graph_id, str)
            and expected_graph_id.strip()
            and graph.graph_id != expected_graph_id.strip()
        ):
            raise MatterRegistryError(
                f"bound graph mismatch for {business_id}: "
                f"expected {expected_graph_id!r}, got {graph.graph_id!r}"
            )
        return graph

    def business_data_paths(self) -> list[Path]:
        paths: list[Path] = []
        seen: set[Path] = set()
        for item in self._loaded.values():
            if item.business_data_path is None:
                continue
            resolved = item.business_data_path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            paths.append(item.business_data_path)
        return paths

    def guide_path(self, business_id: str) -> Path | None:
        item = self._loaded.get(business_id.strip())
        return None if item is None else item.guide_path

    def load_guide_documents(self) -> dict[str, GuideDocument]:
        documents: dict[str, GuideDocument] = {}
        for business_id, item in self._loaded.items():
            if item.guide_path is None or not item.guide_path.is_file():
                continue
            document = load_guide_document(item.guide_path)
            if document.business_id != business_id:
                raise MatterRegistryError(
                    f"guide business_id {document.business_id!r} "
                    f"does not match registry key {business_id!r}"
                )
            documents[business_id] = document
        return documents

    def default_graph(self) -> DecisionGraph:
        first = next(iter(self._loaded.values()))
        return first.graph


def load_matter_registry(path: Path | str, *, repo_root: Path | None = None) -> MatterRegistry:
    file_path = Path(path)
    root = repo_root if repo_root is not None else file_path.resolve().parents[2]
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MatterRegistryError("matter registry cannot be parsed") from exc
    return parse_matter_registry(raw, repo_root=root)


def parse_matter_registry(raw: Any, *, repo_root: Path) -> MatterRegistry:
    if not isinstance(raw, dict):
        raise MatterRegistryError("matter registry must be an object")
    schema_version = raw.get("schema_version")
    if schema_version != "1":
        raise MatterRegistryError(
            f"unsupported matter registry schema_version: {schema_version!r}"
        )
    entries = raw.get("matters")
    if not isinstance(entries, list) or not entries:
        raise MatterRegistryError("matter registry matters must be a non-empty list")
    registrations: list[MatterRegistration] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise MatterRegistryError(f"matters[{index}] must be an object")
        business_id = entry.get("business_id")
        business_data = entry.get("business_data_source")
        graph_source = entry.get("decision_graph_source")
        guide_source = entry.get("guide_source")
        if not isinstance(business_id, str) or not business_id.strip():
            raise MatterRegistryError(f"matters[{index}].business_id is required")
        if not isinstance(business_data, str) or not business_data.strip():
            raise MatterRegistryError(
                f"matters[{index}].business_data_source is required"
            )
        if not isinstance(graph_source, str) or not graph_source.strip():
            raise MatterRegistryError(
                f"matters[{index}].decision_graph_source is required"
            )
        guide_path: Path | None = None
        if guide_source is not None:
            if not isinstance(guide_source, str) or not guide_source.strip():
                raise MatterRegistryError(
                    f"matters[{index}].guide_source must be a non-empty string when set"
                )
            guide_path = Path(guide_source.strip())
        registrations.append(
            MatterRegistration(
                business_id=business_id.strip(),
                business_data_path=Path(business_data.strip()),
                decision_graph_path=Path(graph_source.strip()),
                guide_path=guide_path,
            )
        )
    return MatterRegistry.from_registrations(registrations, repo_root=repo_root)


def _terminal_business_ids(graph: DecisionGraph) -> frozenset[str]:
    return frozenset(
        node.candidate_business_id
        for node in graph.nodes
        if node.node_type == NodeType.TERMINAL_CANDIDATE
        and isinstance(node.candidate_business_id, str)
        and node.candidate_business_id.strip()
    )


def _assert_terminal(graph: DecisionGraph, business_id: str) -> None:
    if business_id not in _terminal_business_ids(graph):
        raise MatterRegistryError(
            f"graph {graph.graph_id!r} has no TERMINAL_CANDIDATE "
            f"for business_id {business_id!r}"
        )


def _resolve_path(path: Path, repo_root: Path | None) -> Path:
    if path.is_absolute():
        return path
    if repo_root is None:
        return path
    return (repo_root / path).resolve()
