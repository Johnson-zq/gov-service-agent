"""Private LangGraph orchestration nodes (F08 + F09). Not public API."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from gov_service_agent.agent.explanation import (
    ExplanationRequest,
    ExplanationResult,
    ExplanationStatus,
    is_safe_explanation_text,
)
from gov_service_agent.agent.interaction import (
    InteractionFailure,
    InteractionFailureKind,
    MappingValidationStatus,
    UtteranceInterpretation,
    UtteranceKind,
    compose_explanation_failure_response,
    compose_explanation_response,
    compose_other_response,
    compose_uncertain_response,
    deserialize_interpretation,
    deserialize_mapping_validation,
    deserialize_slot_context,
    detect_explanation_request,
    mapper_output_to_interpretation,
    merge_f09_artifacts,
    read_f09,
    serialize_interpretation,
    serialize_mapping_validation,
    serialize_transition_result,
    validate_slot_mapping,
    AnswerMappingRequest,
)
from gov_service_agent.agent.state import (
    AgentPhase,
    AgentState,
    AgentStateValidationError,
    WorkflowStatus,
    validate_agent_state,
)
from gov_service_agent.agent.terminal import (
    ConfirmationIntent,
    ConfirmationStatus,
    TerminalConfirmationMode,
    TerminalValidationStatus,
    assign_confirmed_business_id,
    build_terminal_failure,
    compose_terminal_response_text,
    deserialize_rule_readiness,
    deserialize_terminal_context,
    deserialize_terminal_validation,
    interpret_confirmation,
    merge_f10_artifacts,
    read_f10,
    serialize_confirmation,
    serialize_failure,
    serialize_rule_readiness,
    serialize_terminal_validation,
    validate_terminal_candidate,
)
from gov_service_agent.business_graph.transition import (
    TransitionStatus,
    advance_until_blocked,
)
from gov_service_agent.llm.types import LlmProviderError, StructuredParseError


def _prepare_node(state: AgentState) -> dict[str, Any]:
    """Advance RECEIVED → ORCHESTRATING; append orchestration trace delta."""
    validate_agent_state(state)
    return {
        "phase": AgentPhase.ORCHESTRATING,
        "orchestration_trace": ["prepare"],
    }


def _complete_node(state: AgentState) -> dict[str, Any]:
    """Advance ORCHESTRATING → COMPLETED; append orchestration trace delta."""
    validate_agent_state(state)
    return {
        "phase": AgentPhase.COMPLETED,
        "status": WorkflowStatus.COMPLETED,
        "error": None,
        "orchestration_trace": ["complete"],
    }


def _f09_partial(
    state: AgentState,
    f09_update: dict[str, Any],
    *,
    trace: str,
) -> dict[str, Any]:
    return {
        "artifacts": merge_f09_artifacts(state["artifacts"], f09_update),
        "orchestration_trace": [trace],
    }


def _f10_partial(
    state: AgentState,
    f10_update: dict[str, Any],
    *,
    trace: str,
) -> dict[str, Any]:
    return {
        "artifacts": merge_f10_artifacts(state["artifacts"], f10_update),
        "orchestration_trace": [trace],
    }


def _make_interpret_slot_input_node(
    deps: Any,
) -> Callable[[AgentState], dict[str, Any]]:
    def _interpret_slot_input(state: AgentState) -> dict[str, Any]:
        validate_agent_state(state)
        f09 = read_f09(state["artifacts"])
        context = deserialize_slot_context(f09["slot_context"])
        user_text = state["input_text"]

        detected = detect_explanation_request(user_text, context.question_text)
        if detected is not None:
            return _f09_partial(
                state,
                {
                    "interpretation": serialize_interpretation(detected),
                    "failure": None,
                },
                trace="interpret_slot_input",
            )

        request = AnswerMappingRequest(
            required_slot=context.required_slot,
            allowed_values=context.allowed_values,
            user_text=user_text,
        )
        try:
            output = deps.answer_mapper.map_answer(request)
            interpretation = mapper_output_to_interpretation(output)
            return _f09_partial(
                state,
                {
                    "interpretation": serialize_interpretation(interpretation),
                    "failure": None,
                },
                trace="interpret_slot_input",
            )
        except LlmProviderError:
            uncertain = UtteranceInterpretation(
                kind=UtteranceKind.UNCERTAIN,
                mapped_value=None,
                confidence=None,
                explanation_topic=None,
            )
            failure = InteractionFailure(
                kind=InteractionFailureKind.MAPPER_PROVIDER_ERROR,
                safe_message=None,
            )
            return _f09_partial(
                state,
                {
                    "interpretation": serialize_interpretation(uncertain),
                    "failure": failure.model_dump(mode="json"),
                },
                trace="interpret_slot_input",
            )
        except StructuredParseError:
            uncertain = UtteranceInterpretation(
                kind=UtteranceKind.UNCERTAIN,
                mapped_value=None,
                confidence=None,
                explanation_topic=None,
            )
            failure = InteractionFailure(
                kind=InteractionFailureKind.MAPPER_PARSE_ERROR,
                safe_message=None,
            )
            return _f09_partial(
                state,
                {
                    "interpretation": serialize_interpretation(uncertain),
                    "failure": failure.model_dump(mode="json"),
                },
                trace="interpret_slot_input",
            )

    return _interpret_slot_input


def _route_by_interpretation(state: AgentState) -> str:
    f09 = read_f09(state["artifacts"])
    interpretation = f09.get("interpretation")
    if not isinstance(interpretation, dict):
        raise AgentStateValidationError("f09.interpretation is required")
    kind = interpretation.get("kind")
    if kind == UtteranceKind.EXPLANATION_REQUEST.value:
        return "explain_current_topic"
    if kind == UtteranceKind.SLOT_ANSWER.value:
        return "validate_slot_answer"
    if kind in (
        UtteranceKind.UNCERTAIN.value,
        UtteranceKind.OTHER.value,
    ):
        return "resume_current_slot"
    raise AgentStateValidationError("unsupported interpretation kind")


def _make_explain_current_topic_node(
    deps: Any,
) -> Callable[[AgentState], dict[str, Any]]:
    def _explain_current_topic(state: AgentState) -> dict[str, Any]:
        validate_agent_state(state)
        f09 = read_f09(state["artifacts"])
        interpretation = deserialize_interpretation(f09["interpretation"])
        if interpretation.kind != UtteranceKind.EXPLANATION_REQUEST:
            raise AgentStateValidationError(
                "explain_current_topic requires EXPLANATION_REQUEST"
            )
        assert interpretation.explanation_topic is not None
        request = ExplanationRequest(
            topic=interpretation.explanation_topic,
            public_context={},
        )
        try:
            result = deps.explanation_service.explain(request)
            if result.status == ExplanationStatus.ANSWERED:
                assert result.text is not None
                if not is_safe_explanation_text(result.text):
                    unsafe = ExplanationResult(
                        status=ExplanationStatus.UNSUPPORTED,
                        topic=request.topic,
                        text=None,
                    )
                    failure = InteractionFailure(
                        kind=InteractionFailureKind.EXPLANATION_UNSAFE_OUTPUT,
                        safe_message=None,
                    )
                    return _f09_partial(
                        state,
                        {
                            "explanation": unsafe.model_dump(mode="json"),
                            "failure": failure.model_dump(mode="json"),
                        },
                        trace="explain_current_topic",
                    )
            return _f09_partial(
                state,
                {
                    "explanation": result.model_dump(mode="json"),
                    "failure": None,
                },
                trace="explain_current_topic",
            )
        except LlmProviderError:
            unavailable = ExplanationResult(
                status=ExplanationStatus.UNAVAILABLE,
                topic=request.topic,
                text=None,
            )
            failure = InteractionFailure(
                kind=InteractionFailureKind.EXPLANATION_PROVIDER_ERROR,
                safe_message=None,
            )
            return _f09_partial(
                state,
                {
                    "explanation": unavailable.model_dump(mode="json"),
                    "failure": failure.model_dump(mode="json"),
                },
                trace="explain_current_topic",
            )
        except StructuredParseError:
            unavailable = ExplanationResult(
                status=ExplanationStatus.UNAVAILABLE,
                topic=request.topic,
                text=None,
            )
            failure = InteractionFailure(
                kind=InteractionFailureKind.EXPLANATION_PARSE_ERROR,
                safe_message=None,
            )
            return _f09_partial(
                state,
                {
                    "explanation": unavailable.model_dump(mode="json"),
                    "failure": failure.model_dump(mode="json"),
                },
                trace="explain_current_topic",
            )

    return _explain_current_topic


def _make_validate_slot_answer_node(
    deps: Any,
) -> Callable[[AgentState], dict[str, Any]]:
    def _validate_slot_answer(state: AgentState) -> dict[str, Any]:
        validate_agent_state(state)
        f09 = read_f09(state["artifacts"])
        context = deserialize_slot_context(f09["slot_context"])
        interpretation = deserialize_interpretation(f09["interpretation"])
        result = validate_slot_mapping(
            interpretation,
            context,
            deps.mapping_policy,
        )
        validated = (
            result.validated_slot.model_dump(mode="json")
            if result.validated_slot is not None
            else None
        )
        return _f09_partial(
            state,
            {
                "mapping_validation": serialize_mapping_validation(result),
                "validated_slot": validated,
            },
            trace="validate_slot_answer",
        )

    return _validate_slot_answer


def _route_by_validation(state: AgentState) -> str:
    f09 = read_f09(state["artifacts"])
    validation = f09.get("mapping_validation")
    if not isinstance(validation, dict):
        raise AgentStateValidationError("f09.mapping_validation is required")
    status = validation.get("status")
    if status == MappingValidationStatus.ACCEPTED.value:
        return "advance_business_graph"
    if status in (
        MappingValidationStatus.INVALID_VALUE.value,
        MappingValidationStatus.LOW_CONFIDENCE.value,
        MappingValidationStatus.NOT_SLOT_ANSWER.value,
    ):
        return "resume_current_slot"
    raise AgentStateValidationError("unsupported mapping validation status")


def _make_advance_business_graph_node(
    deps: Any,
) -> Callable[[AgentState], dict[str, Any]]:
    def _advance_business_graph(state: AgentState) -> dict[str, Any]:
        validate_agent_state(state)
        f09 = read_f09(state["artifacts"])
        validation = deserialize_mapping_validation(f09["mapping_validation"])
        if validation.status != MappingValidationStatus.ACCEPTED:
            raise AgentStateValidationError(
                "advance_business_graph requires ACCEPTED validation"
            )
        if validation.validated_slot is None:
            raise AgentStateValidationError("validated_slot is required")
        context = deserialize_slot_context(f09["slot_context"])
        new_slots = copy.deepcopy(context.current_slots)
        new_slots[validation.validated_slot.slot_name] = (
            validation.validated_slot.value
        )
        result = advance_until_blocked(
            deps.decision_graph,
            context.current_node_id,
            new_slots,
        )
        response_text: str | None = None
        if result.status in (
            TransitionStatus.NEED_SLOT,
            TransitionStatus.INVALID_SLOT,
        ):
            response_text = result.question_text
        return _f09_partial(
            state,
            {
                "business_transition": serialize_transition_result(result),
                "response_text": response_text,
            },
            trace="advance_business_graph",
        )

    return _advance_business_graph


def _resume_current_slot_node(state: AgentState) -> dict[str, Any]:
    validate_agent_state(state)
    f09 = read_f09(state["artifacts"])
    context = deserialize_slot_context(f09["slot_context"])
    question = context.question_text
    interpretation_payload = f09.get("interpretation")
    if not isinstance(interpretation_payload, dict):
        raise AgentStateValidationError("f09.interpretation is required")
    interpretation = deserialize_interpretation(interpretation_payload)

    if interpretation.kind == UtteranceKind.EXPLANATION_REQUEST:
        explanation_payload = f09.get("explanation")
        if (
            isinstance(explanation_payload, dict)
            and explanation_payload.get("status")
            == ExplanationStatus.ANSWERED.value
            and isinstance(explanation_payload.get("text"), str)
            and is_safe_explanation_text(explanation_payload["text"])
        ):
            response = compose_explanation_response(
                explanation_payload["text"],
                question,
            )
        else:
            response = compose_explanation_failure_response(question)
    elif interpretation.kind == UtteranceKind.OTHER:
        response = compose_other_response(question)
    elif interpretation.kind == UtteranceKind.UNCERTAIN:
        response = compose_uncertain_response(question)
    else:
        # SLOT_ANSWER with non-accepted validation, or defensive fallback
        response = compose_uncertain_response(question)

    return _f09_partial(
        state,
        {"response_text": response},
        trace="resume_current_slot",
    )


# ---------------------------------------------------------------------------
# F10 Terminal Confirmation nodes / routers (private)
# ---------------------------------------------------------------------------


def _read_f10_validation(state: AgentState):
    f10 = read_f10(state["artifacts"])
    validation_payload = f10.get("terminal_validation")
    if not isinstance(validation_payload, dict):
        raise AgentStateValidationError("f10.terminal_validation is required")
    readiness = deserialize_rule_readiness(f10.get("rule_readiness"))
    return deserialize_terminal_validation(
        validation_payload,
        rule_readiness=readiness,
    )


def _make_validate_terminal_candidate_node(
    deps: Any,
) -> Callable[[AgentState], dict[str, Any]]:
    def _validate_terminal_candidate_node(state: AgentState) -> dict[str, Any]:
        validate_agent_state(state)
        f10 = read_f10(state["artifacts"])
        context_payload = f10.get("terminal_context")
        if not isinstance(context_payload, dict):
            raise AgentStateValidationError("f10.terminal_context is required")
        context = deserialize_terminal_context(context_payload)
        validation = validate_terminal_candidate(context, deps)

        if validation.status == TerminalValidationStatus.READY_FOR_CONFIRMATION:
            confirmation_status = ConfirmationStatus.AWAITING_CONFIRMATION
            failure = None
        else:
            confirmation_status = ConfirmationStatus.BLOCKED
            failure = build_terminal_failure(
                validation.status,
                canonical_name=validation.canonical_name,
            )

        return _f10_partial(
            state,
            {
                "terminal_validation": serialize_terminal_validation(validation),
                "rule_readiness": serialize_rule_readiness(
                    validation.rule_readiness
                ),
                "confirmation": serialize_confirmation(
                    status=confirmation_status,
                    intent=None,
                ),
                "confirmed_business_id": None,
                "failure": serialize_failure(failure),
            },
            trace="validate_terminal_candidate",
        )

    return _validate_terminal_candidate_node


def _route_by_terminal_validation(state: AgentState) -> str:
    f10 = read_f10(state["artifacts"])
    validation = f10.get("terminal_validation")
    if not isinstance(validation, dict):
        raise AgentStateValidationError("f10.terminal_validation is required")
    status = validation.get("status")
    if status != TerminalValidationStatus.READY_FOR_CONFIRMATION.value:
        return "compose_terminal_response"
    # Mode router (pure): PREPARE → compose; RESOLVE → interpret.
    return _route_by_terminal_mode(state)


def _route_by_terminal_mode(state: AgentState) -> str:
    f10 = read_f10(state["artifacts"])
    mode = f10.get("mode")
    if mode == TerminalConfirmationMode.PREPARE.value:
        return "compose_terminal_response"
    if mode == TerminalConfirmationMode.RESOLVE.value:
        return "interpret_confirmation"
    raise AgentStateValidationError("unsupported f10.mode")


def _interpret_confirmation_node(state: AgentState) -> dict[str, Any]:
    validate_agent_state(state)
    f10 = read_f10(state["artifacts"])
    if f10.get("mode") != TerminalConfirmationMode.RESOLVE.value:
        raise AgentStateValidationError(
            "interpret_confirmation requires RESOLVE mode"
        )
    validation = _read_f10_validation(state)
    if validation.status != TerminalValidationStatus.READY_FOR_CONFIRMATION:
        raise AgentStateValidationError(
            "interpret_confirmation requires READY_FOR_CONFIRMATION"
        )

    intent = interpret_confirmation(state["input_text"])
    if intent == ConfirmationIntent.CONFIRMED:
        confirmation_status = ConfirmationStatus.CONFIRMED
    elif intent == ConfirmationIntent.REJECTED:
        confirmation_status = ConfirmationStatus.REJECTED
    else:
        confirmation_status = ConfirmationStatus.UNCERTAIN

    return _f10_partial(
        state,
        {
            "confirmation": serialize_confirmation(
                status=confirmation_status,
                intent=intent,
            ),
            "confirmed_business_id": None,
            "failure": None,
        },
        trace="interpret_confirmation",
    )


def _route_by_confirmation_intent(state: AgentState) -> str:
    f10 = read_f10(state["artifacts"])
    confirmation = f10.get("confirmation")
    if not isinstance(confirmation, dict):
        raise AgentStateValidationError("f10.confirmation is required")
    intent = confirmation.get("intent")
    if intent == ConfirmationIntent.CONFIRMED.value:
        return "finalize_confirmation"
    if intent in (
        ConfirmationIntent.REJECTED.value,
        ConfirmationIntent.UNCERTAIN.value,
    ):
        return "compose_terminal_response"
    raise AgentStateValidationError("unsupported confirmation intent")


def _finalize_confirmation_node(state: AgentState) -> dict[str, Any]:
    validate_agent_state(state)
    f10 = read_f10(state["artifacts"])
    context_payload = f10.get("terminal_context")
    if not isinstance(context_payload, dict):
        raise AgentStateValidationError("f10.terminal_context is required")
    context = deserialize_terminal_context(context_payload)
    validation = _read_f10_validation(state)
    confirmation = f10.get("confirmation")
    if not isinstance(confirmation, dict):
        raise AgentStateValidationError("f10.confirmation is required")
    intent_raw = confirmation.get("intent")
    if intent_raw != ConfirmationIntent.CONFIRMED.value:
        raise AgentStateValidationError(
            "finalize_confirmation requires CONFIRMED intent"
        )
    intent = ConfirmationIntent.CONFIRMED

    confirmed = assign_confirmed_business_id(
        validation=validation,
        intent=intent,
        candidate_business_id=context.candidate_business_id,
    )
    if confirmed is None:
        raise AgentStateValidationError(
            "finalize_confirmation defense-in-depth rejected assignment"
        )

    return _f10_partial(
        state,
        {
            "confirmation": serialize_confirmation(
                status=ConfirmationStatus.CONFIRMED,
                intent=intent,
            ),
            "confirmed_business_id": confirmed,
            "failure": None,
        },
        trace="finalize_confirmation",
    )


def _compose_terminal_response_node(state: AgentState) -> dict[str, Any]:
    validate_agent_state(state)
    f10 = read_f10(state["artifacts"])
    mode_raw = f10.get("mode")
    if mode_raw not in (
        TerminalConfirmationMode.PREPARE.value,
        TerminalConfirmationMode.RESOLVE.value,
    ):
        raise AgentStateValidationError("f10.mode is required")
    mode = TerminalConfirmationMode(mode_raw)
    validation = _read_f10_validation(state)
    confirmation = f10.get("confirmation")
    if not isinstance(confirmation, dict):
        raise AgentStateValidationError("f10.confirmation is required")
    status = ConfirmationStatus(confirmation["status"])
    intent_raw = confirmation.get("intent")
    intent = (
        ConfirmationIntent(intent_raw) if isinstance(intent_raw, str) else None
    )

    # PREPARE + READY must surface AWAITING even if confirmation was left blocked
    # only briefly; validate node already sets AWAITING for READY.
    if (
        mode == TerminalConfirmationMode.PREPARE
        and validation.status
        == TerminalValidationStatus.READY_FOR_CONFIRMATION
    ):
        status = ConfirmationStatus.AWAITING_CONFIRMATION
        intent = None

    response_text = compose_terminal_response_text(
        mode=mode,
        validation=validation,
        confirmation_status=status,
        confirmation_intent=intent,
    )

    failure_payload = f10.get("failure")
    if status in (
        ConfirmationStatus.REJECTED,
        ConfirmationStatus.UNCERTAIN,
        ConfirmationStatus.AWAITING_CONFIRMATION,
        ConfirmationStatus.CONFIRMED,
    ):
        failure_payload = None
    elif (
        status == ConfirmationStatus.BLOCKED
        and failure_payload is None
        and validation.status != TerminalValidationStatus.READY_FOR_CONFIRMATION
    ):
        failure = build_terminal_failure(
            validation.status,
            canonical_name=validation.canonical_name,
        )
        failure_payload = serialize_failure(failure)

    return _f10_partial(
        state,
        {
            "confirmation": serialize_confirmation(
                status=status,
                intent=intent,
            ),
            "failure": failure_payload,
            "response_text": response_text,
        },
        trace="compose_terminal_response",
    )
