"""F09 Explanation Side Route: protocol, LLM backend, local safety guard."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gov_service_agent.llm.provider import LlmProvider
from gov_service_agent.llm.structured import parse_structured_output
from gov_service_agent.llm.types import (
    DataClassification,
    LlmMessage,
    LlmRequest,
    LlmRole,
)

_TOPIC_MAX_LEN = 64
_EXPLANATION_MAX_LEN = 500

_HIGH_RISK_MARKERS: frozenset[str] = frozenset(
    {
        "材料",
        "提交材料",
        "准备材料",
        "需要携带",
        "携带",
        "办理地点",
        "办理窗口",
        "窗口",
        "地址",
        "费用",
        "金额",
        "缴费金额",
        "办理时限",
        "工作日",
        "法律依据",
        "政策依据",
        "资格条件",
        "符合条件",
        "办理条件",
    }
)


class ExplanationStatus(StrEnum):
    ANSWERED = "answered"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"


class ExplanationRequest(BaseModel):
    """Mechanical privacy boundary: no raw user utterance fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    topic: str
    public_context: dict[str, str] = Field(default_factory=dict)

    @field_validator("topic")
    @classmethod
    def _validate_topic(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("topic must be nonblank")
        if len(stripped) > _TOPIC_MAX_LEN:
            raise ValueError("topic exceeds max length 64")
        return stripped

    @field_validator("public_context")
    @classmethod
    def _validate_context(cls, value: dict[str, str]) -> dict[str, str]:
        owned: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("public_context keys must be nonblank str")
            if not isinstance(item, str) or not item.strip():
                raise ValueError("public_context values must be nonblank str")
            owned[key] = item
        return owned


class ExplanationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ExplanationStatus
    topic: str
    text: str | None = None

    @field_validator("topic")
    @classmethod
    def _topic(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("topic must be nonblank")
        return stripped

    @model_validator(mode="after")
    def _check_matrix(self) -> ExplanationResult:
        if self.status == ExplanationStatus.ANSWERED:
            if self.text is None or not self.text.strip():
                raise ValueError("ANSWERED requires nonblank text")
            if len(self.text.strip()) > _EXPLANATION_MAX_LEN:
                raise ValueError("explanation text exceeds max length 500")
            return self
        if self.text is not None:
            raise ValueError(f"{self.status.value} forbids text")
        return self


class ExplanationStructuredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    explanation: str = Field(min_length=1, max_length=_EXPLANATION_MAX_LEN)

    @field_validator("explanation")
    @classmethod
    def _trim(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("explanation must be nonblank after trim")
        if len(stripped) > _EXPLANATION_MAX_LEN:
            raise ValueError("explanation exceeds max length 500")
        return stripped


@runtime_checkable
class ExplanationService(Protocol):
    def explain(self, request: ExplanationRequest) -> ExplanationResult: ...


def is_safe_explanation_text(text: str) -> bool:
    """Conservative local Demo guardrail against actionable government facts."""
    if not text or not text.strip():
        return False
    for marker in _HIGH_RISK_MARKERS:
        if marker in text:
            return False
    return True


class LlmExplanationService:
    """Provider-neutral concept explanation. Not an authoritative fact source."""

    def __init__(self, provider: LlmProvider) -> None:
        self._provider = provider

    def explain(self, request: ExplanationRequest) -> ExplanationResult:
        context_lines = ""
        if request.public_context:
            pairs = [f"{k}={v}" for k, v in request.public_context.items()]
            context_lines = "public_context:\n" + "\n".join(pairs) + "\n"
        system = (
            "You explain one public government concept in plain language.\n"
            "Return STRICT JSON only: {\"explanation\": \"...\"}.\n"
            "Constraints: concept explanation only; max 500 characters.\n"
            "Forbidden: materials, locations, windows, addresses, fees, amounts, "
            "deadlines, legal basis, eligibility judgments, business decisions, "
            "business_id, or recommending a specific matter."
        )
        user = (
            f"task=explain_public_concept\n"
            f"topic={request.topic}\n"
            f"{context_lines}"
        )
        llm_request = LlmRequest(
            messages=[
                LlmMessage(
                    role=LlmRole.SYSTEM,
                    content=system,
                    classifications=frozenset(
                        {DataClassification.SYSTEM_CONTROL_DATA}
                    ),
                ),
                LlmMessage(
                    role=LlmRole.USER,
                    content=user,
                    classifications=frozenset(
                        {
                            DataClassification.SYSTEM_CONTROL_DATA,
                            DataClassification.PUBLIC_BUSINESS_METADATA,
                        }
                    ),
                ),
            ],
            operation="f09_explain_public_concept",
        )
        response = self._provider.complete(llm_request)
        parsed = parse_structured_output(
            response.content,
            ExplanationStructuredOutput,
        )
        return ExplanationResult(
            status=ExplanationStatus.ANSWERED,
            topic=request.topic,
            text=parsed.value.explanation,
        )
