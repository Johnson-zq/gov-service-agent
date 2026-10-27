"""F15 guide knowledge, side route, and state invariants. No live LLM or Redis."""

from __future__ import annotations

import copy
import uuid
from pathlib import Path

import pytest

from gov_service_agent.agent.explanation import (
    ExplanationRequest,
    ExplanationResult,
    ExplanationStatus,
)
from gov_service_agent.agent.interaction import (
    AnswerMapperOutput,
    AnswerMappingRequest,
    MapperUtteranceKind,
)
from gov_service_agent.agent.materials_preview import (
    ConfirmedBusinessMaterialsPreviewProcessor,
)
from gov_service_agent.agent.state import AgentState
from gov_service_agent.agent.terminal import read_f10
from gov_service_agent.agent.turn_processor import GovernmentAgentTurnProcessor
from gov_service_agent.agent.workflow import (
    SlotInteractionDependencies,
    TerminalConfirmationDependencies,
)
from gov_service_agent.business_data.models import VerificationStatus
from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.business_graph.loader import load_decision_graph
from gov_service_agent.guide_knowledge.models import guide_document_from_dict, load_guide_document
from gov_service_agent.guide_knowledge.render import FactConstrainedLlmRenderer, TemplateGuideRenderer
from gov_service_agent.guide_knowledge.service import (
    GovernmentKnowledgeService,
    KnowledgeQueryStatus,
)
from gov_service_agent.llm.types import LlmResponse
from gov_service_agent.retrieval.types import RetrievalCandidate, RetrievalResult, RetrievalStatus
from gov_service_agent.session.models import SessionTurnPublicStatus, SessionTurnSuccess

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GRAPH_PATH = _REPO_ROOT / "data" / "graphs" / "demo" / "social_security.json"
_BUSINESS_PATH = _REPO_ROOT / "data" / "demo" / "demo_ss_001.json"
_GUIDE_PATH = _REPO_ROOT / "data" / "guides" / "DEMO_SS_001.guide.json"
_INITIAL = "我辞职了，现在没单位，想自己交社保"
_EMPLOYMENT_QUESTION = (
    "您属于哪种灵活就业情况？例如个体户、未在单位参保的非全日制人员，或其他灵活就业人员。"
)


class FakeRetrieval:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def retrieve(self, query: str) -> RetrievalResult:
        self.queries.append(query)
        return RetrievalResult(
            status=RetrievalStatus.CANDIDATES,
            query=query,
            candidates=[
                RetrievalCandidate(
                    business_id="DEMO_SS_001",
                    display_name="demo",
                    score=0.91,
                    rank=1,
                    direction="social_security",
                    eligibility_scope="ONLINE",
                )
            ],
        )


class ScriptedMapper:
    def __init__(self, outputs: list[AnswerMapperOutput]) -> None:
        self._outputs = list(outputs)
        self.requests: list[AnswerMappingRequest] = []

    def map_answer(self, request: AnswerMappingRequest) -> AnswerMapperOutput:
        self.requests.append(request)
        if not self._outputs:
            raise AssertionError("mapper called unexpectedly")
        return self._outputs.pop(0)


class ScriptedExplanation:
    def __init__(self) -> None:
        self.calls = 0

    def explain(self, request: ExplanationRequest) -> ExplanationResult:
        del request
        self.calls += 1
        return ExplanationResult(
            status=ExplanationStatus.ANSWERED,
            topic="灵活就业",
            text="灵活就业是一种就业形式的说明",
        )


class FakeLlm:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    @property
    def provider_name(self) -> str:
        return "FAKE"

    @property
    def model_id(self) -> str | None:
        return "fake"

    def complete(self, request: object) -> LlmResponse:
        del request
        self.calls += 1
        return LlmResponse(content=self.content, provider_name="FAKE", model_id="fake")


def _slot(value: str) -> AnswerMapperOutput:
    return AnswerMapperOutput(
        kind=MapperUtteranceKind.SLOT_ANSWER,
        mapped_value=value,
        confidence=0.95,
    )


def _build(
    mapper: ScriptedMapper | None = None,
    explanation: ScriptedExplanation | None = None,
) -> tuple[GovernmentAgentTurnProcessor, FakeRetrieval, ScriptedMapper]:
    graph = load_decision_graph(_GRAPH_PATH)
    repository = JsonBusinessRepository.from_paths([_BUSINESS_PATH])
    retrieval = FakeRetrieval()
    scripted = mapper or ScriptedMapper([])
    processor = GovernmentAgentTurnProcessor(
        decision_graph=graph,
        business_repository=repository,
        retrieval_service=retrieval,  # type: ignore[arg-type]
        slot_dependencies=SlotInteractionDependencies(
            answer_mapper=scripted,
            explanation_service=explanation or ScriptedExplanation(),
            decision_graph=graph,
            business_repository=repository,
        ),
        terminal_dependencies=TerminalConfirmationDependencies(
            business_repository=repository,
        ),
    )
    return processor, retrieval, scripted


def _turn(processor: GovernmentAgentTurnProcessor, text: str, restored: AgentState | None):
    return processor.process_turn(
        session_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        input_text=text,
        restored_state=restored,
    )


def _business_snapshot(state: AgentState) -> dict[str, object]:
    f09 = state["artifacts"].get("f09")
    f10 = read_f10(state["artifacts"])
    transition = f09.get("business_transition") if isinstance(f09, dict) else None
    slot = f09.get("slot_context") if isinstance(f09, dict) else None
    validated = f09.get("validated_slot") if isinstance(f09, dict) else None
    return {
        "current_node_id": transition.get("current_node_id") if isinstance(transition, dict) else None,
        "validated_slot": copy.deepcopy(validated),
        "current_slots": copy.deepcopy(slot.get("current_slots")) if isinstance(slot, dict) else None,
        "candidate_business_id": (
            transition.get("candidate_business_id") if isinstance(transition, dict) else None
        ),
        "confirmed_business_id": f10.get("confirmed_business_id"),
    }


def _reach_employment(processor: GovernmentAgentTurnProcessor) -> AgentState:
    state = None
    for text, value in (
        (_INITIAL, None),
        ("缴费", "payment"),
        ("自己缴", "self_payment"),
    ):
        result = _turn(processor, text, state)
        state = result.state
        if value is not None:
            assert result.response_text
    assert state is not None
    assert _business_snapshot(state)["current_node_id"] == "employment_type"
    return state


def test_guide_document_loads_and_answers_core_topics() -> None:
    document = load_guide_document(_GUIDE_PATH)
    repository = JsonBusinessRepository.from_paths([_BUSINESS_PATH])
    service = GovernmentKnowledgeService(
        {document.business_id: document},
        business_repository=repository,
    )
    materials = service.query("DEMO_SS_001", "materials")
    assert materials.status is KnowledgeQueryStatus.FOUND
    assert materials.facts[0].text == "申请材料：身份证。"
    assert "九、申请材料" in materials.facts[0].source_section
    deadline = service.query("DEMO_SS_001", "completion_time")
    assert "即办" in deadline.facts[0].text
    assert "补正" in deadline.facts[0].text
    location = service.query("DEMO_SS_001", "handling_locations")
    assert "建国南路42号" in location.facts[0].text
    hours = service.query("DEMO_SS_001", "handling_time")
    assert "8:30-12:00" in hours.facts[0].text
    legal = service.query("DEMO_SS_001", "legal_basis")
    assert "第六十条" in legal.facts[0].text
    consult = service.query("DEMO_SS_001", "consultation")
    assert "0571-86438110" in consult.facts[0].text
    channels = service.query("DEMO_SS_001", "channels")
    assert "支付宝" in channels.facts[0].text
    fees = service.query("DEMO_SS_001", "fees")
    assert "未记载" in fees.facts[0].text
    assert "免费" not in fees.facts[0].text
    onsite = service.query("DEMO_SS_001", "on_site_requirement")
    assert "0次" in onsite.facts[0].text
    complaints = service.query("DEMO_SS_001", "complaints")
    assert "0571-12345" in complaints.facts[0].text
    faqs = service.query("DEMO_SS_001", "faq")
    assert len(faqs.facts) == 2


def test_unverified_item_is_not_public() -> None:
    document = load_guide_document(_GUIDE_PATH)
    payload = document.model_dump(mode="json")
    payload["knowledge_items"] = [
        {
            "item_id": "ki-hidden",
            "topic": "custom_topic",
            "subtopic": None,
            "value": {"kind": "list", "items": ["只存在于未核验记录"]},
            "verification_status": VerificationStatus.TO_CONFIRM.value,
            "source_id": "src-demo-ss-001",
            "section_id": "sec-fees",
            "excerpt": None,
        }
    ]
    hidden = guide_document_from_dict(payload)
    service = GovernmentKnowledgeService({"DEMO_SS_001": hidden})
    result = service.query("DEMO_SS_001", "custom_topic")
    assert result.status is KnowledgeQueryStatus.NOT_VERIFIED
    assert result.facts == []
    missing = service.query("DEMO_SS_001", "not-a-topic")
    assert missing.status is KnowledgeQueryStatus.NOT_FOUND


def test_guide_question_before_business_is_known_does_not_invent_facts() -> None:
    mapper = ScriptedMapper([])
    processor, _, mapper = _build(mapper)
    pending = _turn(processor, _INITIAL, None).state
    before = _business_snapshot(pending)
    result = _turn(processor, "要什么材料？", pending)
    assert "如果您咨询的是" in result.response_text
    assert "身份证" in result.response_text
    assert "您主要想办理社保缴费" in result.response_text
    assert len(mapper.requests) == 0
    assert _business_snapshot(result.state) == before


def test_side_route_answers_and_restores_employment_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    mapper = ScriptedMapper([_slot("payment"), _slot("self_payment")])
    processor, retrieval, mapper = _build(mapper)
    state = _reach_employment(processor)
    before = _business_snapshot(state)
    mapper_before = len(mapper.requests)
    calls = {"n": 0}
    import gov_service_agent.agent.nodes as nodes
    import gov_service_agent.agent.turn_processor as turn_module

    real_nodes = nodes.advance_until_blocked
    real_turn = turn_module.advance_until_blocked

    def _spy(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return real_nodes(*args, **kwargs)

    monkeypatch.setattr(nodes, "advance_until_blocked", _spy)
    monkeypatch.setattr(turn_module, "advance_until_blocked", _spy)
    del real_turn
    result = _turn(processor, "这个需要什么材料？", state)
    assert calls["n"] == 0
    assert len(mapper.requests) == mapper_before
    assert len(retrieval.queries) == 1
    assert "身份证" in result.response_text
    assert _EMPLOYMENT_QUESTION in result.response_text
    assert result.requires_user_input is True
    assert _business_snapshot(result.state) == before
    SessionTurnSuccess(
        session_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        status=result.public_status,
        response_text=result.response_text,
        requires_user_input=result.requires_user_input,
    )


def test_topic_clarification_does_not_fill_employment_slot() -> None:
    mapper = ScriptedMapper([_slot("payment"), _slot("self_payment")])
    processor, _, mapper = _build(mapper)
    state = _reach_employment(processor)
    before = _business_snapshot(state)
    first = _turn(processor, "线下怎么办？", state)
    assert "去哪里办理" in first.response_text
    assert "窗口办理的具体流程" in first.response_text
    assert _EMPLOYMENT_QUESTION not in first.response_text
    assert _business_snapshot(first.state) == before
    mapper_before = len(mapper.requests)
    second = _turn(processor, "我想问去哪里。", first.state)
    assert len(mapper.requests) == mapper_before
    assert "建国南路42号" in second.response_text
    assert _EMPLOYMENT_QUESTION in second.response_text
    assert _business_snapshot(second.state) == before
    assert second.state["artifacts"]["f15"]["pending_clarification"] is None


def test_two_guide_questions_and_out_of_guide_keep_state() -> None:
    mapper = ScriptedMapper([_slot("payment"), _slot("self_payment")])
    processor, _, mapper = _build(mapper)
    state = _reach_employment(processor)
    before = _business_snapshot(state)
    mapper_before = len(mapper.requests)
    hours = _turn(processor, "几点上班？", state)
    legal = _turn(processor, "法律依据是什么？", hours.state)
    other = _turn(processor, "外省的医保报销比例是多少？", legal.state)
    assert "8:30-12:00" in hours.response_text
    assert "第六十条" in legal.response_text
    assert "不能编造" in other.response_text
    assert _EMPLOYMENT_QUESTION in other.response_text
    assert len(mapper.requests) == mapper_before
    assert _business_snapshot(other.state) == before


def test_confirmation_question_does_not_confirm() -> None:
    mapper = ScriptedMapper(
        [_slot("payment"), _slot("self_payment"), _slot("self_employed_without_employees")]
    )
    processor, _, mapper = _build(mapper)
    state: AgentState | None = None
    for text in (_INITIAL, "缴费", "自己缴", "无雇工的个体工商户"):
        state = _turn(processor, text, state).state
    assert state is not None
    assert read_f10(state["artifacts"]).get("confirmed_business_id") in (None, "")
    before = _business_snapshot(state)
    asked = _turn(processor, "身份证需要什么材料？", state)
    assert "身份证" in asked.response_text
    assert "请确认是否办理" in asked.response_text
    assert read_f10(asked.state["artifacts"]).get("confirmed_business_id") in (None, "")
    assert _business_snapshot(asked.state)["confirmed_business_id"] == before["confirmed_business_id"]
    mapper_before = len(mapper.requests)
    confirmed = _turn(processor, "确认", asked.state)
    assert len(mapper.requests) == mapper_before
    assert read_f10(confirmed.state["artifacts"])["confirmed_business_id"] == "DEMO_SS_001"


def test_confirmed_guide_query_keeps_confirmation_and_skips_f13_repeat() -> None:
    mapper = ScriptedMapper(
        [_slot("payment"), _slot("self_payment"), _slot("self_employed_without_employees")]
    )
    processor, retrieval, mapper = _build(mapper)
    repository = JsonBusinessRepository.from_paths([_BUSINESS_PATH])
    preview = ConfirmedBusinessMaterialsPreviewProcessor(
        base_processor=processor,
        business_repository=repository,
    )
    state = None
    result = None
    for text in (_INITIAL, "缴费", "自己缴", "无雇工的个体工商户", "确认"):
        result = preview.process_turn(
            session_id=str(uuid.uuid4()),
            request_id=str(uuid.uuid4()),
            input_text=text,
            restored_state=state,
        )
        state = result.state
    assert result is not None
    assert "需要准备的材料：" in result.response_text
    later = preview.process_turn(
        session_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        input_text="咨询电话是多少？",
        restored_state=state,
    )
    assert "0571-86438110" in later.response_text
    assert "需要准备的材料：" not in later.response_text
    assert later.requires_user_input is False
    assert later.public_status is SessionTurnPublicStatus.COMPLETED
    assert read_f10(later.state["artifacts"])["confirmed_business_id"] == "DEMO_SS_001"
    assert len(retrieval.queries) == 1
    assert len(mapper.requests) == 3


def test_existing_explanation_still_runs() -> None:
    explanation = ScriptedExplanation()
    mapper = ScriptedMapper([_slot("payment"), _slot("self_payment")])
    processor, _, mapper = _build(mapper, explanation)
    state = _reach_employment(processor)
    result = _turn(processor, "什么叫灵活就业？", state)
    assert explanation.calls == 1
    assert "灵活就业是一种就业形式的说明" in result.response_text
    assert _EMPLOYMENT_QUESTION in result.response_text


def test_llm_renderer_drops_added_facts() -> None:
    document = load_guide_document(_GUIDE_PATH)
    service = GovernmentKnowledgeService({document.business_id: document})
    result = service.query("DEMO_SS_001", "consultation")
    provider = FakeLlm('{"text":"咨询电话是99999，而且免费。"}')
    renderer = FactConstrainedLlmRenderer(provider, TemplateGuideRenderer())
    rendered = renderer.render_facts(result)
    assert provider.calls == 1
    assert "99999" not in rendered
    assert "免费" not in rendered
    assert "0571-86438110" in rendered
