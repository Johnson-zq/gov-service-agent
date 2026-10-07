"""Project controlled allowed-value semantics from public Business Data."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import ConfigDict, Field, model_validator

from gov_service_agent.business_data.models import Condition, ContractModel
from gov_service_agent.business_data.repository import (
    BusinessNotFoundError,
    ConsumptionMode,
    JsonBusinessRepository,
)
from gov_service_agent.business_graph.models import SourceConditionRef

REASON_NONE = "none"
REASON_FULL = "full"
REASON_PARTIAL_MISSING = "partial_missing_values"
REASON_INVALID_EXTRA = "invalid_extra_value"
REASON_INVALID_DUPLICATE = "invalid_duplicate_value"
REASON_INVALID_BLANK = "invalid_blank_meaning"
REASON_INVALID_FIELD = "invalid_field_mismatch"
REASON_INVALID_NORMALIZED = "invalid_normalized_value"
REASON_INVALID_UNAPPROVED = "invalid_unapproved_ref"


class SemanticCoverage(StrEnum):
    FULL = "FULL"
    NONE = "NONE"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID"


class ControlledAllowedValueSemantic(ContractModel):
    """One machine value plus its approved business wording."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str = Field(min_length=1)
    meaning: str = Field(min_length=1)

    @model_validator(mode="after")
    def _nonblank(self) -> ControlledAllowedValueSemantic:
        if not self.value.strip() or not self.meaning.strip():
            raise ValueError("value and meaning must be non-blank")
        return self


class SemanticProjectionResult(ContractModel):
    """Coverage decision. Only FULL carries mapper-ready semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    coverage: SemanticCoverage
    semantics: tuple[ControlledAllowedValueSemantic, ...] = ()
    reason_code: str = Field(min_length=1)

    @model_validator(mode="after")
    def _matrix(self) -> SemanticProjectionResult:
        if self.coverage is SemanticCoverage.FULL:
            if not self.semantics:
                raise ValueError("FULL requires semantics")
            return self
        if self.semantics:
            raise ValueError("only FULL may carry semantics")
        return self


def project_allowed_value_semantics(
    repository: JsonBusinessRepository,
    *,
    slot_name: str,
    allowed_values: Sequence[str],
    source_condition_refs: Sequence[SourceConditionRef] | None,
) -> SemanticProjectionResult:
    """
    Project ordered semantics for one slot.

    Empty refs are NONE and do not query the repository.
    Eligibility uses JsonBusinessRepository PUBLIC conditions only.
    """
    if not source_condition_refs:
        return SemanticProjectionResult(
            coverage=SemanticCoverage.NONE,
            semantics=(),
            reason_code=REASON_NONE,
        )

    allowed = tuple(allowed_values)
    allowed_set = set(allowed)
    found: dict[str, str] = {}

    for ref in source_condition_refs:
        condition = _public_condition(repository, ref)
        if condition is None:
            return _invalid(REASON_INVALID_UNAPPROVED)
        defect = _condition_defect(condition, slot_name, allowed_set, found)
        if defect is not None:
            return _invalid(defect)
        assert condition.normalized_values is not None
        assert condition.source_text is not None
        value = condition.normalized_values[0]
        found[value] = condition.source_text.strip()

    if len(found) != len(allowed) or any(value not in found for value in allowed):
        return SemanticProjectionResult(
            coverage=SemanticCoverage.PARTIAL,
            semantics=(),
            reason_code=REASON_PARTIAL_MISSING,
        )

    ordered = tuple(
        ControlledAllowedValueSemantic(value=value, meaning=found[value])
        for value in allowed
    )
    return SemanticProjectionResult(
        coverage=SemanticCoverage.FULL,
        semantics=ordered,
        reason_code=REASON_FULL,
    )


def _invalid(reason_code: str) -> SemanticProjectionResult:
    return SemanticProjectionResult(
        coverage=SemanticCoverage.INVALID,
        semantics=(),
        reason_code=reason_code,
    )


def _public_condition(
    repository: JsonBusinessRepository,
    ref: SourceConditionRef,
) -> Condition | None:
    try:
        conditions = repository.get_conditions(
            ref.business_id,
            consumption=ConsumptionMode.PUBLIC,
        )
    except BusinessNotFoundError:
        return None
    for condition in conditions:
        if condition.condition_id == ref.condition_id:
            return condition
    return None


def _condition_defect(
    condition: Condition,
    slot_name: str,
    allowed_set: set[str],
    found: dict[str, str],
) -> str | None:
    if condition.field != slot_name:
        return REASON_INVALID_FIELD
    values = condition.normalized_values
    if (
        not isinstance(values, list)
        or len(values) != 1
        or not isinstance(values[0], str)
        or not values[0].strip()
    ):
        return REASON_INVALID_NORMALIZED
    meaning = condition.source_text
    if not isinstance(meaning, str) or not meaning.strip():
        return REASON_INVALID_BLANK
    value = values[0]
    if value not in allowed_set:
        return REASON_INVALID_EXTRA
    if value in found:
        return REASON_INVALID_DUPLICATE
    return None
