"""F03 JsonBusinessRepository: exact BusinessSnapshot queries and public filter."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from gov_service_agent.business_data.models import (
    Business,
    BusinessSnapshot,
    Channel,
    Condition,
    HandlingLocation,
    LegalBasis,
    Material,
    VerificationStatus,
    load_snapshot,
)


class ConsumptionMode(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"


class BusinessNotFoundError(LookupError):
    """Raised when business_id is not in the repository index."""


class DuplicateBusinessError(ValueError):
    """Raised when loading snapshots with a duplicate business_id."""


class RelationType(str, Enum):
    HAS_MATERIAL = "HAS_MATERIAL"
    HANDLED_AT = "HANDLED_AT"
    AVAILABLE_VIA = "AVAILABLE_VIA"
    HAS_LEGAL_BASIS = "HAS_LEGAL_BASIS"
    HAS_CONDITION = "HAS_CONDITION"


class TargetType(str, Enum):
    MATERIAL = "MATERIAL"
    HANDLING_LOCATION = "HANDLING_LOCATION"
    CHANNEL = "CHANNEL"
    LEGAL_BASIS = "LEGAL_BASIS"
    CONDITION = "CONDITION"


class BusinessRelation(BaseModel):
    """Lightweight Knowledge Relation View DTO (runtime projection only)."""

    model_config = ConfigDict(extra="forbid")

    business_id: str
    relation_type: RelationType
    target_type: TargetType
    target_id: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# Public consumption gates (allowlist + fail-closed)
# ---------------------------------------------------------------------------


def _primary_status_is_public(status: VerificationStatus) -> bool:
    """Allowlist: only SOURCE_EXPLICIT and VERIFIED are public primary facts."""
    return status in (
        VerificationStatus.SOURCE_EXPLICIT,
        VerificationStatus.VERIFIED,
    )


def _system_derived_meta_ok(*, rule: str | None, note: str | None) -> bool:
    return bool((rule and rule.strip()) or (note and note.strip()))


def _evidence_present(evidence_source_id: str | None) -> bool:
    return bool(evidence_source_id and evidence_source_id.strip())


def is_public_material(m: Material) -> bool:
    if not _primary_status_is_public(m.source_status):
        return False
    if m.source_status == VerificationStatus.SOURCE_EXPLICIT:
        if not _evidence_present(m.evidence.source_id):
            return False
    if m.requirement_level_status == VerificationStatus.SYSTEM_DERIVED:
        if not _system_derived_meta_ok(rule=None, note=m.derivation_note):
            return False
        if m.source_status != VerificationStatus.SOURCE_EXPLICIT:
            return False
        if not _evidence_present(m.evidence.source_id):
            return False
    elif m.requirement_level_status == VerificationStatus.TO_CONFIRM:
        return False
    elif m.requirement_level_status not in (
        VerificationStatus.SOURCE_EXPLICIT,
        VerificationStatus.VERIFIED,
        VerificationStatus.SYSTEM_DERIVED,
    ):
        return False
    return True


def is_public_handling_location(loc: HandlingLocation) -> bool:
    for status in (loc.name_status, loc.address_status, loc.service_hours.source_status):
        if not _primary_status_is_public(status):
            return False
    if loc.name_status == VerificationStatus.SOURCE_EXPLICIT or (
        loc.address_status == VerificationStatus.SOURCE_EXPLICIT
    ):
        if not _evidence_present(loc.evidence.source_id):
            return False
    return True


def is_public_channel(ch: Channel) -> bool:
    if not _primary_status_is_public(ch.source_status):
        return False
    if ch.source_status == VerificationStatus.SOURCE_EXPLICIT:
        if not _evidence_present(ch.evidence.source_id):
            return False

    for status, rule in (
        (ch.channel_type_status, ch.channel_type_rule),
        (ch.channel_purpose_status, ch.channel_purpose_rule),
    ):
        if status == VerificationStatus.SYSTEM_DERIVED:
            if not _system_derived_meta_ok(rule=rule, note=None):
                return False
            if ch.source_status != VerificationStatus.SOURCE_EXPLICIT:
                return False
            if not _evidence_present(ch.evidence.source_id):
                return False
        elif status == VerificationStatus.TO_CONFIRM:
            return False
        elif status not in (
            VerificationStatus.SOURCE_EXPLICIT,
            VerificationStatus.VERIFIED,
            VerificationStatus.SYSTEM_DERIVED,
        ):
            return False
    return True


def is_public_legal_basis(lb: LegalBasis) -> bool:
    if not _primary_status_is_public(lb.law_name_status):
        return False
    if lb.law_name_status == VerificationStatus.SOURCE_EXPLICIT:
        if not _evidence_present(lb.evidence.source_id):
            return False
    if lb.article_status is not None:
        if not _primary_status_is_public(lb.article_status):
            return False
    return True


def is_public_condition(c: Condition) -> bool:
    """Whole-condition fail-closed: no partial filtered Condition copies."""
    if not _primary_status_is_public(c.source_status):
        return False
    if c.source_status == VerificationStatus.SOURCE_EXPLICIT:
        if c.evidence is None or not _evidence_present(c.evidence.source_id):
            return False

    if c.normalized_status is None:
        return True

    if c.normalized_status == VerificationStatus.TO_CONFIRM:
        return False
    if c.normalized_status == VerificationStatus.SYSTEM_DERIVED:
        if not _system_derived_meta_ok(
            rule=c.normalization_rule,
            note=c.derivation_note,
        ):
            return False
        if c.source_status != VerificationStatus.SOURCE_EXPLICIT:
            return False
        if c.evidence is None or not _evidence_present(c.evidence.source_id):
            return False
        return True
    if c.normalized_status in (
        VerificationStatus.SOURCE_EXPLICIT,
        VerificationStatus.VERIFIED,
    ):
        return True
    return False


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class JsonBusinessRepository:
    """Exact-id BusinessSnapshot index. No LLM, search, or transition."""

    def __init__(self, snapshots: dict[str, BusinessSnapshot]) -> None:
        self._snapshots = dict(snapshots)

    @classmethod
    def from_paths(cls, paths: Sequence[Path | str]) -> JsonBusinessRepository:
        index: dict[str, BusinessSnapshot] = {}
        for path in paths:
            snapshot = load_snapshot(path)
            bid = snapshot.business.business_id
            if bid in index:
                raise DuplicateBusinessError(f"duplicate business_id: {bid}")
            index[bid] = snapshot
        return cls(index)

    def has_business(self, business_id: str) -> bool:
        return business_id in self._snapshots

    def has_condition(self, business_id: str, condition_id: str) -> bool:
        if business_id not in self._snapshots:
            return False
        return any(
            c.condition_id == condition_id
            for c in self._snapshots[business_id].conditions
        )

    def get_snapshot(self, business_id: str) -> BusinessSnapshot:
        try:
            return self._snapshots[business_id]
        except KeyError as exc:
            raise BusinessNotFoundError(
                f"unknown business_id: {business_id}"
            ) from exc

    def get_business(self, business_id: str) -> Business:
        return self.get_snapshot(business_id).business

    def get_materials(
        self,
        business_id: str,
        *,
        consumption: ConsumptionMode = ConsumptionMode.PUBLIC,
    ) -> list[Material]:
        materials = self.get_snapshot(business_id).materials
        if consumption == ConsumptionMode.INTERNAL:
            return list(materials)
        return [m for m in materials if is_public_material(m)]

    def get_handling_locations(
        self,
        business_id: str,
        *,
        consumption: ConsumptionMode = ConsumptionMode.PUBLIC,
    ) -> list[HandlingLocation]:
        locations = self.get_snapshot(business_id).handling_locations
        if consumption == ConsumptionMode.INTERNAL:
            return list(locations)
        return [loc for loc in locations if is_public_handling_location(loc)]

    def get_channels(
        self,
        business_id: str,
        *,
        consumption: ConsumptionMode = ConsumptionMode.PUBLIC,
    ) -> list[Channel]:
        channels = self.get_snapshot(business_id).channels
        if consumption == ConsumptionMode.INTERNAL:
            return list(channels)
        return [ch for ch in channels if is_public_channel(ch)]

    def get_legal_basis(
        self,
        business_id: str,
        *,
        consumption: ConsumptionMode = ConsumptionMode.PUBLIC,
    ) -> list[LegalBasis]:
        items = self.get_snapshot(business_id).legal_basis
        if consumption == ConsumptionMode.INTERNAL:
            return list(items)
        return [lb for lb in items if is_public_legal_basis(lb)]

    def get_conditions(
        self,
        business_id: str,
        *,
        consumption: ConsumptionMode = ConsumptionMode.PUBLIC,
    ) -> list[Condition]:
        conditions = self.get_snapshot(business_id).conditions
        if consumption == ConsumptionMode.INTERNAL:
            return list(conditions)
        return [c for c in conditions if is_public_condition(c)]

    def list_relations(
        self,
        business_id: str,
        *,
        consumption: ConsumptionMode = ConsumptionMode.PUBLIC,
    ) -> list[BusinessRelation]:
        relations: list[BusinessRelation] = []
        for m in self.get_materials(business_id, consumption=consumption):
            relations.append(
                BusinessRelation(
                    business_id=business_id,
                    relation_type=RelationType.HAS_MATERIAL,
                    target_type=TargetType.MATERIAL,
                    target_id=m.material_id,
                )
            )
        for loc in self.get_handling_locations(
            business_id, consumption=consumption
        ):
            relations.append(
                BusinessRelation(
                    business_id=business_id,
                    relation_type=RelationType.HANDLED_AT,
                    target_type=TargetType.HANDLING_LOCATION,
                    target_id=loc.location_id,
                )
            )
        for ch in self.get_channels(business_id, consumption=consumption):
            relations.append(
                BusinessRelation(
                    business_id=business_id,
                    relation_type=RelationType.AVAILABLE_VIA,
                    target_type=TargetType.CHANNEL,
                    target_id=ch.channel_id,
                )
            )
        for lb in self.get_legal_basis(business_id, consumption=consumption):
            relations.append(
                BusinessRelation(
                    business_id=business_id,
                    relation_type=RelationType.HAS_LEGAL_BASIS,
                    target_type=TargetType.LEGAL_BASIS,
                    target_id=lb.legal_basis_id,
                )
            )
        for cond in self.get_conditions(business_id, consumption=consumption):
            relations.append(
                BusinessRelation(
                    business_id=business_id,
                    relation_type=RelationType.HAS_CONDITION,
                    target_type=TargetType.CONDITION,
                    target_id=cond.condition_id,
                )
            )
        return relations
