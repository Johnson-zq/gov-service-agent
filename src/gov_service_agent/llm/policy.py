"""Remote Data Policy evaluator (F07). Deterministic; no network/LLM/DB."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from gov_service_agent.llm.types import DataClassification, LlmRequest

_REMOTE_ALLOW: frozenset[DataClassification] = frozenset(
    {
        DataClassification.PUBLIC_BUSINESS_METADATA,
        DataClassification.SYSTEM_CONTROL_DATA,
        DataClassification.SYNTHETIC_TEST_DATA,
    }
)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    denied_categories: frozenset[DataClassification]
    reason_code: str


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
) -> PolicyDecision:
    """
    Fail-closed remote dispatch policy.

    Classification is caller-supplied security metadata only — never inferred
    from natural-language content.
    """
    normalized = _normalize_classifications(classifications)
    denied = frozenset(c for c in normalized if c not in _REMOTE_ALLOW)
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


def evaluate_request_remote_policy(request: LlmRequest) -> PolicyDecision:
    """Evaluate remote policy for a full LlmRequest."""
    return evaluate_remote_policy(collect_request_classifications(request))
