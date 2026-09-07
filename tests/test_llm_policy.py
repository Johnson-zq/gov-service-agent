"""F07 remote Data Policy unit tests."""

from __future__ import annotations

import pytest

from gov_service_agent.llm.policy import (
    PolicyDecision,
    collect_request_classifications,
    evaluate_remote_policy,
    evaluate_request_remote_policy,
)
from gov_service_agent.llm.types import (
    DataClassification,
    LlmMessage,
    LlmRequest,
    LlmRole,
)


def _msg(
    *classifications: DataClassification,
    content: str = "synthetic",
) -> LlmMessage:
    return LlmMessage(
        role=LlmRole.USER,
        content=content,
        classifications=frozenset(classifications),
    )


@pytest.mark.parametrize(
    "classification",
    [
        DataClassification.PUBLIC_BUSINESS_METADATA,
        DataClassification.SYSTEM_CONTROL_DATA,
        DataClassification.SYNTHETIC_TEST_DATA,
    ],
)
def test_remote_allow(classification: DataClassification) -> None:
    decision = evaluate_remote_policy({classification})
    assert decision.allowed is True
    assert decision.denied_categories == frozenset()
    assert decision.reason_code == "POLICY_ALLOWED"


@pytest.mark.parametrize(
    "classification",
    [
        DataClassification.USER_FREE_TEXT,
        DataClassification.USER_PII,
        DataClassification.HIGH_SENSITIVE_IDENTITY,
        DataClassification.TO_CONFIRM_OR_INTERNAL,
        DataClassification.UNKNOWN,
    ],
)
def test_remote_deny(classification: DataClassification) -> None:
    decision = evaluate_remote_policy({classification})
    assert decision.allowed is False
    assert classification in decision.denied_categories
    assert decision.reason_code == "POLICY_DENIED"


def test_empty_classifications_are_unknown_deny() -> None:
    assert evaluate_remote_policy(None).allowed is False
    assert evaluate_remote_policy([]).allowed is False
    assert evaluate_remote_policy(frozenset()).allowed is False
    assert DataClassification.UNKNOWN in evaluate_remote_policy([]).denied_categories


def test_missing_message_classifications_unknown_deny() -> None:
    request = LlmRequest(messages=[_msg()])
    assert collect_request_classifications(request) == frozenset(
        {DataClassification.UNKNOWN}
    )
    decision = evaluate_request_remote_policy(request)
    assert decision.allowed is False


@pytest.mark.parametrize(
    "allowed,denied",
    [
        (
            DataClassification.PUBLIC_BUSINESS_METADATA,
            DataClassification.USER_PII,
        ),
        (
            DataClassification.SYSTEM_CONTROL_DATA,
            DataClassification.UNKNOWN,
        ),
        (
            DataClassification.SYNTHETIC_TEST_DATA,
            DataClassification.TO_CONFIRM_OR_INTERNAL,
        ),
    ],
)
def test_mixed_payload_deny(
    allowed: DataClassification,
    denied: DataClassification,
) -> None:
    decision = evaluate_remote_policy({allowed, denied})
    assert decision.allowed is False
    assert denied in decision.denied_categories


def test_policy_result_excludes_content() -> None:
    decision = evaluate_remote_policy({DataClassification.USER_PII})
    blob = repr(decision) + str(decision)
    assert "synthetic secret text" not in blob
    assert isinstance(decision, PolicyDecision)
    assert "USER_PII" in {c.value for c in decision.denied_categories}


def test_policy_deterministic() -> None:
    classes = {
        DataClassification.PUBLIC_BUSINESS_METADATA,
        DataClassification.USER_FREE_TEXT,
    }
    first = evaluate_remote_policy(classes)
    second = evaluate_remote_policy(classes)
    assert first == second
