"""F12 Production AgentTurnProcessor: thin turn orchestration over F06/F04/F09/F10."""

from __future__ import annotations

import copy
import logging
from dataclasses import replace
from enum import StrEnum
from typing import Any, Mapping

from gov_service_agent.agent.first_turn_extract import (
    FirstTurnSlotExtractor,
    LlmFirstTurnExtractor,
    deterministic_slot_candidates,
)
from gov_service_agent.agent.guide_route import (
    GuideQueryHandler,
    build_default_guide_handler,
)
from gov_service_agent.agent.interaction import (
    MappingValidationStatus,
    SlotInteractionContext,
    build_slot_interaction_context,
    deserialize_slot_context,
    empty_f09_namespace,
    merge_f09_artifacts,
    read_f09,
    serialize_slot_context,
    serialize_transition_result,
)
from gov_service_agent.agent.state import (
    AgentPhase,
    AgentState,
    WorkflowStatus,
    create_initial_state,
    validate_agent_state,
)
from gov_service_agent.agent.terminal import (
    ConfirmationStatus,
    build_terminal_candidate_context,
    deserialize_terminal_context,
    read_f10,
)
from gov_service_agent.agent.workflow import (
    SlotInteractionDependencies,
    TerminalConfirmationDependencies,
    prepare_terminal_confirmation,
    resolve_terminal_confirmation,
    run_slot_interaction_workflow,
)
from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.business_graph.models import DecisionGraph, NodeType
from gov_service_agent.business_graph.transition import (
    TransitionResult,
    TransitionStatus,
    advance_until_blocked,
)
from gov_service_agent.guide_knowledge.recognize import (
    Recognition,
    RecognitionKind,
    recognize_guide_utterance,
)
from gov_service_agent.guide_knowledge.render import render_matter_unclear
from gov_service_agent.llm.types import RemoteDataPolicyProfile
from gov_service_agent.matters.registry import MatterRegistry, MatterRegistryError
from gov_service_agent.retrieval.service import SemanticRetrievalService
from gov_service_agent.retrieval.types import RetrievalCandidate, RetrievalStatus
from gov_service_agent.session.models import AgentTurnResult, SessionTurnPublicStatus

_F12_ARTIFACT_KEY = "f12"

_MSG_NO_DIRECTION = (
    "暂时无法确定您要办理的业务方向，请补充说明后重试。"
)
_MSG_SAFE_HOLD = (
    "当前办理路径暂时无法继续，请换一种需求说明或开启新的会话。"
)
_MSG_GRAPH_BIND_FAILURE = (
    "当前会话的办理路径无法继续，请开启新的会话后重试。"
)

# First-turn pure guide consult topics (answer without entering qualification graph).
_INITIAL_GUIDE_TOPICS = frozenset(
    {
        "fees",
        "materials",
        "completion_time",
        "legal_basis",
        "consultation",
        "complaints",
        "handling_locations",
        "handling_time",
        "faq",
        "process",
        "channels",
        "special_notice",
        "on_site_requirement",
        "implementing_authority",
        "result",
        "flow_chart",
        "applicant_scope",
    }
)

_RESOLVABLE_CONFIRMATION = frozenset(
    {
        ConfirmationStatus.AWAITING_CONFIRMATION.value,
        ConfirmationStatus.UNCERTAIN.value,
        ConfirmationStatus.REJECTED.value,
        ConfirmationStatus.BLOCKED.value,
    }
)


class _TurnMode(StrEnum):
    ALREADY_CONFIRMED = "already_confirmed"
    TERMINAL_CONFIRMATION = "terminal_confirmation"
    SLOT_INTERACTION = "slot_interaction"
    SAFE_HOLD = "safe_hold"
    INITIAL_ROUTING = "initial_routing"


class GovernmentAgentTurnProcessor:
    """Production turn orchestrator satisfying AgentTurnProcessor Protocol."""

    def __init__(
        self,
        *,
        business_repository: JsonBusinessRepository,
        retrieval_service: SemanticRetrievalService,
        slot_dependencies: SlotInteractionDependencies,
        terminal_dependencies: TerminalConfirmationDependencies,
        decision_graph: DecisionGraph | None = None,
        matter_registry: MatterRegistry | None = None,
        guide_handler: GuideQueryHandler | None = None,
        load_default_guide: bool = True,
        first_turn_extractor: FirstTurnSlotExtractor | None = None,
    ) -> None:
        if decision_graph is None and matter_registry is None:
            raise TypeError("decision_graph or matter_registry is required")
        if business_repository is None:
            raise TypeError("business_repository is required")
        if retrieval_service is None:
            raise TypeError("retrieval_service is required")
        if slot_dependencies is None:
            raise TypeError("slot_dependencies is required")
        if terminal_dependencies is None:
            raise TypeError("terminal_dependencies is required")
        if matter_registry is not None:
            self._registry = matter_registry
            self._decision_graph = (
                decision_graph
                if decision_graph is not None
                else matter_registry.default_graph()
            )
        else:
            assert decision_graph is not None
            self._decision_graph = decision_graph
            self._registry = MatterRegistry.from_single_graph(decision_graph)
        self._business_repository = business_repository
        self._retrieval_service = retrieval_service
        self._slot_dependencies = slot_dependencies
        self._terminal_dependencies = terminal_dependencies
        if guide_handler is not None:
            self._guide_handler: GuideQueryHandler | None = guide_handler
        elif load_default_guide:
            self._guide_handler = build_default_guide_handler(
                self._decision_graph,
                business_repository,
                matter_registry=self._registry,
            )
        else:
            self._guide_handler = None
        if first_turn_extractor is not None:
            self._first_turn_extractor: FirstTurnSlotExtractor | None = (
                first_turn_extractor
            )
        else:
            self._first_turn_extractor = _extractor_from_mapper(
                slot_dependencies,
                self._decision_graph,
            )
        self._registered_business_ids = self._registry.registered_ids()

    def process_turn(
        self,
        *,
        session_id: str,
        request_id: str,
        input_text: str,
        restored_state: AgentState | None,
    ) -> AgentTurnResult:
        del session_id  # Session identity remains F11-owned; AgentState has no session field.
        if restored_state is None:
            working = create_initial_state(request_id, input_text)
        else:
            working = _copy_working_state(
                restored_state,
                request_id=request_id,
                input_text=input_text,
            )

        mode = _determine_turn_mode(working)
        try:
            if mode is not _TurnMode.INITIAL_ROUTING:
                self._resolve_bound_graph(working)
        except MatterRegistryError:
            return _awaiting_or_completed(
                working,
                response_text=_MSG_GRAPH_BIND_FAILURE,
                requires_user_input=True,
                public_status=SessionTurnPublicStatus.AWAITING_USER_INPUT,
            )
        intercept = (
            None
            if self._guide_handler is None
            else self._guide_handler.try_handle(working, mode=mode.value)
        )
        if intercept is not None:
            artifacts = copy.deepcopy(working["artifacts"])
            artifacts["f15"] = intercept.f15
            return _awaiting_or_completed(
                _replace_artifacts(working, artifacts),
                response_text=intercept.response_text,
                requires_user_input=intercept.requires_user_input,
                public_status=intercept.public_status,
            )
        if mode is _TurnMode.ALREADY_CONFIRMED:
            return self._handle_already_confirmed(working)
        if mode is _TurnMode.TERMINAL_CONFIRMATION:
            return self._handle_terminal_confirmation(working)
        if mode is _TurnMode.SLOT_INTERACTION:
            return self._handle_slot_interaction(working)
        if mode is _TurnMode.SAFE_HOLD:
            return self._handle_safe_hold(working)
        return self._handle_initial_routing(working)

    def _handle_already_confirmed(self, state: AgentState) -> AgentTurnResult:
        f10 = read_f10(state["artifacts"])
        response = f10.get("response_text")
        if not isinstance(response, str) or not response.strip():
            raise ValueError("confirmed state missing F10 response_text")
        return _awaiting_or_completed(
            state,
            response_text=response,
            requires_user_input=False,
            public_status=SessionTurnPublicStatus.COMPLETED,
        )

    def _handle_terminal_confirmation(self, state: AgentState) -> AgentTurnResult:
        context = _require_terminal_context(state)
        result = resolve_terminal_confirmation(
            state,
            context,
            self._terminal_dependencies,
        )
        return self._result_from_f10(result)

    def _handle_slot_interaction(self, state: AgentState) -> AgentTurnResult:
        slot_context = _resolve_slot_context(state)
        graph = self._resolve_bound_graph(state)
        business_id = _bound_business_id_from_state(state)
        seeded, conflict = _seed_deterministic_facts(
            state["input_text"],
            graph=graph,
            business_id=business_id,
            current_slots=slot_context.current_slots,
        )
        if conflict is not None:
            question = slot_context.question_text or "请再明确说明一下当前问题。"
            return _awaiting_or_completed(
                state,
                response_text=(
                    f"您刚才的说明与已记录信息不一致（{conflict}）。"
                    f"请确认后重新回答：\n{question}"
                ),
                requires_user_input=True,
                public_status=SessionTurnPublicStatus.AWAITING_USER_INPUT,
            )
        seeded_context = slot_context.model_copy(
            update={"current_slots": seeded},
            deep=True,
        )
        required = seeded_context.required_slot
        if (
            isinstance(required, str)
            and required in seeded
            and required not in slot_context.current_slots
        ):
            transition = advance_until_blocked(
                graph,
                seeded_context.current_node_id,
                seeded,
            )
            projected = _project_seeded_slot_advance(
                state,
                transition=transition,
                current_slots=seeded,
                slot_context=seeded_context,
            )
            return self._result_from_f09(projected)

        deps = replace(self._slot_dependencies, decision_graph=graph)
        result = run_slot_interaction_workflow(
            state,
            seeded_context,
            deps,
        )
        return self._result_from_f09(result)

    def _handle_safe_hold(self, state: AgentState) -> AgentTurnResult:
        transition = _latest_safe_hold_transition(state)
        if transition is None:
            raise ValueError("SAFE_HOLD mode without FALLBACK/UNSUPPORTED transition")
        if (
            transition.status is TransitionStatus.UNSUPPORTED
            and isinstance(transition.unsupported_reason, str)
            and transition.unsupported_reason.strip()
        ):
            text = transition.unsupported_reason
            # Offline / ineligible branch is finished for online flow — do not
            # keep the frontend "等待您补充信息" awaiting hint.
            return _awaiting_or_completed(
                state,
                response_text=text,
                requires_user_input=False,
                public_status=SessionTurnPublicStatus.COMPLETED,
            )
        return _awaiting_or_completed(
            state,
            response_text=_MSG_SAFE_HOLD,
            requires_user_input=True,
            public_status=SessionTurnPublicStatus.AWAITING_USER_INPUT,
        )

    def _handle_initial_routing(self, state: AgentState) -> AgentTurnResult:
        retrieval = self._retrieval_service.retrieve(state["input_text"])
        if retrieval.status in (
            RetrievalStatus.UNAVAILABLE,
            RetrievalStatus.NOT_READY,
        ):
            raise RuntimeError(
                f"required semantic retrieval failed: {retrieval.status.value}"
            )
        if retrieval.status in (
            RetrievalStatus.NO_USABLE_CANDIDATE,
            RetrievalStatus.INVALID_QUERY,
        ):
            return _awaiting_or_completed(
                state,
                response_text=_MSG_NO_DIRECTION,
                requires_user_input=True,
                public_status=SessionTurnPublicStatus.AWAITING_USER_INPUT,
            )
        if retrieval.status is not RetrievalStatus.CANDIDATES:
            raise RuntimeError(
                f"unsupported retrieval status: {retrieval.status.value}"
            )

        matched_candidates = [
            candidate
            for candidate in retrieval.candidates
            if candidate.business_id in self._registered_business_ids
        ]
        unique_ids = list(
            dict.fromkeys(candidate.business_id for candidate in matched_candidates)
        )
        if not unique_ids:
            return _awaiting_or_completed(
                state,
                response_text=_MSG_NO_DIRECTION,
                requires_user_input=True,
                public_status=SessionTurnPublicStatus.AWAITING_USER_INPUT,
            )
        if len(unique_ids) > 1:
            ambiguous = _replace_artifacts(
                state,
                {
                    **copy.deepcopy(state["artifacts"]),
                    _F12_ARTIFACT_KEY: {
                        "knowledge_context_unique": False,
                        "knowledge_context_business_id": None,
                        "matched_business_ids": unique_ids,
                    },
                },
            )
            return _awaiting_or_completed(
                ambiguous,
                response_text=render_matter_unclear(),
                requires_user_input=True,
                public_status=SessionTurnPublicStatus.AWAITING_USER_INPUT,
            )

        matched = next(
            candidate
            for candidate in matched_candidates
            if candidate.business_id == unique_ids[0]
        )
        try:
            graph = self._registry.require_graph(matched.business_id)
        except MatterRegistryError:
            return _awaiting_or_completed(
                state,
                response_text=_MSG_NO_DIRECTION,
                requires_user_input=True,
                public_status=SessionTurnPublicStatus.AWAITING_USER_INPUT,
            )

        proposed = self._propose_first_turn_slots(
            state["input_text"],
            graph=graph,
            business_id=matched.business_id,
        )
        recognition = recognize_guide_utterance(
            state["input_text"],
            pending_question_text=None,
            active_business_id=matched.business_id,
        )
        consult = self._try_initial_guide_consult(
            state,
            matched=matched,
            recognition=recognition,
            proposed=proposed,
        )
        if consult is not None:
            return consult

        # Clause (二)/(三): any explicit offline-exception fact satisfies OR.
        # Do not invent answers for unasked sibling facts; short-circuit to guidance.
        if _offline_exception_triggered(proposed) and proposed.get("handling_case") in (
            "lost_reissue",
            "damaged_replace",
        ):
            transition = _offline_guidance_transition(graph)
            consumed = {
                key: value
                for key, value in proposed.items()
                if key == "handling_case"
                or (
                    key
                    in {
                        "submitted_photo_not_self",
                        "appearance_change_major",
                        "bad_credit_record",
                    }
                    and value == "yes"
                )
            }
        else:
            transition = advance_until_blocked(
                graph,
                graph.entry_node_id,
                proposed,
            )
            consumed = _consumed_slots(graph, transition, proposed)
        logging.getLogger("gov_service_agent").info(
            "message=first_turn_slots_consumed proposed=%s consumed=%s",
            ",".join(sorted(proposed)),
            ",".join(sorted(consumed)),
        )
        projected = _project_initial_transition(
            state,
            transition,
            direction_meta=_direction_artifact(
                matched,
                graph=graph,
                knowledge_unique=True,
            ),
            current_slots=consumed,
        )
        if transition.status is TransitionStatus.TERMINAL_CANDIDATE:
            return self._prepare_terminal(projected, transition)
        if transition.status in (
            TransitionStatus.NEED_SLOT,
            TransitionStatus.INVALID_SLOT,
        ):
            question = transition.question_text
            if not isinstance(question, str) or not question.strip():
                raise ValueError("initial NEED_SLOT missing question_text")
            return _awaiting_or_completed(
                projected,
                response_text=_with_opening(consumed, question),
                requires_user_input=True,
                public_status=SessionTurnPublicStatus.AWAITING_USER_INPUT,
            )
        if transition.status in (
            TransitionStatus.FALLBACK,
            TransitionStatus.UNSUPPORTED,
        ):
            return self._handle_safe_hold(projected)
        raise ValueError(
            f"unsupported initial transition status: {transition.status.value}"
        )

    def _resolve_bound_graph(self, state: AgentState) -> DecisionGraph:
        bound = _bound_business_id_from_state(state)
        if bound is None:
            # Legacy checkpoints without bound_*: fall back to default graph.
            return self._decision_graph
        expected = _bound_graph_id_from_state(state)
        return self._registry.require_graph_consistent(
            bound,
            expected_graph_id=expected,
        )

    def _try_initial_guide_consult(
        self,
        state: AgentState,
        *,
        matched: RetrievalCandidate,
        recognition: Recognition,
        proposed: Mapping[str, str],
    ) -> AgentTurnResult | None:
        """Prefer sourced guide answers for first-turn consults; never confirm."""
        if self._guide_handler is None:
            return None
        if recognition.kind is not RecognitionKind.TOPIC or recognition.topic is None:
            return None
        if recognition.topic not in _INITIAL_GUIDE_TOPICS:
            return None
        # Explicit offline-exception facts belong to handling routing, not Q&A.
        if proposed.get("submitted_photo_not_self") == "yes":
            return None
        if proposed.get("appearance_change_major") == "yes":
            return None
        if proposed.get("bad_credit_record") == "yes":
            return None
        intercept = self._guide_handler.consult_with_business(
            state,
            business_id=matched.business_id,
            topic=recognition.topic,
            subtopic=recognition.subtopic,
            lookups=recognition.lookups,
        )
        artifacts = copy.deepcopy(state["artifacts"])
        artifacts[_F12_ARTIFACT_KEY] = {
            "matched_business_id": matched.business_id,
            "rank": matched.rank,
            "direction": matched.direction,
            "eligibility_scope": matched.eligibility_scope,
            "knowledge_context_unique": True,
            "knowledge_context_business_id": matched.business_id,
            # Consult-only: do not bind the decision graph or confirm the matter.
            "bound_business_id": None,
            "bound_graph_id": None,
        }
        artifacts["f15"] = intercept.f15
        return _awaiting_or_completed(
            _replace_artifacts(state, artifacts),
            response_text=intercept.response_text,
            requires_user_input=True,
            public_status=SessionTurnPublicStatus.AWAITING_USER_INPUT,
        )

    def _propose_first_turn_slots(
        self,
        user_text: str,
        *,
        graph: DecisionGraph,
        business_id: str,
    ) -> dict[str, str]:
        if self._first_turn_extractor is None:
            return {}
        try:
            proposed = self._first_turn_extractor.accepted_slots(
                user_text,
                decision_graph=graph,
                business_id=business_id,
            )
        except TypeError:
            try:
                proposed = self._first_turn_extractor.accepted_slots(user_text)
            except Exception:
                logging.getLogger("gov_service_agent").info(
                    "message=first_turn_slots_skipped reason=unexpected_error"
                )
                return {}
        except Exception:
            logging.getLogger("gov_service_agent").info(
                "message=first_turn_slots_skipped reason=unexpected_error"
            )
            return {}
        if not isinstance(proposed, dict):
            return {}
        clean: dict[str, str] = {}
        for key, value in proposed.items():
            if isinstance(key, str) and isinstance(value, str) and value.strip():
                clean[key] = value
        return clean

    def _result_from_f09(self, state: AgentState) -> AgentTurnResult:
        f09 = read_f09(state["artifacts"])
        transition_payload = f09.get("business_transition")
        if isinstance(transition_payload, Mapping):
            transition = TransitionResult.model_validate(transition_payload)
            if transition.status is TransitionStatus.TERMINAL_CANDIDATE:
                projected = _project_pending_slot_after_f09(state)
                return self._prepare_terminal(projected, transition)
            if transition.status in (
                TransitionStatus.NEED_SLOT,
                TransitionStatus.INVALID_SLOT,
            ):
                projected = _project_pending_slot_after_f09(state)
                response = read_f09(projected["artifacts"]).get("response_text")
                if not isinstance(response, str) or not response.strip():
                    response = transition.question_text
                if not isinstance(response, str) or not response.strip():
                    raise ValueError("pending slot turn missing response_text")
                return _awaiting_or_completed(
                    projected,
                    response_text=response,
                    requires_user_input=True,
                    public_status=SessionTurnPublicStatus.AWAITING_USER_INPUT,
                )
            if transition.status in (
                TransitionStatus.FALLBACK,
                TransitionStatus.UNSUPPORTED,
            ):
                return self._handle_safe_hold(state)

        response = f09.get("response_text")
        if not isinstance(response, str) or not response.strip():
            raise ValueError("F09 turn missing response_text")
        return _awaiting_or_completed(
            state,
            response_text=response,
            requires_user_input=True,
            public_status=SessionTurnPublicStatus.AWAITING_USER_INPUT,
        )

    def _prepare_terminal(
        self,
        state: AgentState,
        transition: TransitionResult,
    ) -> AgentTurnResult:
        context = build_terminal_candidate_context(transition)
        prepared = prepare_terminal_confirmation(
            _rearm_same_turn_workflow(state),
            context,
            self._terminal_dependencies,
        )
        return self._result_from_f10(prepared)

    def _result_from_f10(self, state: AgentState) -> AgentTurnResult:
        f10 = read_f10(state["artifacts"])
        response = f10.get("response_text")
        if not isinstance(response, str) or not response.strip():
            raise ValueError("F10 turn missing response_text")
        confirmed = f10.get("confirmed_business_id")
        if isinstance(confirmed, str) and confirmed.strip():
            return _awaiting_or_completed(
                state,
                response_text=response,
                requires_user_input=False,
                public_status=SessionTurnPublicStatus.COMPLETED,
            )
        return _awaiting_or_completed(
            state,
            response_text=response,
            requires_user_input=True,
            public_status=SessionTurnPublicStatus.AWAITING_USER_INPUT,
        )


def _copy_working_state(
    restored_state: AgentState,
    *,
    request_id: str,
    input_text: str,
) -> AgentState:
    """Start this turn at the same lifecycle as create_initial_state.

    A persisted success is COMPLETED/COMPLETED. F09/F10 prepare only moves
    phase to ORCHESTRATING and leaves status unchanged, so copying that
    success forward becomes ORCHESTRATING/COMPLETED. Business artifacts stay;
    the caller-owned restored_state is not written.
    """
    return create_initial_state(
        request_id,
        input_text,
        artifacts=restored_state["artifacts"],
    )


def _rearm_same_turn_workflow(state: AgentState) -> AgentState:
    """Open the next sub-workflow inside this same user turn.

    F09 completion is COMPLETED/COMPLETED. F10 prepare only changes phase,
    so that completion is not a legal F10 entry. Trace belongs to one
    compiled workflow: nodes append with operator.add, and F11 does not
    persist the list. request_id and input_text stay on this request.
    """
    return create_initial_state(
        state["request_id"],
        state["input_text"],
        artifacts=state["artifacts"],
    )


def _determine_turn_mode(state: AgentState) -> _TurnMode:
    f10 = read_f10(state["artifacts"])
    confirmed = f10.get("confirmed_business_id")
    if isinstance(confirmed, str) and confirmed.strip():
        return _TurnMode.ALREADY_CONFIRMED

    # Terminal confirmation outranks stale F09 slot_context left after PREPARE.
    if _has_unconfirmed_terminal_context(f10):
        confirmation = f10.get("confirmation")
        if isinstance(confirmation, Mapping):
            status = confirmation.get("status")
            if status in _RESOLVABLE_CONFIRMATION:
                return _TurnMode.TERMINAL_CONFIRMATION
        raise ValueError("terminal confirmation checkpoint shape is invalid")

    if _has_pending_slot(state):
        return _TurnMode.SLOT_INTERACTION

    if _latest_safe_hold_transition(state) is not None:
        return _TurnMode.SAFE_HOLD

    if not _has_graph_context(state):
        return _TurnMode.INITIAL_ROUTING

    raise ValueError("unrecognized agent checkpoint shape for turn mode")


def _has_unconfirmed_terminal_context(f10: Mapping[str, Any]) -> bool:
    confirmed = f10.get("confirmed_business_id")
    if isinstance(confirmed, str) and confirmed.strip():
        return False
    payload = f10.get("terminal_context")
    if not isinstance(payload, Mapping):
        return False
    context = deserialize_terminal_context(payload)
    return context.transition_status is TransitionStatus.TERMINAL_CANDIDATE


def _require_terminal_context(state: AgentState):
    f10 = read_f10(state["artifacts"])
    payload = f10.get("terminal_context")
    if not isinstance(payload, Mapping):
        raise ValueError("terminal confirmation missing terminal_context")
    return deserialize_terminal_context(payload)


def _has_pending_slot(state: AgentState) -> bool:
    """Pending slot follows the latest transition, not a stale slot_context."""
    f09 = read_f09(state["artifacts"])
    transition_payload = f09.get("business_transition")
    if isinstance(transition_payload, Mapping):
        status = transition_payload.get("status")
        if status in (
            TransitionStatus.NEED_SLOT.value,
            TransitionStatus.INVALID_SLOT.value,
        ):
            TransitionResult.model_validate(transition_payload)
            return True
        if status in (
            TransitionStatus.FALLBACK.value,
            TransitionStatus.UNSUPPORTED.value,
            TransitionStatus.TERMINAL_CANDIDATE.value,
        ):
            return False
    slot_payload = f09.get("slot_context")
    if isinstance(slot_payload, Mapping):
        context = deserialize_slot_context(slot_payload)
        return context.transition_status in (
            TransitionStatus.NEED_SLOT,
            TransitionStatus.INVALID_SLOT,
        )
    return False


def _has_graph_context(state: AgentState) -> bool:
    f09 = read_f09(state["artifacts"])
    f10 = read_f10(state["artifacts"])
    if isinstance(f10.get("terminal_context"), Mapping):
        return True
    if isinstance(f09.get("business_transition"), Mapping):
        return True
    if isinstance(f09.get("slot_context"), Mapping):
        return True
    return False


def _latest_safe_hold_transition(state: AgentState) -> TransitionResult | None:
    f09 = read_f09(state["artifacts"])
    payload = f09.get("business_transition")
    if not isinstance(payload, Mapping):
        return None
    status = payload.get("status")
    if status not in (
        TransitionStatus.FALLBACK.value,
        TransitionStatus.UNSUPPORTED.value,
    ):
        return None
    return TransitionResult.model_validate(payload)


def _accumulated_slots(f09: Mapping[str, Any]) -> dict[str, str]:
    slots: dict[str, str] = {}
    slot_payload = f09.get("slot_context")
    if isinstance(slot_payload, Mapping):
        slots.update(deserialize_slot_context(slot_payload).current_slots)
    mapping = f09.get("mapping_validation")
    validated = f09.get("validated_slot")
    if (
        isinstance(mapping, Mapping)
        and mapping.get("status") == MappingValidationStatus.ACCEPTED.value
        and isinstance(validated, Mapping)
    ):
        name = validated.get("slot_name")
        value = validated.get("value")
        if isinstance(name, str) and name.strip() and isinstance(value, str):
            slots[name] = value
    return slots


def _resolve_slot_context(state: AgentState) -> SlotInteractionContext:
    f09 = read_f09(state["artifacts"])
    slots = _accumulated_slots(f09)
    transition_payload = f09.get("business_transition")
    if isinstance(transition_payload, Mapping) and transition_payload.get(
        "status"
    ) in (
        TransitionStatus.NEED_SLOT.value,
        TransitionStatus.INVALID_SLOT.value,
    ):
        transition = TransitionResult.model_validate(transition_payload)
        return build_slot_interaction_context(transition, current_slots=slots)

    slot_payload = f09.get("slot_context")
    if not isinstance(slot_payload, Mapping):
        raise ValueError("pending slot context is missing")
    context = deserialize_slot_context(slot_payload)
    return SlotInteractionContext(
        transition_status=context.transition_status,
        current_node_id=context.current_node_id,
        required_slot=context.required_slot,
        allowed_values=context.allowed_values,
        question_text=context.question_text,
        invalid_value=context.invalid_value,
        current_slots=slots if slots else dict(context.current_slots),
    )


def _project_pending_slot_after_f09(state: AgentState) -> AgentState:
    """Keep slot_context aligned with the latest NEED_SLOT transition for resume."""
    f09 = read_f09(state["artifacts"])
    transition_payload = f09.get("business_transition")
    if not isinstance(transition_payload, Mapping):
        return state
    if transition_payload.get("status") not in (
        TransitionStatus.NEED_SLOT.value,
        TransitionStatus.INVALID_SLOT.value,
        TransitionStatus.TERMINAL_CANDIDATE.value,
    ):
        return state
    slots = _accumulated_slots(f09)
    if transition_payload.get("status") == TransitionStatus.TERMINAL_CANDIDATE.value:
        # Preserve accumulated slots under existing slot_context for audit continuity.
        slot_payload = f09.get("slot_context")
        if not isinstance(slot_payload, Mapping):
            return state
        context = deserialize_slot_context(slot_payload)
        refreshed = SlotInteractionContext(
            transition_status=context.transition_status,
            current_node_id=context.current_node_id,
            required_slot=context.required_slot,
            allowed_values=context.allowed_values,
            question_text=context.question_text,
            invalid_value=context.invalid_value,
            current_slots=slots,
        )
        artifacts = merge_f09_artifacts(
            state["artifacts"],
            {"slot_context": serialize_slot_context(refreshed)},
        )
        return _replace_artifacts(state, artifacts)

    transition = TransitionResult.model_validate(transition_payload)
    refreshed = build_slot_interaction_context(transition, current_slots=slots)
    artifacts = merge_f09_artifacts(
        state["artifacts"],
        {"slot_context": serialize_slot_context(refreshed)},
    )
    return _replace_artifacts(state, artifacts)


def _project_initial_transition(
    state: AgentState,
    transition: TransitionResult,
    *,
    direction_meta: dict[str, Any],
    current_slots: Mapping[str, str] | None = None,
) -> AgentState:
    artifacts = copy.deepcopy(state["artifacts"])
    artifacts[_F12_ARTIFACT_KEY] = direction_meta
    owned_slots = dict(current_slots or {})
    if transition.status in (
        TransitionStatus.NEED_SLOT,
        TransitionStatus.INVALID_SLOT,
    ):
        slot_context = build_slot_interaction_context(
            transition,
            current_slots=owned_slots,
        )
        f09 = empty_f09_namespace(slot_context)
        f09["business_transition"] = serialize_transition_result(transition)
        f09["response_text"] = transition.question_text
        artifacts["f09"] = f09
    else:
        artifacts["f09"] = {
            "slot_context": None,
            "interpretation": None,
            "mapping_validation": None,
            "validated_slot": None,
            "explanation": None,
            "business_transition": serialize_transition_result(transition),
            "failure": None,
            "response_text": None,
        }
    return _replace_artifacts(state, artifacts)


def _extractor_from_mapper(
    slot_dependencies: SlotInteractionDependencies,
    decision_graph: DecisionGraph,
) -> FirstTurnSlotExtractor | None:
    mapper = slot_dependencies.answer_mapper
    provider = getattr(mapper, "_provider", None)
    if provider is None or not callable(getattr(provider, "complete", None)):
        return None
    profile = getattr(
        provider,
        "_remote_data_policy_profile",
        RemoteDataPolicyProfile.DEFAULT,
    )
    if not isinstance(profile, RemoteDataPolicyProfile):
        profile = RemoteDataPolicyProfile.DEFAULT
    return LlmFirstTurnExtractor(
        provider,
        decision_graph,
        remote_data_policy_profile=profile,
    )


def _consumed_slots(
    graph: DecisionGraph,
    transition: TransitionResult,
    proposed: Mapping[str, str],
) -> dict[str, str]:
    """Slots the graph actually passed, excluding the node that is still blocked."""
    by_id = {node.node_id: node for node in graph.nodes}
    blocking: str | None = None
    if transition.status in (
        TransitionStatus.NEED_SLOT,
        TransitionStatus.INVALID_SLOT,
    ):
        blocking = transition.current_node_id
    consumed: dict[str, str] = {}
    for node_id in transition.visited_node_ids:
        if node_id == blocking:
            continue
        node = by_id.get(node_id)
        if node is None or node.node_type is not NodeType.SLOT_GATE:
            continue
        slot_name = node.slot_name
        if not isinstance(slot_name, str) or slot_name not in proposed:
            continue
        consumed[slot_name] = proposed[slot_name]
    return consumed


def _offline_exception_triggered(proposed: Mapping[str, str]) -> bool:
    return (
        proposed.get("submitted_photo_not_self") == "yes"
        or proposed.get("appearance_change_major") == "yes"
        or proposed.get("bad_credit_record") == "yes"
    )


def _seed_deterministic_facts(
    user_text: str,
    *,
    graph: DecisionGraph,
    business_id: str | None,
    current_slots: Mapping[str, str],
) -> tuple[dict[str, str], str | None]:
    """Merge multi-fact deterministic candidates; never silently overwrite.

    Returns (merged_slots, conflict_description_or_none).
    """
    proposed = deterministic_slot_candidates(
        user_text,
        graph,
        business_id=business_id,
    )
    merged = dict(current_slots)
    conflicts: list[str] = []
    for slot_name, value in proposed.items():
        existing = merged.get(slot_name)
        if existing is None:
            merged[slot_name] = value
            continue
        if existing != value:
            conflicts.append(f"{slot_name}: 已记录「{existing}」，本次「{value}」")
    if conflicts:
        return dict(current_slots), "；".join(conflicts)
    return merged, None


def _project_seeded_slot_advance(
    state: AgentState,
    *,
    transition: TransitionResult,
    current_slots: Mapping[str, str],
    slot_context: SlotInteractionContext,
) -> AgentState:
    """Project a deterministic multi-slot advance into F09 artifacts."""
    owned_slots = dict(current_slots)
    if transition.status in (
        TransitionStatus.NEED_SLOT,
        TransitionStatus.INVALID_SLOT,
    ):
        refreshed = build_slot_interaction_context(
            transition,
            current_slots=owned_slots,
        )
        f09 = empty_f09_namespace(refreshed)
        f09["business_transition"] = serialize_transition_result(transition)
        f09["response_text"] = transition.question_text
    elif transition.status is TransitionStatus.TERMINAL_CANDIDATE:
        preserved = SlotInteractionContext(
            transition_status=slot_context.transition_status,
            current_node_id=slot_context.current_node_id,
            required_slot=slot_context.required_slot,
            allowed_values=slot_context.allowed_values,
            question_text=slot_context.question_text,
            invalid_value=slot_context.invalid_value,
            current_slots=owned_slots,
        )
        f09 = empty_f09_namespace(preserved)
        f09["business_transition"] = serialize_transition_result(transition)
        f09["response_text"] = None
    else:
        # FALLBACK / UNSUPPORTED: keep accumulated slots for audit, no pending ask.
        preserved = SlotInteractionContext(
            transition_status=slot_context.transition_status,
            current_node_id=slot_context.current_node_id,
            required_slot=slot_context.required_slot,
            allowed_values=slot_context.allowed_values,
            question_text=slot_context.question_text,
            invalid_value=slot_context.invalid_value,
            current_slots=owned_slots,
        )
        f09 = empty_f09_namespace(preserved)
        f09["business_transition"] = serialize_transition_result(transition)
        f09["response_text"] = transition.unsupported_reason
    artifacts = merge_f09_artifacts(state["artifacts"], f09)
    return _replace_artifacts(state, artifacts)


def _offline_guidance_transition(graph: DecisionGraph) -> TransitionResult:
    node = next(
        (item for item in graph.nodes if item.node_id == "offline_window_guidance"),
        None,
    )
    if node is None or node.node_type is not NodeType.UNSUPPORTED:
        raise ValueError("idcard offline_window_guidance node missing")
    if not isinstance(node.unsupported_reason, str) or not node.unsupported_reason.strip():
        raise ValueError("offline_window_guidance missing unsupported_reason")
    return TransitionResult(
        status=TransitionStatus.UNSUPPORTED,
        current_node_id=node.node_id,
        unsupported_reason=node.unsupported_reason,
        visited_node_ids=[graph.entry_node_id, "handling_case", node.node_id],
        traversed_edge_ids=[
            "e-entry-handling",
            "e-offline-exception-short-circuit",
        ],
    )


def _with_opening(consumed: Mapping[str, str], question: str) -> str:
    if (
        consumed.get("service_action") == "payment"
        and consumed.get("payment_actor") == "self_payment"
    ):
        return f"明白了，您想自己缴纳社保。我再了解一下您的就业情况：\n{question}"
    if consumed.get("service_action") == "payment" and "payment_actor" not in consumed:
        return f"明白了，您想办理社保缴费。\n{question}"
    if consumed.get("handling_case") == "lost_reissue":
        return (
            "好的，您是居民身份证丢失需要补领。"
            f"我再确认一项是否适合网上办理：\n{question}"
        )
    if consumed.get("handling_case") == "damaged_replace":
        return (
            "好的，您是居民身份证损坏需要换领。"
            f"我再确认一项是否适合网上办理：\n{question}"
        )
    return question


def _direction_artifact(
    candidate: RetrievalCandidate,
    *,
    graph: DecisionGraph,
    knowledge_unique: bool,
) -> dict[str, Any]:
    return {
        "matched_business_id": candidate.business_id,
        "rank": candidate.rank,
        "direction": candidate.direction,
        "eligibility_scope": candidate.eligibility_scope,
        "knowledge_context_unique": knowledge_unique,
        "knowledge_context_business_id": (
            candidate.business_id if knowledge_unique else None
        ),
        "bound_business_id": candidate.business_id if knowledge_unique else None,
        "bound_graph_id": graph.graph_id if knowledge_unique else None,
    }


def _bound_business_id_from_state(state: AgentState) -> str | None:
    f12 = state["artifacts"].get(_F12_ARTIFACT_KEY)
    if not isinstance(f12, dict):
        return None
    bound = f12.get("bound_business_id")
    if isinstance(bound, str) and bound.strip():
        return bound.strip()
    matched = f12.get("matched_business_id")
    if (
        isinstance(matched, str)
        and matched.strip()
        and f12.get("knowledge_context_unique") is True
    ):
        return matched.strip()
    return None


def _bound_graph_id_from_state(state: AgentState) -> str | None:
    f12 = state["artifacts"].get(_F12_ARTIFACT_KEY)
    if not isinstance(f12, dict):
        return None
    graph_id = f12.get("bound_graph_id")
    if isinstance(graph_id, str) and graph_id.strip():
        return graph_id.strip()
    return None


def _replace_artifacts(state: AgentState, artifacts: dict[str, Any]) -> AgentState:
    owned: AgentState = {
        "request_id": state["request_id"],
        "input_text": state["input_text"],
        "phase": state["phase"],
        "status": state["status"],
        "artifacts": artifacts,
        "error": state["error"],
        "orchestration_trace": list(state["orchestration_trace"]),
    }
    return validate_agent_state(owned)


def _as_completed(state: AgentState) -> AgentState:
    owned: AgentState = {
        "request_id": state["request_id"],
        "input_text": state["input_text"],
        "phase": AgentPhase.COMPLETED,
        "status": WorkflowStatus.COMPLETED,
        "artifacts": copy.deepcopy(state["artifacts"]),
        "error": None,
        "orchestration_trace": list(state["orchestration_trace"]),
    }
    return validate_agent_state(owned)


def _awaiting_or_completed(
    state: AgentState,
    *,
    response_text: str,
    requires_user_input: bool,
    public_status: SessionTurnPublicStatus,
) -> AgentTurnResult:
    return AgentTurnResult(
        state=_as_completed(state),
        response_text=response_text,
        requires_user_input=requires_user_input,
        public_status=public_status,
    )
