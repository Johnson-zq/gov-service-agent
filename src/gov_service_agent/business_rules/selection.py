"""F04 Executable Rule Selection / Readiness (no expression evaluation)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gov_service_agent.business_data.models import Condition, VerificationStatus
from gov_service_agent.business_data.repository import (
    ConsumptionMode,
    JsonBusinessRepository,
)


class RuleSelectionStatus(str, Enum):
    NO_RULES = "NO_RULES"
    RULES_AVAILABLE_UNEVALUATED = "RULES_AVAILABLE_UNEVALUATED"


class RuleSelectionResult(BaseModel):
    """Readiness result: which conditions are executable VERIFIED rules."""

    model_config = ConfigDict(extra="forbid")

    business_id: str
    status: RuleSelectionStatus
    selected_rule_ids: list[str]
    skipped_non_executable_count: int = Field(ge=0)

    @model_validator(mode="after")
    def check_status_vs_selected(self) -> RuleSelectionResult:
        if self.status == RuleSelectionStatus.NO_RULES:
            if self.selected_rule_ids:
                raise ValueError(
                    "NO_RULES requires selected_rule_ids to be empty"
                )
        elif self.status == RuleSelectionStatus.RULES_AVAILABLE_UNEVALUATED:
            if not self.selected_rule_ids:
                raise ValueError(
                    "RULES_AVAILABLE_UNEVALUATED requires non-empty "
                    "selected_rule_ids"
                )
        else:
            raise ValueError(f"unsupported RuleSelectionStatus: {self.status}")
        return self


def _is_executable_verified(condition: Condition) -> bool:
    executable = condition.executable
    if executable is None:
        return False
    if executable.verification_status != VerificationStatus.VERIFIED:
        return False
    if not executable.usable_by_rule_engine:
        return False
    return True


def select_executable_rules(
    business_id: str,
    repository: JsonBusinessRepository,
) -> RuleSelectionResult:
    """Select executable VERIFIED rules for a business (readiness only).

    Does not evaluate rules, accept facts, or return PASS/FAIL.
    Unknown business_id propagates BusinessNotFoundError from repository.
    """
    conditions = repository.get_conditions(
        business_id,
        consumption=ConsumptionMode.INTERNAL,
    )
    selected_rule_ids = [
        c.condition_id for c in conditions if _is_executable_verified(c)
    ]
    skipped = len(conditions) - len(selected_rule_ids)
    if selected_rule_ids:
        status = RuleSelectionStatus.RULES_AVAILABLE_UNEVALUATED
    else:
        status = RuleSelectionStatus.NO_RULES
    return RuleSelectionResult(
        business_id=business_id,
        status=status,
        selected_rule_ids=selected_rule_ids,
        skipped_non_executable_count=skipped,
    )
