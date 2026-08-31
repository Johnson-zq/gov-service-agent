"""F03 Decision Graph Domain: Pydantic v2 models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gov_service_agent.business_data.models import DataScope


# ---------------------------------------------------------------------------
# Contract base (internal — not a business entity)
# ---------------------------------------------------------------------------


class ContractModel(BaseModel):
    """Internal base: Decision Graph Contract forbids unknown fields."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class NodeType(str, Enum):
    ENTRY = "ENTRY"
    SLOT_GATE = "SLOT_GATE"
    TERMINAL_CANDIDATE = "TERMINAL_CANDIDATE"
    UNSUPPORTED = "UNSUPPORTED"
    FALLBACK = "FALLBACK"


class EdgeKind(str, Enum):
    ENTRY_FORWARD = "ENTRY_FORWARD"
    SLOT_MATCH = "SLOT_MATCH"


class SlotMatchOperator(str, Enum):
    EQ = "EQ"


class DesignBasis(str, Enum):
    SYSTEM_DESIGNED = "SYSTEM_DESIGNED"
    SOURCE_SUPPORTED = "SOURCE_SUPPORTED"
    TEST_ONLY = "TEST_ONLY"


# ---------------------------------------------------------------------------
# Supporting models
# ---------------------------------------------------------------------------


class SourceConditionRef(ContractModel):
    """Scoped reference to an F02 Condition (design basis only, not a Rule)."""

    business_id: str
    condition_id: str

    @field_validator("business_id", "condition_id")
    @classmethod
    def required_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v


class SlotMatch(ContractModel):
    """Phase-1 edge match: EQ only."""

    slot: str
    operator: SlotMatchOperator
    value: str

    @field_validator("slot", "value")
    @classmethod
    def required_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v

    @model_validator(mode="after")
    def operator_must_be_eq(self) -> SlotMatch:
        if self.operator != SlotMatchOperator.EQ:
            raise ValueError("SlotMatch.operator must be EQ in phase 1")
        return self


# ---------------------------------------------------------------------------
# DecisionNode
# ---------------------------------------------------------------------------


class DecisionNode(ContractModel):
    node_id: str
    node_type: NodeType
    design_basis: DesignBasis

    slot_name: str | None = None
    allowed_values: list[str] | None = None
    question_text: str | None = None

    candidate_business_id: str | None = None
    unsupported_reason: str | None = None

    source_condition_refs: list[SourceConditionRef] | None = None

    @field_validator("node_id")
    @classmethod
    def node_id_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("node_id must be non-empty")
        return v

    @model_validator(mode="after")
    def check_node_fields(self) -> DecisionNode:
        nt = self.node_type

        if self.design_basis == DesignBasis.SOURCE_SUPPORTED:
            if not self.source_condition_refs:
                raise ValueError(
                    "SOURCE_SUPPORTED node requires at least one "
                    "source_condition_ref"
                )

        if nt == NodeType.ENTRY:
            for name, value in (
                ("slot_name", self.slot_name),
                ("allowed_values", self.allowed_values),
                ("question_text", self.question_text),
                ("candidate_business_id", self.candidate_business_id),
                ("unsupported_reason", self.unsupported_reason),
            ):
                if value is not None:
                    raise ValueError(f"ENTRY must not set {name}")
            return self

        if nt == NodeType.SLOT_GATE:
            if not self.slot_name or not self.slot_name.strip():
                raise ValueError("SLOT_GATE requires non-empty slot_name")
            if not self.allowed_values:
                raise ValueError("SLOT_GATE requires non-empty allowed_values")
            if len(self.allowed_values) != len(set(self.allowed_values)):
                raise ValueError("SLOT_GATE allowed_values must not contain duplicates")
            for v in self.allowed_values:
                if not v.strip():
                    raise ValueError("SLOT_GATE allowed_values must be non-empty strings")
            if not self.question_text or not self.question_text.strip():
                raise ValueError("SLOT_GATE requires non-empty question_text")
            if self.candidate_business_id is not None:
                raise ValueError("SLOT_GATE must not set candidate_business_id")
            if self.unsupported_reason is not None:
                raise ValueError("SLOT_GATE must not set unsupported_reason")
            return self

        if nt == NodeType.TERMINAL_CANDIDATE:
            if (
                not self.candidate_business_id
                or not self.candidate_business_id.strip()
            ):
                raise ValueError(
                    "TERMINAL_CANDIDATE requires non-empty candidate_business_id"
                )
            for name, value in (
                ("slot_name", self.slot_name),
                ("allowed_values", self.allowed_values),
                ("question_text", self.question_text),
                ("unsupported_reason", self.unsupported_reason),
            ):
                if value is not None:
                    raise ValueError(f"TERMINAL_CANDIDATE must not set {name}")
            return self

        if nt == NodeType.UNSUPPORTED:
            if (
                not self.unsupported_reason
                or not self.unsupported_reason.strip()
            ):
                raise ValueError("UNSUPPORTED requires non-empty unsupported_reason")
            if self.candidate_business_id is not None:
                raise ValueError("UNSUPPORTED must not set candidate_business_id")
            for name, value in (
                ("slot_name", self.slot_name),
                ("allowed_values", self.allowed_values),
                ("question_text", self.question_text),
            ):
                if value is not None:
                    raise ValueError(f"UNSUPPORTED must not set {name}")
            return self

        if nt == NodeType.FALLBACK:
            if self.candidate_business_id is not None:
                raise ValueError("FALLBACK must not set candidate_business_id")
            for name, value in (
                ("slot_name", self.slot_name),
                ("allowed_values", self.allowed_values),
                ("question_text", self.question_text),
                ("unsupported_reason", self.unsupported_reason),
            ):
                if value is not None:
                    raise ValueError(f"FALLBACK must not set {name}")
            return self

        raise ValueError(f"unsupported node_type: {nt}")


# ---------------------------------------------------------------------------
# DecisionEdge
# ---------------------------------------------------------------------------


class DecisionEdge(ContractModel):
    edge_id: str
    from_node_id: str
    to_node_id: str
    edge_kind: EdgeKind
    design_basis: DesignBasis
    match: SlotMatch | None = None
    source_condition_refs: list[SourceConditionRef] | None = None

    @field_validator("edge_id", "from_node_id", "to_node_id")
    @classmethod
    def required_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v

    @model_validator(mode="after")
    def check_edge_fields(self) -> DecisionEdge:
        if self.design_basis == DesignBasis.SOURCE_SUPPORTED:
            if not self.source_condition_refs:
                raise ValueError(
                    "SOURCE_SUPPORTED edge requires at least one "
                    "source_condition_ref"
                )

        if self.edge_kind == EdgeKind.ENTRY_FORWARD:
            if self.match is not None:
                raise ValueError("ENTRY_FORWARD must have match=null")
            return self

        if self.edge_kind == EdgeKind.SLOT_MATCH:
            if self.match is None:
                raise ValueError("SLOT_MATCH requires match")
            return self

        raise ValueError(f"unsupported edge_kind: {self.edge_kind}")


# ---------------------------------------------------------------------------
# DecisionGraph
# ---------------------------------------------------------------------------


class DecisionGraph(ContractModel):
    schema_version: str
    graph_id: str
    graph_version: int = Field(ge=1)
    data_scope: DataScope
    entry_node_id: str
    nodes: list[DecisionNode]
    edges: list[DecisionEdge]

    @field_validator("schema_version", "graph_id", "entry_node_id")
    @classmethod
    def required_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v
