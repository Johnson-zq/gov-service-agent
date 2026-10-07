"""F09 interaction domain / detector / mapping / explanation unit tests."""

from __future__ import annotations

import json
import math
from typing import Any

import pytest
from pydantic import ValidationError

from gov_service_agent.agent.explanation import (
    ExplanationRequest,
    ExplanationResult,
    ExplanationStatus,
    LlmExplanationService,
    is_safe_explanation_text,
)
from gov_service_agent.agent.interaction import (
    AnswerMapperOutput,
    AnswerMappingRequest,
    InteractionFailureKind,
    LlmAnswerMapper,
    MapperUtteranceKind,
    MappingPolicy,
    MappingValidationStatus,
    SlotInteractionContext,
    UtteranceInterpretation,
    UtteranceKind,
    build_slot_interaction_context,
    compose_explanation_failure_response,
    compose_explanation_response,
    compose_other_response,
    compose_uncertain_response,
    detect_explanation_request,
    empty_f09_namespace,
    mapper_output_to_interpretation,
    serialize_slot_context,
    serialize_transition_result,
    validate_slot_mapping,
)
from gov_service_agent.business_data.semantics import ControlledAllowedValueSemantic
from gov_service_agent.business_graph.transition import (
    TransitionResult,
    TransitionStatus,
)
from gov_service_agent.llm.policy import evaluate_request_remote_policy
from gov_service_agent.llm.types import (
    DataClassification,
    LlmErrorCode,
    LlmProviderError,
    LlmRequest,
    LlmResponse,
    LlmRole,
    RemoteDataPolicyProfile,
    StructuredParseError,
)

_MAPPER_SYSTEM_PROMPT = (
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
_EMPLOYMENT_VALUES = (
    "self_employed_without_employees",
    "part_time_without_employer_insurance",
    "other_flexible_employment",
)
_EMPLOYMENT_MEANINGS = (
    "无雇工的个体工商户",
    "未在用人单位参加社会保险的非全日制从业人员",
    "其他灵活就业人员",
)


class CapturingLlmProvider:
    """Test-only provider: 0 network; records requests."""

    def __init__(
        self,
        *,
        content: str = '{"status":"demo"}',
        failure: LlmErrorCode | None = None,
    ) -> None:
        self.requests: list[LlmRequest] = []
        self._content = content
        self._failure = failure

    @property
    def provider_name(self) -> str:
        return "CAPTURE"

    @property
    def model_id(self) -> str | None:
        return None

    def complete(self, request: LlmRequest) -> LlmResponse:
        self.requests.append(request)
        if self._failure is not None:
            raise LlmProviderError(
                self._failure,
                message="controlled capture failure",
                retryable=False,
            )
        return LlmResponse(
            content=self._content,
            provider_name=self.provider_name,
            model_id=None,
            reasoning_present=False,
            finish_reason=None,
        )


def _need_slot_context(**overrides: Any) -> SlotInteractionContext:
    base = {
        "transition_status": TransitionStatus.NEED_SLOT,
        "current_node_id": "social_security_action",
        "required_slot": "service_action",
        "allowed_values": ("payment", "transfer", "inquiry", "other"),
        "question_text": (
            "您主要想办理社保缴费、社保转移，还是查询或其他业务？"
        ),
        "invalid_value": None,
        "current_slots": {},
    }
    base.update(overrides)
    return SlotInteractionContext(**base)


# --- enums ---


def test_utterance_kind_members_and_values() -> None:
    assert {m.value for m in UtteranceKind} == {
        "slot_answer",
        "explanation_request",
        "uncertain",
        "other",
    }


def test_mapper_utterance_kind_no_explanation() -> None:
    assert {m.value for m in MapperUtteranceKind} == {
        "slot_answer",
        "uncertain",
        "other",
    }
    assert not hasattr(MapperUtteranceKind, "EXPLANATION_REQUEST")


def test_interaction_failure_kinds() -> None:
    assert {m.value for m in InteractionFailureKind} == {
        "mapper_provider_error",
        "mapper_parse_error",
        "explanation_provider_error",
        "explanation_parse_error",
        "explanation_unsafe_output",
        "semantic_projection_partial",
        "semantic_projection_invalid",
    }


# --- interpretation / mapper output ---


@pytest.mark.parametrize(
    "payload",
    [
        {
            "kind": UtteranceKind.SLOT_ANSWER,
            "mapped_value": "transfer",
            "confidence": 0.9,
            "explanation_topic": None,
        },
        {
            "kind": UtteranceKind.EXPLANATION_REQUEST,
            "mapped_value": None,
            "confidence": None,
            "explanation_topic": "社保转移",
        },
        {
            "kind": UtteranceKind.UNCERTAIN,
            "mapped_value": None,
            "confidence": None,
            "explanation_topic": None,
        },
        {
            "kind": UtteranceKind.OTHER,
            "mapped_value": None,
            "confidence": None,
            "explanation_topic": None,
        },
    ],
)
def test_utterance_interpretation_valid_matrix(payload: dict[str, Any]) -> None:
    UtteranceInterpretation(**payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": UtteranceKind.SLOT_ANSWER, "confidence": 0.9},
        {"kind": UtteranceKind.SLOT_ANSWER, "mapped_value": "transfer"},
        {
            "kind": UtteranceKind.SLOT_ANSWER,
            "mapped_value": "transfer",
            "confidence": 0.9,
            "explanation_topic": "x",
        },
        {
            "kind": UtteranceKind.EXPLANATION_REQUEST,
            "mapped_value": "transfer",
            "explanation_topic": "社保转移",
        },
        {
            "kind": UtteranceKind.EXPLANATION_REQUEST,
            "confidence": 0.5,
            "explanation_topic": "社保转移",
        },
        {"kind": UtteranceKind.EXPLANATION_REQUEST},
        {
            "kind": UtteranceKind.UNCERTAIN,
            "mapped_value": "transfer",
        },
        {"kind": UtteranceKind.OTHER, "confidence": 0.2},
        {
            "kind": UtteranceKind.SLOT_ANSWER,
            "mapped_value": "transfer",
            "confidence": 0.9,
            "extra": 1,
        },
    ],
)
def test_utterance_interpretation_invalid_matrix(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        UtteranceInterpretation(**payload)


@pytest.mark.parametrize("value", [0.0, 0.8, 1.0])
def test_confidence_valid_bounds(value: float) -> None:
    UtteranceInterpretation(
        kind=UtteranceKind.SLOT_ANSWER,
        mapped_value="transfer",
        confidence=value,
    )


@pytest.mark.parametrize(
    "value",
    [-0.01, 1.01, float("nan"), float("inf"), float("-inf")],
)
def test_confidence_rejects_nonfinite_and_out_of_range(value: float) -> None:
    with pytest.raises(ValidationError):
        UtteranceInterpretation(
            kind=UtteranceKind.SLOT_ANSWER,
            mapped_value="transfer",
            confidence=value,
        )


def test_mapper_output_extra_business_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        AnswerMapperOutput.model_validate(
            {
                "kind": "slot_answer",
                "mapped_value": "transfer",
                "confidence": 1.0,
                "next_node": "bad",
            }
        )
    for extra_field in (
        "business_id",
        "candidate_business_id",
        "confirmed_business_id",
        "rule_result",
    ):
        with pytest.raises(ValidationError):
            AnswerMapperOutput.model_validate(
                {
                    "kind": "slot_answer",
                    "mapped_value": "transfer",
                    "confidence": 1.0,
                    extra_field: "X",
                }
            )


def test_mapper_output_to_interpretation_never_explanation() -> None:
    out = AnswerMapperOutput(
        kind=MapperUtteranceKind.OTHER,
        mapped_value=None,
        confidence=None,
    )
    converted = mapper_output_to_interpretation(out)
    assert converted.kind is UtteranceKind.OTHER


# --- context / policy / validation ---


def test_slot_context_need_and_invalid() -> None:
    need = _need_slot_context()
    assert need.invalid_value is None
    invalid = _need_slot_context(
        transition_status=TransitionStatus.INVALID_SLOT,
        invalid_value="invented",
    )
    assert invalid.invalid_value == "invented"


def test_slot_context_rejects_other_status() -> None:
    with pytest.raises(ValidationError):
        _need_slot_context(transition_status=TransitionStatus.ADVANCED)


def test_need_slot_forbids_invalid_value() -> None:
    with pytest.raises(ValidationError):
        _need_slot_context(invalid_value="x")


def test_invalid_slot_requires_invalid_value() -> None:
    with pytest.raises(ValidationError):
        _need_slot_context(
            transition_status=TransitionStatus.INVALID_SLOT,
            invalid_value=None,
        )


def test_allowed_values_and_slots_isolation() -> None:
    allowed = ["payment", "transfer"]
    slots = {"service_action": "payment"}
    ctx = _need_slot_context(
        allowed_values=tuple(allowed),
        current_slots=slots,
    )
    allowed.append("hacked")
    slots["service_action"] = "hacked"
    assert ctx.allowed_values == ("payment", "transfer")
    assert ctx.current_slots == {"service_action": "payment"}


def test_context_factory_from_transition() -> None:
    result = TransitionResult(
        status=TransitionStatus.NEED_SLOT,
        current_node_id="employment_type",
        required_slot="employment_type",
        allowed_values=["a", "b"],
        question_text="问就业类型？",
        visited_node_ids=["employment_type"],
        traversed_edge_ids=[],
    )
    ctx = build_slot_interaction_context(result, {"service_action": "payment"})
    assert ctx.required_slot == "employment_type"
    with pytest.raises(ValueError):
        build_slot_interaction_context(
            TransitionResult(
                status=TransitionStatus.FALLBACK,
                current_node_id="social_security_fallback",
                visited_node_ids=["social_security_fallback"],
                traversed_edge_ids=[],
            )
        )


def test_mapping_policy_default_and_bounds() -> None:
    policy = MappingPolicy()
    assert policy.min_confidence == 0.80
    MappingPolicy(min_confidence=0.0)
    MappingPolicy(min_confidence=1.0)
    with pytest.raises(ValueError):
        MappingPolicy(min_confidence=-0.1)
    with pytest.raises(ValueError):
        MappingPolicy(min_confidence=1.1)
    with pytest.raises(ValueError):
        MappingPolicy(min_confidence=float("nan"))


def test_validate_membership_first_and_threshold() -> None:
    ctx = _need_slot_context()
    policy = MappingPolicy()
    invented = UtteranceInterpretation(
        kind=UtteranceKind.SLOT_ANSWER,
        mapped_value="invented_value",
        confidence=1.0,
    )
    assert (
        validate_slot_mapping(invented, ctx, policy).status
        is MappingValidationStatus.INVALID_VALUE
    )
    low = UtteranceInterpretation(
        kind=UtteranceKind.SLOT_ANSWER,
        mapped_value="transfer",
        confidence=0.799999,
    )
    assert (
        validate_slot_mapping(low, ctx, policy).status
        is MappingValidationStatus.LOW_CONFIDENCE
    )
    below = UtteranceInterpretation(
        kind=UtteranceKind.SLOT_ANSWER,
        mapped_value="transfer",
        confidence=0.79,
    )
    assert (
        validate_slot_mapping(below, ctx, policy).status
        is MappingValidationStatus.LOW_CONFIDENCE
    )
    edge = UtteranceInterpretation(
        kind=UtteranceKind.SLOT_ANSWER,
        mapped_value="transfer",
        confidence=0.80,
    )
    accepted = validate_slot_mapping(edge, ctx, policy)
    assert accepted.status is MappingValidationStatus.ACCEPTED
    assert accepted.validated_slot is not None
    assert accepted.validated_slot.value == "transfer"


def test_not_slot_answer_for_uncertain_other_explanation() -> None:
    ctx = _need_slot_context()
    policy = MappingPolicy()
    for kind in (
        UtteranceKind.UNCERTAIN,
        UtteranceKind.OTHER,
        UtteranceKind.EXPLANATION_REQUEST,
    ):
        kwargs: dict[str, Any] = {
            "kind": kind,
            "mapped_value": None,
            "confidence": None,
            "explanation_topic": "社保转移"
            if kind is UtteranceKind.EXPLANATION_REQUEST
            else None,
        }
        result = validate_slot_mapping(
            UtteranceInterpretation(**kwargs),
            ctx,
            policy,
        )
        assert result.status is MappingValidationStatus.NOT_SLOT_ANSWER
        assert result.validated_slot is None


def test_answer_mapping_request_strict() -> None:
    AnswerMappingRequest(
        required_slot="service_action",
        allowed_values=("payment", "transfer"),
        user_text="我想转移",
    )
    with pytest.raises(ValidationError):
        AnswerMappingRequest(
            required_slot="",
            allowed_values=("payment",),
            user_text="x",
        )
    with pytest.raises(ValidationError):
        AnswerMappingRequest.model_validate(
            {
                "required_slot": "service_action",
                "allowed_values": ["payment"],
                "user_text": "x",
                "extra": 1,
            }
        )


# --- mapper provider ---


def test_llm_answer_mapper_valid_and_classifications() -> None:
    provider = CapturingLlmProvider(
        content='{"kind":"slot_answer","mapped_value":"transfer","confidence":0.91}'
    )
    mapper = LlmAnswerMapper(provider)
    out = mapper.map_answer(
        AnswerMappingRequest(
            required_slot="service_action",
            allowed_values=("payment", "transfer", "inquiry", "other"),
            user_text="我想办转移",
        )
    )
    assert out.kind is MapperUtteranceKind.SLOT_ANSWER
    assert provider.requests
    cats: set[DataClassification] = set()
    for message in provider.requests[0].messages:
        cats.update(message.classifications)
    assert DataClassification.USER_FREE_TEXT in cats
    assert DataClassification.SYSTEM_CONTROL_DATA in cats


def test_llm_answer_mapper_rejects_extra_and_invalid_json() -> None:
    bad_extra = CapturingLlmProvider(
        content=(
            '{"kind":"slot_answer","mapped_value":"transfer",'
            '"confidence":1.0,"business_id":"X"}'
        )
    )
    with pytest.raises(StructuredParseError):
        LlmAnswerMapper(bad_extra).map_answer(
            AnswerMappingRequest(
                required_slot="service_action",
                allowed_values=("transfer",),
                user_text="转移",
            )
        )
    bad_json = CapturingLlmProvider(content="not json at all")
    with pytest.raises(StructuredParseError):
        LlmAnswerMapper(bad_json).map_answer(
            AnswerMappingRequest(
                required_slot="service_action",
                allowed_values=("transfer",),
                user_text="转移",
            )
        )


# --- detector ---


def test_golden_detector_social_security_transfer() -> None:
    question = "您主要想办理社保缴费、社保转移，还是查询或其他业务？"
    hit = detect_explanation_request("什么是社保转移？", question)
    assert hit is not None
    assert hit.kind is UtteranceKind.EXPLANATION_REQUEST
    assert hit.explanation_topic == "社保转移"
    assert hit.mapped_value is None


def test_generic_detector_not_hardcoded() -> None:
    question = "您要办理事项A还是事项B？"
    hit = detect_explanation_request("什么是事项A？", question)
    assert hit is not None
    assert hit.explanation_topic == "事项A"


@pytest.mark.parametrize(
    "utterance",
    [
        "事项A是什么意思？",
        "事项A是指什么？",
        "请解释一下事项A",
        "能解释一下事项A吗？",
        "可以解释一下事项A吗？",
    ],
)
def test_generic_explanation_forms(utterance: str) -> None:
    question = "您要办理事项A还是事项B？"
    hit = detect_explanation_request(utterance, question)
    assert hit is not None
    assert hit.explanation_topic == "事项A"


_FLEXIBLE_EMPLOYMENT_QUESTION = "您属于哪种灵活就业情况？"


@pytest.mark.parametrize(
    "utterance",
    [
        "什么叫灵活就业",
        "什么叫灵活就业？",
        "什么叫灵活就业?",
    ],
)
def test_shenme_jiao_flexible_employment_is_explanation(utterance: str) -> None:
    hit = detect_explanation_request(utterance, _FLEXIBLE_EMPLOYMENT_QUESTION)
    assert hit is not None
    assert hit.kind is UtteranceKind.EXPLANATION_REQUEST
    assert hit.explanation_topic == "灵活就业"
    assert hit.mapped_value is None
    assert hit.confidence is None


def test_shenme_shi_flexible_employment_still_explanation() -> None:
    hit = detect_explanation_request(
        "什么是灵活就业？",
        _FLEXIBLE_EMPLOYMENT_QUESTION,
    )
    assert hit is not None
    assert hit.kind is UtteranceKind.EXPLANATION_REQUEST
    assert hit.explanation_topic == "灵活就业"


@pytest.mark.parametrize(
    ("utterance", "question"),
    [
        ("平时接零活，没有固定单位", _FLEXIBLE_EMPLOYMENT_QUESTION),
        ("我叫张三", "当前备注可能出现我叫张三，请确认灵活就业。"),
        ("这个项目叫自由职业", "这个项目叫自由职业，请选择灵活就业类型。"),
        ("他们叫我去窗口办理", "他们叫我去窗口办理，请先确认灵活就业。"),
    ],
)
def test_non_explanation_utterances_stay_unmatched(
    utterance: str,
    question: str,
) -> None:
    assert detect_explanation_request(utterance, question) is None


def test_unknown_topic_no_explanation() -> None:
    question = "您主要想办理社保缴费、社保转移，还是查询或其他业务？"
    assert detect_explanation_request("什么是养老金计算？", question) is None


def test_topic_length_gate() -> None:
    topic = "事项" + ("A" * 70)
    question = f"您要办理{topic}还是事项B？"
    assert detect_explanation_request(f"什么是{topic}？", question) is None


def test_comparison_question_deferred_no_explanation() -> None:
    question = "您主要想办理社保缴费、社保转移，还是查询或其他业务？"
    assert (
        detect_explanation_request(
            "社保缴费和社保转移有什么区别？",
            question,
        )
        is None
    )


# --- explanation ---


def test_explanation_request_forbids_raw_fields() -> None:
    ExplanationRequest(topic="事项A", public_context={})
    for forbidden in (
        {"user_text": "x"},
        {"input_text": "x"},
        {"question_text": "x"},
        {"raw_query": "x"},
        {"history": "x"},
        {"reasoning": "x"},
    ):
        with pytest.raises(ValidationError):
            ExplanationRequest.model_validate(
                {"topic": "事项A", "public_context": {}, **forbidden}
            )


def test_explanation_request_topic_bounds() -> None:
    with pytest.raises(ValidationError):
        ExplanationRequest(topic="   ")
    with pytest.raises(ValidationError):
        ExplanationRequest(topic="x" * 65)


def test_explanation_result_matrix_and_length() -> None:
    ExplanationResult(
        status=ExplanationStatus.ANSWERED,
        topic="事项A",
        text="x" * 500,
    )
    with pytest.raises(ValidationError):
        ExplanationResult(
            status=ExplanationStatus.ANSWERED,
            topic="事项A",
            text="x" * 501,
        )
    ExplanationResult(
        status=ExplanationStatus.UNSUPPORTED,
        topic="事项A",
        text=None,
    )
    with pytest.raises(ValidationError):
        ExplanationResult(
            status=ExplanationStatus.UNSUPPORTED,
            topic="事项A",
            text="nope",
        )


def test_llm_explanation_service_classifications_and_payload() -> None:
    provider = CapturingLlmProvider(
        content='{"explanation":"事项A是一个受控公共概念说明。"}'
    )
    service = LlmExplanationService(provider)
    raw_user = "麻烦你告诉我一下什么是事项A呀？"
    result = service.explain(
        ExplanationRequest(
            topic="事项A",
            public_context={"demo": "public"},
        )
    )
    assert result.status is ExplanationStatus.ANSWERED
    assert provider.requests
    request = provider.requests[0]
    cats: set[DataClassification] = set()
    blob = ""
    for message in request.messages:
        cats.update(message.classifications)
        blob += message.content
    assert DataClassification.USER_FREE_TEXT not in cats
    assert DataClassification.SYSTEM_CONTROL_DATA in cats
    assert DataClassification.PUBLIC_BUSINESS_METADATA in cats
    assert "事项A" in blob
    assert raw_user not in blob
    assert "demo=public" in blob


def test_explanation_extra_field_and_prose_rejected() -> None:
    with pytest.raises(StructuredParseError):
        LlmExplanationService(
            CapturingLlmProvider(
                content='{"explanation":"ok","materials":"bad"}'
            )
        ).explain(ExplanationRequest(topic="事项A"))
    with pytest.raises(StructuredParseError):
        LlmExplanationService(
            CapturingLlmProvider(content='Here is JSON: {"explanation":"ok"}')
        ).explain(ExplanationRequest(topic="事项A"))


@pytest.mark.parametrize(
    "text",
    [
        "需要携带材料办理",
        "请到办理地点窗口",
        "费用金额是多少",
        "办理时限五个工作日",
        "法律依据与政策依据",
        "资格条件符合条件",
        "办理条件如下",
    ],
)
def test_safety_guard_high_risk(text: str) -> None:
    assert is_safe_explanation_text(text) is False


def test_safety_guard_safe_and_no_rewrite() -> None:
    assert is_safe_explanation_text("社保转移一般指保险关系转移接续。") is True


def test_response_composition_helpers() -> None:
    q = "原问题不变"
    assert compose_explanation_response("解释A", q) == f"解释A\n\n{q}"
    assert compose_explanation_failure_response(q).endswith(q)
    assert compose_uncertain_response(q).endswith(q)
    assert compose_other_response(q).endswith(q)


def test_artifact_serialization_allow_nan_false() -> None:
    ctx = _need_slot_context()
    payload = empty_f09_namespace(ctx)
    json.dumps(payload, allow_nan=False)
    result = TransitionResult(
        status=TransitionStatus.NEED_SLOT,
        current_node_id="n1",
        required_slot="s",
        allowed_values=["a"],
        question_text="q",
        visited_node_ids=["n1"],
        traversed_edge_ids=[],
    )
    json.dumps(serialize_transition_result(result), allow_nan=False)
    json.dumps(serialize_slot_context(ctx), allow_nan=False)
    assert not math.isnan(0.8)


def _employment_semantics() -> tuple[ControlledAllowedValueSemantic, ...]:
    return tuple(
        ControlledAllowedValueSemantic(value=value, meaning=meaning)
        for value, meaning in zip(
            _EMPLOYMENT_VALUES,
            _EMPLOYMENT_MEANINGS,
            strict=True,
        )
    )


def _map_and_capture(
    *,
    semantics: tuple[ControlledAllowedValueSemantic, ...] | None,
) -> LlmRequest:
    provider = CapturingLlmProvider(
        content='{"kind":"uncertain","mapped_value":null,"confidence":null}'
    )
    LlmAnswerMapper(provider).map_answer(
        AnswerMappingRequest(
            required_slot="employment_type",
            allowed_values=_EMPLOYMENT_VALUES,
            allowed_value_semantics=semantics,
            user_text="平时接零活，没有固定单位",
        )
    )
    assert len(provider.requests) == 1
    return provider.requests[0]


def _message(request: LlmRequest, role: LlmRole):
    return next(item for item in request.messages if item.role is role)


def test_legacy_none_prompt_has_no_meanings() -> None:
    request = _map_and_capture(semantics=None)
    user = _message(request, LlmRole.USER).content
    assert user == (
        "required_slot=employment_type\n"
        "allowed_values=["
        "self_employed_without_employees, "
        "part_time_without_employer_insurance, "
        "other_flexible_employment]\n"
        "user_text=平时接零活，没有固定单位"
    )
    assert "allowed_value_meanings" not in user


def test_full_prompt_keeps_values_and_adds_meanings() -> None:
    request = _map_and_capture(semantics=_employment_semantics())
    user = _message(request, LlmRole.USER).content
    lines = user.splitlines()
    assert lines[0] == "required_slot=employment_type"
    assert lines[1] == (
        "allowed_values=["
        "self_employed_without_employees, "
        "part_time_without_employer_insurance, "
        "other_flexible_employment]"
    )
    assert lines[2].startswith("allowed_value_meanings=")
    payload = json.loads(lines[2].split("=", 1)[1])
    assert payload == [
        {"value": value, "meaning": meaning}
        for value, meaning in zip(
            _EMPLOYMENT_VALUES,
            _EMPLOYMENT_MEANINGS,
            strict=True,
        )
    ]
    assert lines[3] == "user_text=平时接零活，没有固定单位"


def test_system_prompt_unchanged_for_none_and_full() -> None:
    forbidden = ("0.80", "threshold", "few-shot", "Golden", "置信度")
    for semantics in (None, _employment_semantics()):
        request = _map_and_capture(semantics=semantics)
        system = _message(request, LlmRole.SYSTEM).content
        assert system == _MAPPER_SYSTEM_PROMPT
        for token in forbidden:
            assert token not in system


def test_full_and_none_classifications_are_exact() -> None:
    none_request = _map_and_capture(semantics=None)
    assert _message(none_request, LlmRole.SYSTEM).classifications == frozenset(
        {DataClassification.SYSTEM_CONTROL_DATA}
    )
    assert _message(none_request, LlmRole.USER).classifications == frozenset(
        {
            DataClassification.USER_FREE_TEXT,
            DataClassification.SYSTEM_CONTROL_DATA,
        }
    )
    full_request = _map_and_capture(semantics=_employment_semantics())
    assert _message(full_request, LlmRole.SYSTEM).classifications == frozenset(
        {DataClassification.SYSTEM_CONTROL_DATA}
    )
    full_user = frozenset(
        {
            DataClassification.USER_FREE_TEXT,
            DataClassification.SYSTEM_CONTROL_DATA,
            DataClassification.PUBLIC_BUSINESS_METADATA,
        }
    )
    assert _message(full_request, LlmRole.USER).classifications == full_user
    demo = evaluate_request_remote_policy(
        full_request,
        profile=RemoteDataPolicyProfile.DEMO_APPROVED,
    )
    assert demo.allowed is True
    default = evaluate_request_remote_policy(
        full_request,
        profile=RemoteDataPolicyProfile.DEFAULT,
    )
    assert default.allowed is False
    assert DataClassification.USER_FREE_TEXT in default.denied_categories


def test_none_semantics_is_legacy_empty_tuple_is_not() -> None:
    AnswerMappingRequest(
        required_slot="employment_type",
        allowed_values=_EMPLOYMENT_VALUES,
        allowed_value_semantics=None,
        user_text="平时接零活",
    )
    with pytest.raises(ValidationError):
        AnswerMappingRequest(
            required_slot="employment_type",
            allowed_values=_EMPLOYMENT_VALUES,
            allowed_value_semantics=(),
            user_text="平时接零活",
        )


def test_semantics_alignment_rejects_count_and_order() -> None:
    one = (ControlledAllowedValueSemantic(value=_EMPLOYMENT_VALUES[0], meaning="甲"),)
    with pytest.raises(ValidationError):
        AnswerMappingRequest(
            required_slot="employment_type",
            allowed_values=_EMPLOYMENT_VALUES,
            allowed_value_semantics=one,
            user_text="平时接零活",
        )
    swapped = (
        ControlledAllowedValueSemantic(value=_EMPLOYMENT_VALUES[1], meaning="乙"),
        ControlledAllowedValueSemantic(value=_EMPLOYMENT_VALUES[0], meaning="甲"),
        ControlledAllowedValueSemantic(value=_EMPLOYMENT_VALUES[2], meaning="丙"),
    )
    with pytest.raises(ValidationError):
        AnswerMappingRequest(
            required_slot="employment_type",
            allowed_values=_EMPLOYMENT_VALUES,
            allowed_value_semantics=swapped,
            user_text="平时接零活",
        )
