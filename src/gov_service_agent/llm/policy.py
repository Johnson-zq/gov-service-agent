"""Remote Data Policy evaluator (F07). Deterministic; no network/LLM/DB."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from gov_service_agent.llm.types import (
    DataClassification,
    LlmRequest,
    RemoteDataPolicyProfile,
)

_REMOTE_ALLOW: frozenset[DataClassification] = frozenset(
    {
        DataClassification.PUBLIC_BUSINESS_METADATA,
        DataClassification.SYSTEM_CONTROL_DATA,
        DataClassification.SYNTHETIC_TEST_DATA,
    }
)

_REMOTE_ALLOW_DEMO_APPROVED: frozenset[DataClassification] = frozenset(
    {
        DataClassification.PUBLIC_BUSINESS_METADATA,
        DataClassification.SYSTEM_CONTROL_DATA,
        DataClassification.SYNTHETIC_TEST_DATA,
        DataClassification.USER_FREE_TEXT,
        DataClassification.USER_PII,
        DataClassification.HIGH_SENSITIVE_IDENTITY,
        DataClassification.TO_CONFIRM_OR_INTERNAL,
    }
)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    denied_categories: frozenset[DataClassification]
    reason_code: str


def _allow_set_for_profile(
    profile: RemoteDataPolicyProfile,
) -> frozenset[DataClassification]:
    if profile == RemoteDataPolicyProfile.DEMO_APPROVED:
        return _REMOTE_ALLOW_DEMO_APPROVED
    # DEFAULT and any unexpected value: fail closed to original allow-set.
    return _REMOTE_ALLOW


def _normalize_classifications(
    classifications: Iterable[DataClassification] | None,
) -> frozenset[DataClassification]:
    if classifications is None:
        return frozenset({DataClassification.UNKNOWN})
    collected = frozenset(classifications)
    if not collected:
        return frozenset({DataClassification.UNKNOWN})
    return collected


def collect_request_classifications(request: LlmRequest) -> frozenset[DataClassification]:
    """Aggregate explicit classifications from all messages (empty → UNKNOWN)."""
    aggregated: set[DataClassification] = set()
    for message in request.messages:
        if not message.classifications:
            aggregated.add(DataClassification.UNKNOWN)
        else:
            aggregated.update(message.classifications)
    if not aggregated:
        return frozenset({DataClassification.UNKNOWN})
    return frozenset(aggregated)


def evaluate_remote_policy(
    classifications: Iterable[DataClassification] | None,
    profile: RemoteDataPolicyProfile = RemoteDataPolicyProfile.DEFAULT,
) -> PolicyDecision:
    """
    Fail-closed remote dispatch policy.

    Classification is caller-supplied security metadata only — never inferred
    from natural-language content. Profile is explicit deployment configuration.
    """
    normalized = _normalize_classifications(classifications)
    allow_set = _allow_set_for_profile(profile)
    denied = frozenset(c for c in normalized if c not in allow_set)
    if denied:
        return PolicyDecision(
            allowed=False,
            denied_categories=denied,
            reason_code="POLICY_DENIED",
        )
    return PolicyDecision(
        allowed=True,
        denied_categories=frozenset(),
        reason_code="POLICY_ALLOWED",
    )


def evaluate_request_remote_policy(
    request: LlmRequest,
    profile: RemoteDataPolicyProfile = RemoteDataPolicyProfile.DEFAULT,
) -> PolicyDecision:
    """Evaluate remote policy for a full LlmRequest."""
    return evaluate_remote_policy(
        collect_request_classifications(request),
        profile=profile,
    )
