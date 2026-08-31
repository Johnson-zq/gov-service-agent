"""F02 Business Data Contract: Pydantic v2 models and snapshot loading."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Contract base (internal — not a business entity)
# ---------------------------------------------------------------------------


class ContractModel(BaseModel):
    """Internal base: Business Data Contract forbids unknown fields."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class VerificationStatus(str, Enum):
    """Business fact / rule verification status.

    Not used for system metadata (business_id, data_scope, data_version, etc.).
    Public filtering is deferred to F03 Repository.
    """

    SOURCE_EXPLICIT = "SOURCE_EXPLICIT"
    SYSTEM_DERIVED = "SYSTEM_DERIVED"
    TO_CONFIRM = "TO_CONFIRM"
    VERIFIED = "VERIFIED"


class DataScope(str, Enum):
    TEST = "TEST"
    DEMO = "DEMO"
    PRODUCTION = "PRODUCTION"


class LifecycleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class SourceType(str, Enum):
    OFFICIAL_GUIDE = "OFFICIAL_GUIDE"
    MANUAL_CONFIRMATION = "MANUAL_CONFIRMATION"
    INTERNAL_NOTE = "INTERNAL_NOTE"


class ConditionRole(str, Enum):
    APPLICANT_SCOPE = "APPLICANT_SCOPE"
    ELIGIBILITY = "ELIGIBILITY"
    PROCESS_BRANCH = "PROCESS_BRANCH"


class RequirementLevel(str, Enum):
    REQUIRED = "REQUIRED"
    CONDITIONAL = "CONDITIONAL"
    OPTIONAL = "OPTIONAL"


class ChannelType(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    MINI_PROGRAM = "MINI_PROGRAM"
    SELF_SERVICE_TERMINAL = "SELF_SERVICE_TERMINAL"
    SERVICE_HALL = "SERVICE_HALL"
    BANK_WINDOW = "BANK_WINDOW"


class ChannelPurpose(str, Enum):
    PAYMENT = "PAYMENT"
    APPLICATION = "APPLICATION"
    INQUIRY = "INQUIRY"
    OTHER = "OTHER"


class LocationDetailStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    UNKNOWN_DETAIL = "UNKNOWN_DETAIL"
    DISPUTED = "DISPUTED"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class EvidenceRef(ContractModel):
    """Fact-level provenance: which source, section, and optional excerpt."""

    source_id: str
    source_section: str | None = None
    source_excerpt: str | None = None

    @field_validator("source_id")
    @classmethod
    def source_id_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source_id must be non-empty")
        return v


class SourceRecord(ContractModel):
    source_id: str
    source_title: str
    source_type: SourceType
    source_file: str | None = None
    source_section: str | None = None
    effective_date: date | None = None
    source_version: str | None = None
    ingested_at: datetime | None = None
    ingested_by: str | None = None

    @field_validator("source_id", "source_title")
    @classmethod
    def required_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v

    @field_validator("source_file")
    @classmethod
    def no_absolute_path(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # Reject Windows drive paths and POSIX absolute paths.
        if len(v) >= 2 and v[1] == ":":
            raise ValueError("source_file must be a filename, not an absolute path")
        if v.startswith("/") or v.startswith("\\"):
            raise ValueError("source_file must be a filename, not an absolute path")
        if "\\" in v or "/" in v:
            raise ValueError("source_file must be a filename without directory path")
        return v


# ---------------------------------------------------------------------------
# Business
# ---------------------------------------------------------------------------


class Business(ContractModel):
    business_id: str
    canonical_name: str
    category: str
    data_scope: DataScope
    data_version: int = Field(ge=1)
    status: LifecycleStatus
    primary_source_id: str
    updated_at: datetime

    service_target: str
    implementing_authority: str
    on_site_visits: str
    quantity_limit: str
    prohibition: str

    metadata_source_id: str
    metadata_source_status: VerificationStatus

    @field_validator(
        "business_id",
        "canonical_name",
        "category",
        "primary_source_id",
        "service_target",
        "implementing_authority",
        "on_site_visits",
        "quantity_limit",
        "prohibition",
        "metadata_source_id",
    )
    @classmethod
    def required_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v


# ---------------------------------------------------------------------------
# Material / Location / Channel / LegalBasis
# ---------------------------------------------------------------------------


def _require_system_derived_lineage(
    status: VerificationStatus,
    *,
    rule: str | None,
    note: str | None,
    field_label: str,
) -> None:
    if status == VerificationStatus.SYSTEM_DERIVED:
        if not (rule and rule.strip()) and not (note and note.strip()):
            raise ValueError(
                f"{field_label}: SYSTEM_DERIVED requires normalization_rule "
                "or derivation_note"
            )


class Material(ContractModel):
    material_id: str
    evidence: EvidenceRef

    source_text: str
    source_status: VerificationStatus

    requirement_level: RequirementLevel
    requirement_level_status: VerificationStatus
    derivation_note: str | None = None
    condition_ref: str | None = None

    @field_validator("material_id", "source_text")
    @classmethod
    def required_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v

    @model_validator(mode="after")
    def check_statuses(self) -> Material:
        if self.source_status == VerificationStatus.SOURCE_EXPLICIT:
            if not self.evidence.source_id.strip():
                raise ValueError(
                    "SOURCE_EXPLICIT material requires EvidenceRef.source_id"
                )
        _require_system_derived_lineage(
            self.requirement_level_status,
            rule=None,
            note=self.derivation_note,
            field_label="requirement_level",
        )
        return self


class ServiceHours(ContractModel):
    raw_text: str
    source_status: VerificationStatus

    @field_validator("raw_text")
    @classmethod
    def raw_text_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("raw_text must be non-empty")
        return v


class HandlingLocation(ContractModel):
    location_id: str
    evidence: EvidenceRef

    name: str
    name_status: VerificationStatus
    address: str
    address_status: VerificationStatus
    service_hours: ServiceHours

    floor: str | None = None
    window: str | None = None
    location_detail_status: LocationDetailStatus

    @field_validator("location_id", "name", "address")
    @classmethod
    def required_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v

    @model_validator(mode="after")
    def check_source_explicit_evidence(self) -> HandlingLocation:
        for status, label in (
            (self.name_status, "name"),
            (self.address_status, "address"),
        ):
            if status == VerificationStatus.SOURCE_EXPLICIT:
                if not self.evidence.source_id.strip():
                    raise ValueError(
                        f"SOURCE_EXPLICIT {label} requires EvidenceRef.source_id"
                    )
        return self


class Channel(ContractModel):
    channel_id: str
    evidence: EvidenceRef

    source_name: str
    source_status: VerificationStatus

    channel_type: ChannelType
    channel_type_status: VerificationStatus
    channel_type_rule: str | None = None

    channel_purpose: ChannelPurpose
    channel_purpose_status: VerificationStatus
    channel_purpose_rule: str | None = None
    channel_purpose_source_text: str | None = None

    @field_validator("channel_id", "source_name")
    @classmethod
    def required_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v

    @model_validator(mode="after")
    def check_statuses(self) -> Channel:
        if self.source_status == VerificationStatus.SOURCE_EXPLICIT:
            if not self.evidence.source_id.strip():
                raise ValueError(
                    "SOURCE_EXPLICIT channel requires EvidenceRef.source_id"
                )
        _require_system_derived_lineage(
            self.channel_type_status,
            rule=self.channel_type_rule,
            note=None,
            field_label="channel_type",
        )
        _require_system_derived_lineage(
            self.channel_purpose_status,
            rule=self.channel_purpose_rule,
            note=None,
            field_label="channel_purpose",
        )
        return self


class LegalBasis(ContractModel):
    legal_basis_id: str
    evidence: EvidenceRef

    law_name: str
    law_name_status: VerificationStatus
    article: str | None = None
    article_status: VerificationStatus | None = None
    text_excerpt: str | None = None

    @field_validator("legal_basis_id", "law_name")
    @classmethod
    def required_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v

    @model_validator(mode="after")
    def check_source_explicit_evidence(self) -> LegalBasis:
        if self.law_name_status == VerificationStatus.SOURCE_EXPLICIT:
            if not self.evidence.source_id.strip():
                raise ValueError(
                    "SOURCE_EXPLICIT legal basis requires EvidenceRef.source_id"
                )
        return self


# ---------------------------------------------------------------------------
# Condition (three layers)
# ---------------------------------------------------------------------------


class ConditionExecutable(ContractModel):
    """Layer 3: Executable Rule — F04 consumable only when VERIFIED."""

    operator: str
    verification_status: VerificationStatus
    usable_by_rule_engine: bool

    @field_validator("operator")
    @classmethod
    def operator_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("operator must be non-empty")
        return v

    @model_validator(mode="after")
    def must_be_verified_executable(self) -> ConditionExecutable:
        if self.verification_status != VerificationStatus.VERIFIED:
            raise ValueError(
                "executable.verification_status must be VERIFIED"
            )
        if not self.usable_by_rule_engine:
            raise ValueError(
                "executable.usable_by_rule_engine must be true"
            )
        return self


class Condition(ContractModel):
    """Condition with three layers: Source / Normalized / Executable."""

    condition_id: str
    role: ConditionRole
    evidence: EvidenceRef | None = None

    # Layer 1
    source_text: str | None = None
    source_status: VerificationStatus

    # Layer 2
    field: str | None = None
    normalized_values: list[str] | None = None
    normalized_status: VerificationStatus | None = None
    normalization_rule: str | None = None
    derivation_note: str | None = None

    # Layer 3
    executable: ConditionExecutable | None = None

    @field_validator("condition_id")
    @classmethod
    def condition_id_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("condition_id must be non-empty")
        return v

    @model_validator(mode="after")
    def check_layers(self) -> Condition:
        if self.source_status == VerificationStatus.SOURCE_EXPLICIT:
            if self.evidence is None or not self.evidence.source_id.strip():
                raise ValueError(
                    "SOURCE_EXPLICIT condition requires EvidenceRef"
                )

        if self.source_status == VerificationStatus.TO_CONFIRM:
            if self.executable is not None:
                raise ValueError(
                    "TO_CONFIRM condition must not have executable rule"
                )

        if self.normalized_status == VerificationStatus.SYSTEM_DERIVED:
            _require_system_derived_lineage(
                self.normalized_status,
                rule=self.normalization_rule,
                note=self.derivation_note,
                field_label="normalized_values",
            )

        return self


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def _duplicate_ids(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    dupes: list[str] = []
    for item in ids:
        if item in seen and item not in dupes:
            dupes.append(item)
        seen.add(item)
    return dupes


class BusinessSnapshot(ContractModel):
    """Top-level Business Data Contract document for one business."""

    schema_version: str
    business: Business
    sources: list[SourceRecord]
    materials: list[Material]
    handling_locations: list[HandlingLocation]
    channels: list[Channel]
    legal_basis: list[LegalBasis]
    conditions: list[Condition]

    @field_validator("schema_version")
    @classmethod
    def schema_version_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("schema_version must be non-empty")
        return v

    @model_validator(mode="after")
    def check_source_references(self) -> BusinessSnapshot:
        id_groups: list[tuple[str, list[str]]] = [
            ("source_id", [s.source_id for s in self.sources]),
            ("material_id", [m.material_id for m in self.materials]),
            (
                "location_id",
                [loc.location_id for loc in self.handling_locations],
            ),
            ("channel_id", [ch.channel_id for ch in self.channels]),
            (
                "legal_basis_id",
                [lb.legal_basis_id for lb in self.legal_basis],
            ),
            (
                "condition_id",
                [cond.condition_id for cond in self.conditions],
            ),
        ]
        for label, values in id_groups:
            dupes = _duplicate_ids(values)
            if dupes:
                raise ValueError(
                    f"duplicate {label}: {', '.join(dupes)}"
                )

        source_ids = {s.source_id for s in self.sources}
        if not source_ids:
            raise ValueError("sources must not be empty")

        missing: list[str] = []

        def need(sid: str | None, label: str) -> None:
            if sid is None:
                return
            if sid not in source_ids:
                missing.append(f"{label} -> {sid}")

        need(self.business.primary_source_id, "business.primary_source_id")
        need(self.business.metadata_source_id, "business.metadata_source_id")

        for m in self.materials:
            need(m.evidence.source_id, f"material:{m.material_id}")
        for loc in self.handling_locations:
            need(loc.evidence.source_id, f"location:{loc.location_id}")
        for ch in self.channels:
            need(ch.evidence.source_id, f"channel:{ch.channel_id}")
        for lb in self.legal_basis:
            need(lb.evidence.source_id, f"legal_basis:{lb.legal_basis_id}")
        for cond in self.conditions:
            if cond.evidence is not None:
                need(
                    cond.evidence.source_id,
                    f"condition:{cond.condition_id}",
                )

        if missing:
            raise ValueError(
                "unknown source_id references: " + "; ".join(missing)
            )
        return self


def load_snapshot(path: Path | str) -> BusinessSnapshot:
    """Load and validate a BusinessSnapshot JSON file.

    Does not mutate timestamps; reads JSON as stored.
    """
    file_path = Path(path)
    return BusinessSnapshot.model_validate_json(
        file_path.read_text(encoding="utf-8")
    )


def snapshot_from_dict(data: dict[str, Any]) -> BusinessSnapshot:
    """Validate a dict as BusinessSnapshot (for tests / fixtures)."""
    return BusinessSnapshot.model_validate(data)
