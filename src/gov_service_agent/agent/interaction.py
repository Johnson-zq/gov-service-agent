"""F09 Missing-slot interaction domain, mapping, local detector, validation."""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Protocol, runtime_checkable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from gov_service_agent.business_graph.transition import TransitionResult, TransitionStatus
from gov_service_agent.llm.provider import LlmProvider
from gov_service_agent.llm.structured import parse_structured_output
from gov_service_agent.llm.types import (
    DataClassification,
    LlmMessage,
    LlmRequest,
    LlmRole,
)

_F09_ARTIFACT_KEY = "f09"
_TOPIC_MAX_LEN = 64
_DEFAULT_MIN_CONFIDENCE = 0.80

_EXPLANATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*什么是\s*(.+?)\s*[?？!！。.\s]*$"),
    re.compile(r"^\s*(.+?)\s*是什么意思\s*[?？!！。.\s]*$"),
    re.compile(r"^\s*(.+?)\s*是指什么\s*[?？!！。.\s]*$"),
    re.compile(r"^\s*请解释一下\s*(.+?)\s*[?？!！。.\s]*$"),
    re.compile(r"^\s*请解释下\s*(.+?)\s*[?？!！。.\s]*$"),
    re.compile(r"^\s*能解释一下\s*(.+?)\s*吗\s*[?？!！。.\s]*$"),
    re.compile(r"^\s*可以解释一下\s*(.+?)\s*吗\s*[?？!！。.\s]*$"),
)

_POLITE_TAIL = re.compile(
    r"(?:一下|下|呢|啊|呀|吧|嘛|谢谢|请问)+$",
)

_FALLBACK_EXPLANATION_UNAVAILABLE = (
    "这个概念我暂时无法提供可靠解释，我们先继续确认您要办理的业务。"
)
_FALLBACK_UNCERTAIN = "我还不能确定您的意思，请根据当前选项再说明一下。"
_FALLBACK_OTHER = (
    "您刚才的内容没有直接回答当前办理选项，我们先继续确认当前事项。"
)


class UtteranceKind(StrEnum):
    SLOT_ANSWER = "slot_answer"
    EXPLANATION_REQUEST = "explanation_request"
    UNCERTAIN = "uncertain"
    OTHER = "other"


class MapperUtteranceKind(StrEnum):
    SLOT_ANSWER = "slot_answer"
    UNCERTAIN = "uncertain"
    OTHER = "other"


class MappingValidationStatus(StrEnum):
    ACCEPTED = "accepted"
    INVALID_VALUE = "invalid_value"
    LOW_CONFIDENCE = "low_confidence"
    NOT_SLOT_ANSWER = "not_slot_answer"


class InteractionFailureKind(StrEnum):
    MAPPER_PROVIDER_ERROR = "mapper_provider_error"
    MAPPER_PARSE_ERROR = "mapper_parse_error"
    EXPLANATION_PROVIDER_ERROR = "explanation_provider_error"
    EXPLANATION_PARSE_ERROR = "explanation_parse_error"
    EXPLANATION_UNSAFE_OUTPUT = "explanation_unsafe_output"


def _reject_non_finite_confidence(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("confidence must be a finite float")
    if value < 0.0 or value > 1.0:
        raise ValueError("confidence must be in [0.0, 1.0]")
    return value


def _require_nonblank(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-blank str")
    return value


class UtteranceInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: UtteranceKind
    mapped_value: str | None = None
    confidence: float | None = None
    explanation_topic: str | None = None

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return _reject_non_finite_confidence(value)

    @model_validator(mode="after")
    def _check_matrix(self) -> UtteranceInterpretation:
        if self.kind == UtteranceKind.SLOT_ANSWER:
            if self.mapped_value is None or not self.mapped_value.strip():
                raise ValueError("SLOT_ANSWER requires nonblank mapped_value")
            if self.confidence is None:
                raise ValueError("SLOT_ANSWER requires confidence")
            if self.explanation_topic is not None:
                raise ValueError("SLOT_ANSWER forbids explanation_topic")
            return self
        if self.kind == UtteranceKind.EXPLANATION_REQUEST:
            if self.mapped_value is not None or self.confidence is not None:
                raise ValueError(
                    "EXPLANATION_REQUEST forbids mapped_value and confidence"
                )
            if (
                self.explanation_topic is None
                or not self.explanation_topic.strip()
            ):
                raise ValueError(
                    "EXPLANATION_REQUEST requires nonblank explanation_topic"
                )
            return self
        if self.mapped_value is not None or self.confidence is not None:
            raise ValueError(f"{self.kind.value} forbids mapped_value/confidence")
        if self.explanation_topic is not None:
            raise ValueError(f"{self.kind.value} forbids explanation_topic")
        return self


class AnswerMapperOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: MapperUtteranceKind
    mapped_value: str | None = None
    confidence: float | None = None

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return _reject_non_finite_confidence(value)

    @model_validator(mode="after")
    def _check_matrix(self) -> AnswerMapperOutput:
        if self.kind == MapperUtteranceKind.SLOT_ANSWER:
            if self.mapped_value is None or not self.mapped_value.strip():
                raise ValueError("SLOT_ANSWER requires nonblank mapped_value")
            if self.confidence is None:
                raise ValueError("SLOT_ANSWER requires confidence")
            return self
        if self.mapped_value is not None or self.confidence is not None:
            raise ValueError(f"{self.kind.value} forbids mapped_value/confidence")
        return self


class SlotInteractionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    transition_status: TransitionStatus
    current_node_id: str
    required_slot: str
    allowed_values: tuple[str, ...]
    question_text: str
    invalid_value: str | None = None
    current_slots: dict[str, str] = Field(default_factory=dict)

    @field_validator("current_node_id", "required_slot", "question_text")
    @classmethod
    def _nonblank_str(cls, value: str) -> str:
        return _require_nonblank(value, field_name="field")

    @field_validator("allowed_values")
    @classmethod
    def _validate_allowed(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("allowed_values must be non-empty")
        cleaned: list[str] = []
        for item in value:
            cleaned.append(_require_nonblank(item, field_name="allowed_values item"))
        return tuple(cleaned)

    @field_validator("current_slots")
    @classmethod
    def _validate_slots(cls, value: dict[str, str]) -> dict[str, str]:
        owned: dict[str, str] = {}
        for key, item in value.items():
            owned[_require_nonblank(key, field_name="current_slots key")] = (
                _require_nonblank(item, field_name="current_slots value")
            )
        return owned

    @model_validator(mode="after")
    def _check_status_matrix(self) -> SlotInteractionContext:
        if self.transition_status not in (
            TransitionStatus.NEED_SLOT,
            TransitionStatus.INVALID_SLOT,
        ):
            raise ValueError(
                "transition_status must be NEED_SLOT or INVALID_SLOT"
            )
        if self.transition_status == TransitionStatus.NEED_SLOT:
            if self.invalid_value is not None:
                raise ValueError("NEED_SLOT forbids invalid_value")
            return self
        if self.invalid_value is None or not self.invalid_value.strip():
            raise ValueError("INVALID_SLOT requires nonblank invalid_value")
        return self


def build_slot_interaction_context(
    result: TransitionResult,
    current_slots: Mapping[str, str] | None = None,
) -> SlotInteractionContext:
    """Build SlotInteractionContext from F04 TransitionResult + slots."""
    if result.status not in (
        TransitionStatus.NEED_SLOT,
        TransitionStatus.INVALID_SLOT,
    ):
        raise ValueError(
            "SlotInteractionContext requires NEED_SLOT or INVALID_SLOT"
        )
    if result.allowed_values is None:
        raise ValueError("TransitionResult.allowed_values is required")
    if result.required_slot is None or result.question_text is None:
        raise ValueError("TransitionResult missing required_slot/question_text")
    slots = dict(current_slots) if current_slots is not None else {}
    return SlotInteractionContext(
        transition_status=result.status,
        current_node_id=result.current_node_id,
        required_slot=result.required_slot,
        allowed_values=tuple(result.allowed_values),
        question_text=result.question_text,
        invalid_value=result.invalid_value,
        current_slots=slots,
    )


@dataclass(frozen=True, slots=True)
class MappingPolicy:
    min_confidence: float = _DEFAULT_MIN_CONFIDENCE

    def __post_init__(self) -> None:
        _reject_non_finite_confidence(self.min_confidence)


class ValidatedSlot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    slot_name: str
    value: str
    confidence: float

    @field_validator("slot_name", "value")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        return _require_nonblank(value, field_name="field")

    @field_validator("confidence")
    @classmethod
    def _confidence(cls, value: float) -> float:
        return _reject_non_finite_confidence(value)


class MappingValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: MappingValidationStatus
    validated_slot: ValidatedSlot | None = None

    @model_validator(mode="after")
    def _check_matrix(self) -> MappingValidationResult:
        if self.status == MappingValidationStatus.ACCEPTED:
            if self.validated_slot is None:
                raise ValueError("ACCEPTED requires validated_slot")
            return self
        if self.validated_slot is not None:
            raise ValueError(f"{self.status.value} forbids validated_slot")
        return self


def validate_slot_mapping(
    interpretation: UtteranceInterpretation,
    context: SlotInteractionContext,
    policy: MappingPolicy,
) -> MappingValidationResult:
    """Deterministic membership-then-confidence validation."""
    if interpretation.kind != UtteranceKind.SLOT_ANSWER:
        return MappingValidationResult(
            status=MappingValidationStatus.NOT_SLOT_ANSWER,
            validated_slot=None,
        )
    assert interpretation.mapped_value is not None
    assert interpretation.confidence is not None
    if interpretation.mapped_value not in context.allowed_values:
        return MappingValidationResult(
            status=MappingValidationStatus.INVALID_VALUE,
            validated_slot=None,
        )
    if interpretation.confidence < policy.min_confidence:
        return MappingValidationResult(
            status=MappingValidationStatus.LOW_CONFIDENCE,
            validated_slot=None,
        )
    return MappingValidationResult(
        status=MappingValidationStatus.ACCEPTED,
        validated_slot=ValidatedSlot(
            slot_name=context.required_slot,
            value=interpretation.mapped_value,
            confidence=interpretation.confidence,
        ),
    )


class AnswerMappingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    required_slot: str
    allowed_values: tuple[str, ...]
    user_text: str

    @field_validator("required_slot", "user_text")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        return _require_nonblank(value, field_name="field")

    @field_validator("allowed_values")
    @classmethod
    def _allowed(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("allowed_values must be non-empty")
        return tuple(
            _require_nonblank(item, field_name="allowed_values item")
            for item in value
        )


@runtime_checkable
class AnswerMapper(Protocol):
    def map_answer(self, request: AnswerMappingRequest) -> AnswerMapperOutput: ...


class LlmAnswerMapper:
    """Provider-backed answer mapper. Policy enforcement remains in Provider."""

    def __init__(self, provider: LlmProvider) -> None:
        self._provider = provider

    def map_answer(self, request: AnswerMappingRequest) -> AnswerMapperOutput:
        allowed = ", ".join(request.allowed_values)
        system = (
            "You map a user utterance to one controlled slot value.\n"
            "Return STRICT JSON only with fields: kind, mapped_value, confidence.\n"
            "kind must be one of: slot_answer, uncertain, other.\n"
            "For slot_answer: mapped_value must be exactly one allowed value; "
            "confidence must be a finite float in [0,1].\n"
            "For uncertain/other: mapped_value and confidence must be null.\n"
            "Never output next_node, business_id, rule_result, materials, "
            "locations, channels, or legal_basis.\n"
            "Never classify explanation questions as slot_answer."
        )
        user = (
            f"required_slot={request.required_slot}\n"
            f"allowed_values=[{allowed}]\n"
            f"user_text={request.user_text}"
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
                            DataClassification.USER_FREE_TEXT,
                            DataClassification.SYSTEM_CONTROL_DATA,
                        }
                    ),
                ),
            ],
            operation="f09_slot_answer_mapping",
        )
        response = self._provider.complete(llm_request)
        parsed = parse_structured_output(response.content, AnswerMapperOutput)
        return parsed.value


def mapper_output_to_interpretation(
    output: AnswerMapperOutput,
) -> UtteranceInterpretation:
    if output.kind == MapperUtteranceKind.SLOT_ANSWER:
        return UtteranceInterpretation(
            kind=UtteranceKind.SLOT_ANSWER,
            mapped_value=output.mapped_value,
            confidence=output.confidence,
            explanation_topic=None,
        )
    if output.kind == MapperUtteranceKind.UNCERTAIN:
        return UtteranceInterpretation(
            kind=UtteranceKind.UNCERTAIN,
            mapped_value=None,
            confidence=None,
            explanation_topic=None,
        )
    return UtteranceInterpretation(
        kind=UtteranceKind.OTHER,
        mapped_value=None,
        confidence=None,
        explanation_topic=None,
    )


def _normalize_topic_candidate(raw: str) -> str | None:
    text = raw.strip()
    text = text.strip("?？!！。．.、,， ")
    text = _POLITE_TAIL.sub("", text).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return None
    if len(text) < 1 or len(text) > _TOPIC_MAX_LEN:
        return None
    return text


def detect_explanation_request(
    user_text: str,
    question_text: str,
) -> UtteranceInterpretation | None:
    """Local deterministic explanation detector. No network/LLM/embedding."""
    if not user_text or not question_text:
        return None
    candidate: str | None = None
    for pattern in _EXPLANATION_PATTERNS:
        match = pattern.match(user_text.strip())
        if match is None:
            continue
        candidate = _normalize_topic_candidate(match.group(1))
        break
    if candidate is None:
        return None
    if candidate not in question_text:
        return None
    return UtteranceInterpretation(
        kind=UtteranceKind.EXPLANATION_REQUEST,
        mapped_value=None,
        confidence=None,
        explanation_topic=candidate,
    )


class InteractionFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: InteractionFailureKind
    safe_message: str | None = None


def compose_explanation_response(explanation: str, question_text: str) -> str:
    return f"{explanation.strip()}\n\n{question_text}"


def compose_explanation_failure_response(question_text: str) -> str:
    return f"{_FALLBACK_EXPLANATION_UNAVAILABLE}\n\n{question_text}"


def compose_uncertain_response(question_text: str) -> str:
    return f"{_FALLBACK_UNCERTAIN}\n\n{question_text}"


def compose_other_response(question_text: str) -> str:
    return f"{_FALLBACK_OTHER}\n\n{question_text}"


def serialize_slot_context(context: SlotInteractionContext) -> dict[str, Any]:
    return context.model_dump(mode="json")


def deserialize_slot_context(payload: Mapping[str, Any]) -> SlotInteractionContext:
    data = dict(payload)
    allowed = data.get("allowed_values")
    if isinstance(allowed, list):
        data["allowed_values"] = tuple(allowed)
    status = data.get("transition_status")
    if isinstance(status, str):
        data["transition_status"] = TransitionStatus(status)
    return SlotInteractionContext.model_validate(data)


def serialize_interpretation(
    interpretation: UtteranceInterpretation,
) -> dict[str, Any]:
    return interpretation.model_dump(mode="json")


def deserialize_interpretation(
    payload: Mapping[str, Any],
) -> UtteranceInterpretation:
    return UtteranceInterpretation.model_validate(payload)


def serialize_mapping_validation(
    result: MappingValidationResult,
) -> dict[str, Any]:
    return result.model_dump(mode="json")


def deserialize_mapping_validation(
    payload: Mapping[str, Any],
) -> MappingValidationResult:
    return MappingValidationResult.model_validate(payload)


def serialize_transition_result(result: TransitionResult) -> dict[str, Any]:
    return {
        "status": result.status.value,
        "current_node_id": result.current_node_id,
        "required_slot": result.required_slot,
        "invalid_value": result.invalid_value,
        "allowed_values": (
            list(result.allowed_values) if result.allowed_values is not None else None
        ),
        "question_text": result.question_text,
        "candidate_business_id": result.candidate_business_id,
        "unsupported_reason": result.unsupported_reason,
        "visited_node_ids": list(result.visited_node_ids),
        "traversed_edge_ids": list(result.traversed_edge_ids),
    }


def empty_f09_namespace(slot_context: SlotInteractionContext) -> dict[str, Any]:
    return {
        "slot_context": serialize_slot_context(slot_context),
        "interpretation": None,
        "mapping_validation": None,
        "validated_slot": None,
        "explanation": None,
        "business_transition": None,
        "failure": None,
        "response_text": None,
    }


def merge_f09_artifacts(
    artifacts: dict[str, Any],
    f09_update: Mapping[str, Any],
) -> dict[str, Any]:
    """Deep-copy artifacts, merge/replace f09 namespace keys, preserve others."""
    owned = copy.deepcopy(artifacts)
    current = owned.get(_F09_ARTIFACT_KEY)
    if not isinstance(current, dict):
        current = {}
    merged = copy.deepcopy(current)
    merged.update(dict(f09_update))
    owned[_F09_ARTIFACT_KEY] = merged
    return owned


def read_f09(artifacts: Mapping[str, Any]) -> dict[str, Any]:
    value = artifacts.get(_F09_ARTIFACT_KEY)
    if not isinstance(value, dict):
        return {}
    return value


def interpretation_from_mapper_safe(
    output: AnswerMapperOutput,
) -> UtteranceInterpretation:
    try:
        return mapper_output_to_interpretation(output)
    except ValidationError as exc:
        raise ValueError("invalid mapper output conversion") from exc
