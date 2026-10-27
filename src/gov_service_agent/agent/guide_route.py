"""GUIDE_QUERY side route. It does not advance the decision graph or confirm a matter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gov_service_agent.agent.interaction import read_f09
from gov_service_agent.agent.state import AgentState
from gov_service_agent.agent.terminal import (
    ConfirmationIntent,
    interpret_confirmation,
    read_f10,
)
from gov_service_agent.business_graph.models import DecisionGraph
from gov_service_agent.business_graph.transition import TransitionStatus
from gov_service_agent.guide_knowledge.models import load_guide_document
from gov_service_agent.guide_knowledge.recognize import (
    ClarificationOption,
    RecognitionKind,
    match_clarification_topic,
    recognize_guide_utterance,
)
from gov_service_agent.guide_knowledge.render import (
    GuideAnswerRenderer,
    TemplateGuideRenderer,
    append_resume,
    render_business_not_ready,
    render_clarification,
    render_matter_unclear,
    render_out_of_guide,
    render_smalltalk,
    render_uncertain_guide,
)
from gov_service_agent.guide_knowledge.service import (
    GovernmentKnowledgeService,
    KnowledgeQueryStatus,
)
from gov_service_agent.session.models import SessionTurnPublicStatus

_ACTIVE_MODES = frozenset(
    {"already_confirmed", "terminal_confirmation", "slot_interaction"}
)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_GUIDE = _REPO_ROOT / "data" / "guides" / "DEMO_SS_001.guide.json"


@dataclass(frozen=True)
class GuideIntercept:
    response_text: str
    requires_user_input: bool
    public_status: SessionTurnPublicStatus
    f15: dict[str, Any]


class GuideQueryHandler:
    def __init__(
        self,
        *,
        decision_graph: DecisionGraph,
        knowledge_service: GovernmentKnowledgeService,
        renderer: GuideAnswerRenderer | None = None,
    ) -> None:
        self._graph = decision_graph
        self._knowledge = knowledge_service
        self._renderer = renderer or TemplateGuideRenderer()

    def try_handle(self, state: AgentState, *, mode: str) -> GuideIntercept | None:
        if mode not in _ACTIVE_MODES:
            return None
        user_text = state["input_text"]
        pending = _read_pending(state)
        if pending is not None:
            return self._handle_pending(state, mode, user_text, pending)
        if mode == "terminal_confirmation" and _is_explicit_confirmation(user_text):
            return None
        recognition = recognize_guide_utterance(
            user_text,
            pending_question_text=_pending_question(state) if mode == "slot_interaction" else None,
        )
        if recognition.kind is RecognitionKind.FALL_THROUGH:
            return None
        if recognition.kind is RecognitionKind.AMBIGUOUS:
            return self._ask_clarification(state, mode, recognition.options)
        if recognition.kind is RecognitionKind.UNCERTAIN:
            return self._reply(
                state,
                mode,
                render_uncertain_guide(),
                pending=None,
                status="UNCERTAIN",
                include_resume=False,
            )
        if recognition.kind is RecognitionKind.SMALLTALK:
            return self._reply(
                state,
                mode,
                render_smalltalk(user_text),
                pending=None,
                status="SMALLTALK",
            )
        if recognition.kind is RecognitionKind.OUT_OF_GUIDE:
            return self._reply(state, mode, render_out_of_guide(), pending=None, status="OUT_OF_GUIDE")
        assert recognition.topic is not None
        return self._answer_topic(
            state,
            mode,
            recognition.topic,
            recognition.subtopic,
            recognition.lookups,
        )

    def _handle_pending(
        self,
        state: AgentState,
        mode: str,
        user_text: str,
        pending: dict[str, Any],
    ) -> GuideIntercept:
        options = _options_from_payload(pending["options"])
        topic = match_clarification_topic(user_text, options)
        if topic is None:
            recognition = recognize_guide_utterance(user_text, pending_question_text=None)
            if recognition.kind is RecognitionKind.TOPIC and recognition.topic is not None:
                return self._answer_topic(
                    state,
                    mode,
                    recognition.topic,
                    recognition.subtopic,
                )
            return self._reply(
                state,
                mode,
                render_clarification(tuple(option.label for option in options)),
                pending=pending,
                status="AMBIGUOUS",
                include_resume=False,
            )
        return self._answer_topic(state, mode, topic, None)

    def _ask_clarification(
        self,
        state: AgentState,
        mode: str,
        options: tuple[ClarificationOption, ...],
    ) -> GuideIntercept:
        pending = {
            "prompt": render_clarification(tuple(option.label for option in options)),
            "options": [
                {
                    "topic": option.topic,
                    "label": option.label,
                    "phrases": list(option.phrases),
                }
                for option in options
            ],
        }
        return self._reply(
            state,
            mode,
            str(pending["prompt"]),
            pending=pending,
            status="AMBIGUOUS",
            include_resume=False,
        )

    def _answer_topic(
        self,
        state: AgentState,
        mode: str,
        topic: str,
        subtopic: str | None,
        lookups: tuple[tuple[str, str | None], ...] = (),
    ) -> GuideIntercept:
        business_id, context_kind = _resolve_business_context(state, mode, self._graph)
        if business_id is None:
            message = (
                render_matter_unclear()
                if _knowledge_context_ambiguous(state)
                else render_business_not_ready()
            )
            return self._reply(
                state,
                mode,
                message,
                pending=None,
                status="NO_BUSINESS",
            )
        specs = lookups or ((topic, subtopic),)
        result = self._knowledge.query_many(business_id, specs)
        if result.status is KnowledgeQueryStatus.NOT_FOUND and subtopic is not None and not lookups:
            result = self._knowledge.query(business_id, topic, None)
        answer = self._renderer.render_facts(result)
        if context_kind == "knowledge":
            title = self._knowledge.source_title(business_id) or business_id
            answer = f"如果您咨询的是“{title}”事项：\n{answer}"
        return self._reply(
            state,
            mode,
            answer,
            pending=None,
            status=result.status.value,
        )

    def _reply(
        self,
        state: AgentState,
        mode: str,
        answer: str,
        *,
        pending: dict[str, Any] | None,
        status: str,
        include_resume: bool = True,
    ) -> GuideIntercept:
        resume, requires_user_input, public_status = _resume_contract(state, mode)
        shown = resume if include_resume else None
        return GuideIntercept(
            response_text=append_resume(answer, shown),
            requires_user_input=requires_user_input,
            public_status=public_status,
            f15={
                "pending_clarification": pending,
                "last_status": status,
            },
        )


def build_default_guide_handler(
    decision_graph: DecisionGraph,
    business_repository: Any,
) -> GuideQueryHandler | None:
    if not _DEFAULT_GUIDE.is_file():
        return None
    document = load_guide_document(_DEFAULT_GUIDE)
    service = GovernmentKnowledgeService(
        {document.business_id: document},
        business_repository=business_repository,
    )
    return GuideQueryHandler(
        decision_graph=decision_graph,
        knowledge_service=service,
    )


def _is_explicit_confirmation(user_text: str) -> bool:
    intent = interpret_confirmation(user_text)
    return intent in (ConfirmationIntent.CONFIRMED, ConfirmationIntent.REJECTED)


def _read_pending(state: AgentState) -> dict[str, Any] | None:
    f15 = state["artifacts"].get("f15")
    if not isinstance(f15, dict):
        return None
    pending = f15.get("pending_clarification")
    if not isinstance(pending, dict):
        return None
    options = pending.get("options")
    if not isinstance(options, list) or not options:
        return None
    return pending


def _options_from_payload(payload: object) -> tuple[ClarificationOption, ...]:
    if not isinstance(payload, list):
        return ()
    options: list[ClarificationOption] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        topic = item.get("topic")
        label = item.get("label")
        phrases = item.get("phrases")
        if not isinstance(topic, str) or not isinstance(label, str):
            continue
        if not isinstance(phrases, list):
            continue
        text_phrases = tuple(phrase for phrase in phrases if isinstance(phrase, str))
        options.append(ClarificationOption(topic, label, text_phrases))
    return tuple(options)


def _pending_question(state: AgentState) -> str | None:
    f09 = read_f09(state["artifacts"])
    transition = f09.get("business_transition")
    if isinstance(transition, dict) and transition.get("status") in (
        TransitionStatus.NEED_SLOT.value,
        TransitionStatus.INVALID_SLOT.value,
    ):
        question = transition.get("question_text")
        if isinstance(question, str) and question.strip():
            return question
    slot_payload = f09.get("slot_context")
    if isinstance(slot_payload, dict):
        question = slot_payload.get("question_text")
        if isinstance(question, str) and question.strip():
            return question
    return None


def _resume_contract(
    state: AgentState,
    mode: str,
) -> tuple[str | None, bool, SessionTurnPublicStatus]:
    if mode == "already_confirmed":
        return None, False, SessionTurnPublicStatus.COMPLETED
    if mode == "terminal_confirmation":
        response = read_f10(state["artifacts"]).get("response_text")
        if not isinstance(response, str) or not response.strip():
            response = "请明确回复“确认”或“不确认”。"
        return response, True, SessionTurnPublicStatus.AWAITING_USER_INPUT
    question = _pending_question(state)
    return question, True, SessionTurnPublicStatus.AWAITING_USER_INPUT


def _resolve_business_context(
    state: AgentState,
    mode: str,
    graph: DecisionGraph,
) -> tuple[str | None, str]:
    """Return a guide business id and whether it is confirmed, candidate, or knowledge context."""
    f10 = read_f10(state["artifacts"])
    confirmed = f10.get("confirmed_business_id")
    if isinstance(confirmed, str) and confirmed.strip():
        return confirmed.strip(), "confirmed"
    if mode == "terminal_confirmation":
        payload = f10.get("terminal_context")
        if isinstance(payload, dict):
            candidate = payload.get("candidate_business_id")
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip(), "candidate"
    node_business = _business_id_from_node(state, graph)
    if node_business is not None:
        return node_business, "candidate"
    knowledge = _knowledge_context_id(state)
    if knowledge is not None:
        return knowledge, "knowledge"
    return None, "none"


def _business_id_from_node(state: AgentState, graph: DecisionGraph) -> str | None:
    node_id = _current_node_id(state)
    if node_id is None:
        return None
    for node in graph.nodes:
        if node.node_id != node_id:
            continue
        refs = node.source_condition_refs or []
        business_ids = {ref.business_id for ref in refs if ref.business_id.strip()}
        if len(business_ids) == 1:
            return next(iter(business_ids))
        return None
    return None


def _knowledge_context_id(state: AgentState) -> str | None:
    f12 = state["artifacts"].get("f12")
    if not isinstance(f12, dict) or f12.get("knowledge_context_unique") is not True:
        return None
    business_id = f12.get("knowledge_context_business_id")
    if isinstance(business_id, str) and business_id.strip():
        return business_id.strip()
    return None


def _knowledge_context_ambiguous(state: AgentState) -> bool:
    f12 = state["artifacts"].get("f12")
    return isinstance(f12, dict) and f12.get("knowledge_context_unique") is False


def _current_node_id(state: AgentState) -> str | None:
    f09 = read_f09(state["artifacts"])
    transition = f09.get("business_transition")
    if isinstance(transition, dict):
        node_id = transition.get("current_node_id")
        if isinstance(node_id, str) and node_id.strip():
            return node_id
    slot_payload = f09.get("slot_context")
    if isinstance(slot_payload, dict):
        node_id = slot_payload.get("current_node_id")
        if isinstance(node_id, str) and node_id.strip():
            return node_id
    return None
