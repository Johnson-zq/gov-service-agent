"""F16-1 multi-matter foundation. Fixtures are not official government facts."""

from __future__ import annotations

import copy
import uuid
from pathlib import Path

from gov_service_agent.agent.explanation import (
    ExplanationRequest,
    ExplanationResult,
    ExplanationStatus,
)
from gov_service_agent.agent.guide_route import GuideQueryHandler, build_default_guide_handler
from gov_service_agent.agent.interaction import (
    AnswerMapperOutput,
    AnswerMappingRequest,
    MapperUtteranceKind,
)
from gov_service_agent.agent.materials_preview import (
    ConfirmedBusinessMaterialsPreviewProcessor,
)
from gov_service_agent.agent.terminal import read_f10
from gov_service_agent.agent.turn_processor import GovernmentAgentTurnProcessor
from gov_service_agent.agent.workflow import (
    SlotInteractionDependencies,
    TerminalConfirmationDependencies,
)
from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.business_graph.loader import load_decision_graph
from gov_service_agent.guide_knowledge.models import load_guide_document
from gov_service_agent.guide_knowledge.recognize import RecognitionKind, recognize_guide_utterance
from gov_service_agent.guide_knowledge.service import (
    GovernmentKnowledgeService,
    KnowledgeQueryStatus,
)
from gov_service_agent.matters.registry import MatterRegistry, load_matter_registry
from gov_service_agent.retrieval.types import RetrievalCandidate, RetrievalResult, RetrievalStatus
from gov_service_agent.session.models import SessionTurnPublicStatus, SessionTurnSuccess

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEMO_GRAPH = _REPO_ROOT / "data" / "graphs" / "demo" / "social_security.json"
_DEMO_BUSINESS = _REPO_ROOT / "data" / "demo" / "demo_ss_001.json"
_DEMO_GUIDE = _REPO_ROOT / "data" / "guides" / "DEMO_SS_001.guide.json"
_STUB_ROOT = _REPO_ROOT / "tests" / "fixtures" / "f16_stub_matter"
_STUB_GRAPH = _STUB_ROOT / "TEST_F16_STUB.graph.json"
_STUB_BUSINESS = _STUB_ROOT / "TEST_F16_STUB.business.json"
_STUB_GUIDE = _STUB_ROOT / "TEST_F16_STUB.guide.json"
_REGISTRY = _REPO_ROOT / "data" / "matters" / "registry.json"


class ScriptedMapper:
    def __init__(self, outputs: list[AnswerMapperOutput] | None = None) -> None:
        self._outputs = list(outputs or [])
        self.requests: list[AnswerMappingRequest] = []

    def map_answer(self, request: AnswerMappingRequest) -> AnswerMapperOutput:
        self.requests.append(request)
        if not self._outputs:
            raise AssertionError("mapper called unexpectedly")
        return self._outputs.pop(0)


class ScriptedExplanation:
    def explain(self, request: ExplanationRequest) -> ExplanationResult:
        return ExplanationResult(
            status=ExplanationStatus.ANSWERED,
            topic=request.topic,
            text="fixture explanation",
        )


class ScriptedRetrieval:
    def __init__(self, candidates: list[RetrievalCandidate]) -> None:
        self._candidates = candidates
        self.queries: list[str] = []

    def retrieve(self, query: str) -> RetrievalResult:
        self.queries.append(query)
        return RetrievalResult(
            status=RetrievalStatus.CANDIDATES,
            query=query,
            candidates=list(self._candidates),
        )


def _cand(business_id: str, *, rank: int = 1, score: float = 0.91) -> RetrievalCandidate:
    return RetrievalCandidate(
        business_id=business_id,
        display_name=business_id,
        score=score,
        rank=rank,
        direction="fixture",
        eligibility_scope="ONLINE",
    )


def _slot(value: str) -> AnswerMapperOutput:
    return AnswerMapperOutput(
        kind=MapperUtteranceKind.SLOT_ANSWER,
        mapped_value=value,
        confidence=0.95,
    )


def _dual_registry() -> MatterRegistry:
    return MatterRegistry.from_loaded(
        {
            "DEMO_SS_001": load_decision_graph(_DEMO_GRAPH),
            "TEST_F16_STUB": load_decision_graph(_STUB_GRAPH),
        },
        business_data_paths={
            "DEMO_SS_001": _DEMO_BUSINESS,
            "TEST_F16_STUB": _STUB_BUSINESS,
        },
        guide_paths={
            "DEMO_SS_001": _DEMO_GUIDE,
            "TEST_F16_STUB": _STUB_GUIDE,
        },
    )


def _repo() -> JsonBusinessRepository:
    return JsonBusinessRepository.from_paths([_DEMO_BUSINESS, _STUB_BUSINESS])


def _processor(
    retrieval: ScriptedRetrieval,
    *,
    registry: MatterRegistry | None = None,
    mapper: ScriptedMapper | None = None,
    load_guide: bool = True,
) -> GovernmentAgentTurnProcessor:
    reg = registry or _dual_registry()
    repository = _repo()
    graph = reg.require_graph("DEMO_SS_001")
    guide = None
    if load_guide:
        docs = {
            "DEMO_SS_001": load_guide_document(_DEMO_GUIDE),
            "TEST_F16_STUB": load_guide_document(_STUB_GUIDE),
        }
        guide = GuideQueryHandler(
            decision_graph=graph,
            knowledge_service=GovernmentKnowledgeService(
                docs,
                business_repository=repository,
            ),
            matter_registry=reg,
        )
    return GovernmentAgentTurnProcessor(
        decision_graph=graph,
        matter_registry=reg,
        business_repository=repository,
        retrieval_service=retrieval,  # type: ignore[arg-type]
        slot_dependencies=SlotInteractionDependencies(
            answer_mapper=mapper or ScriptedMapper([]),
            explanation_service=ScriptedExplanation(),
            decision_graph=graph,
            business_repository=repository,
        ),
        terminal_dependencies=TerminalConfirmationDependencies(
            business_repository=repository,
        ),
        guide_handler=guide,
        load_default_guide=False,
    )


def _turn(processor: GovernmentAgentTurnProcessor, text: str, restored=None):
    return processor.process_turn(
        session_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        input_text=text,
        restored_state=restored,
    )


def test_registry_resolves_graph_by_business_id() -> None:
    registry = load_matter_registry(_REGISTRY, repo_root=_REPO_ROOT)
    graph = registry.require_graph("DEMO_SS_001")
    assert graph.graph_id == "social_security"
    assert registry.get_graph("NOT_REGISTERED") is None
    docs = registry.load_guide_documents()
    assert "DEMO_SS_001" in docs
    assert "IDCARD_RC_LT5Y" in docs


def test_unregistered_candidate_cannot_enter_graph() -> None:
    registry = MatterRegistry.from_loaded(
        {"DEMO_SS_001": load_decision_graph(_DEMO_GRAPH)}
    )
    retrieval = ScriptedRetrieval([_cand("NOT_IN_REGISTRY", score=0.99)])
    processor = _processor(retrieval, registry=registry, load_guide=False)
    result = _turn(processor, "我想办一个未注册事项")
    assert "暂时无法确定" in result.response_text
    assert "f09" not in result.state["artifacts"] or result.state["artifacts"].get("f09") in (
        None,
        {},
    )
    assert result.state["artifacts"].get("f12") in (None, {})


def test_multi_registered_candidates_do_not_auto_pick_top_score() -> None:
    retrieval = ScriptedRetrieval(
        [
            _cand("DEMO_SS_001", rank=1, score=0.99),
            _cand("TEST_F16_STUB", rank=2, score=0.98),
        ]
    )
    result = _turn(_processor(retrieval, load_guide=False), "我想办事")
    assert "多项可能的业务" in result.response_text
    f12 = result.state["artifacts"]["f12"]
    assert f12["knowledge_context_unique"] is False
    assert f12.get("bound_business_id") in (None, "")
    assert "f09" not in result.state["artifacts"]


def test_guides_are_isolated_by_business_id() -> None:
    service = GovernmentKnowledgeService(
        {
            "DEMO_SS_001": load_guide_document(_DEMO_GUIDE),
            "TEST_F16_STUB": load_guide_document(_STUB_GUIDE),
        }
    )
    demo = service.query("DEMO_SS_001", "materials")
    stub = service.query("TEST_F16_STUB", "materials")
    assert demo.status is KnowledgeQueryStatus.FOUND
    assert "身份证" in demo.facts[0].text
    assert "测试夹具材料A" not in demo.facts[0].text
    assert stub.status is KnowledgeQueryStatus.FOUND
    assert "测试夹具材料A" in stub.facts[0].text
    assert "身份证" not in stub.facts[0].text
    missing = service.query("UNKNOWN_MATTER", "materials")
    assert missing.status is KnowledgeQueryStatus.NOT_FOUND


def test_early_guide_query_keeps_bound_graph_and_node() -> None:
    retrieval = ScriptedRetrieval([_cand("DEMO_SS_001")])
    processor = _processor(retrieval)
    pending = _turn(processor, "我想办社保", None).state
    before = copy.deepcopy(pending["artifacts"]["f09"])
    f12_before = copy.deepcopy(pending["artifacts"]["f12"])
    answered = _turn(processor, "需要什么材料？", pending)
    assert "身份证" in answered.response_text
    assert answered.state["artifacts"]["f09"] == before
    assert answered.state["artifacts"]["f12"]["bound_business_id"] == "DEMO_SS_001"
    assert answered.state["artifacts"]["f12"]["bound_graph_id"] == f12_before["bound_graph_id"]


def test_bound_session_does_not_reselect_graph_on_guide_turn() -> None:
    retrieval = ScriptedRetrieval(
        [
            _cand("TEST_F16_STUB", rank=1, score=0.99),
            _cand("DEMO_SS_001", rank=2, score=0.98),
        ]
    )
    # First bind DEMO uniquely, then ensure later retrieval noise is ignored.
    bind_retrieval = ScriptedRetrieval([_cand("DEMO_SS_001")])
    processor = _processor(bind_retrieval)
    pending = _turn(processor, "我想办社保", None).state
    assert pending["artifacts"]["f12"]["bound_business_id"] == "DEMO_SS_001"
    processor._retrieval_service = retrieval  # type: ignore[attr-defined]
    again = _turn(processor, "办结时限多久？", pending)
    assert again.state["artifacts"]["f12"]["bound_business_id"] == "DEMO_SS_001"
    assert again.state["artifacts"]["f12"]["bound_graph_id"] == "social_security"
    assert len(retrieval.queries) == 0


def test_checkpoint_restore_keeps_matter_binding() -> None:
    retrieval = ScriptedRetrieval([_cand("TEST_F16_STUB")])
    processor = _processor(retrieval)
    waiting = _turn(processor, "我想办测试夹具事项", None)
    assert waiting.public_status is SessionTurnPublicStatus.AWAITING_USER_INPUT
    f10 = read_f10(waiting.state["artifacts"])
    assert f10.get("confirmed_business_id") in (None, "")
    assert waiting.state["artifacts"]["f12"]["bound_business_id"] == "TEST_F16_STUB"
    assert waiting.state["artifacts"]["f12"]["bound_graph_id"] == "test_f16_stub"
    restored = copy.deepcopy(waiting.state)
    confirmed = _turn(processor, "确认", restored)
    assert read_f10(confirmed.state["artifacts"])["confirmed_business_id"] == "TEST_F16_STUB"
    assert confirmed.state["artifacts"]["f12"]["bound_graph_id"] == "test_f16_stub"


def test_shallow_graph_still_requires_explicit_f10_confirmation() -> None:
    retrieval = ScriptedRetrieval([_cand("TEST_F16_STUB")])
    result = _turn(_processor(retrieval, load_guide=False), "办理测试夹具")
    f10 = read_f10(result.state["artifacts"])
    assert f10.get("confirmed_business_id") in (None, "")
    assert result.requires_user_input is True
    assert "确认" in result.response_text


def test_guide_query_does_not_repeat_f13_preview() -> None:
    retrieval = ScriptedRetrieval([_cand("TEST_F16_STUB")])
    base = _processor(retrieval)
    repository = _repo()
    processor = ConfirmedBusinessMaterialsPreviewProcessor(
        base_processor=base,
        business_repository=repository,
    )
    waiting = _turn(processor, "办理测试夹具", None)
    confirmed = _turn(processor, "确认", waiting.state)
    assert "测试夹具材料A" in confirmed.response_text
    later = _turn(processor, "需要什么材料？", confirmed.state)
    assert later.response_text.count("需要准备的材料") == 0
    assert "测试夹具材料A" in later.response_text
    assert read_f10(later.state["artifacts"])["confirmed_business_id"] == "TEST_F16_STUB"


def test_demo_ss_phrases_do_not_apply_on_stub_matter() -> None:
    recognition = recognize_guide_utterance(
        "银行扣缴协议怎么签？",
        pending_question_text=None,
        active_business_id="TEST_F16_STUB",
    )
    assert not (
        recognition.kind is RecognitionKind.TOPIC
        and recognition.topic == "faq"
        and recognition.subtopic == "bank_withholding"
    )
    demo = recognize_guide_utterance(
        "银行扣缴协议怎么签？",
        pending_question_text=None,
        active_business_id="DEMO_SS_001",
    )
    assert demo.kind is RecognitionKind.TOPIC
    assert demo.topic == "faq"
    assert demo.subtopic == "bank_withholding"


def test_build_default_guide_handler_loads_registry_documents() -> None:
    registry = _dual_registry()
    repository = _repo()
    handler = build_default_guide_handler(
        registry.require_graph("DEMO_SS_001"),
        repository,
        matter_registry=registry,
    )
    assert handler is not None
    demo = handler._knowledge.query("DEMO_SS_001", "materials")
    stub = handler._knowledge.query("TEST_F16_STUB", "materials")
    assert demo.status is KnowledgeQueryStatus.FOUND
    assert stub.status is KnowledgeQueryStatus.FOUND


def test_bound_graph_mismatch_stops_safely() -> None:
    retrieval = ScriptedRetrieval([_cand("DEMO_SS_001")])
    processor = _processor(retrieval, load_guide=False)
    pending = _turn(processor, "我想办社保", None).state
    broken = copy.deepcopy(pending)
    broken["artifacts"]["f12"]["bound_graph_id"] = "wrong_graph"
    result = _turn(processor, "自己缴", broken)
    assert "无法继续" in result.response_text
    assert result.requires_user_input is True


def test_f11_public_success_fields_unchanged() -> None:
    assert set(SessionTurnSuccess.model_fields) == {
        "session_id",
        "request_id",
        "status",
        "response_text",
        "requires_user_input",
    }


def test_demo_first_turn_still_extracts_payment_slots() -> None:
    from gov_service_agent.agent.first_turn_extract import deterministic_slot_candidates

    class DeterministicOnly:
        def accepted_slots(
            self,
            user_text: str,
            *,
            decision_graph=None,
            business_id: str | None = None,
        ) -> dict[str, str]:
            assert decision_graph is not None
            return deterministic_slot_candidates(
                user_text,
                decision_graph,
                business_id=business_id,
            )

    retrieval = ScriptedRetrieval([_cand("DEMO_SS_001")])
    registry = _dual_registry()
    repository = _repo()
    graph = registry.require_graph("DEMO_SS_001")
    processor = GovernmentAgentTurnProcessor(
        decision_graph=graph,
        matter_registry=registry,
        business_repository=repository,
        retrieval_service=retrieval,  # type: ignore[arg-type]
        slot_dependencies=SlotInteractionDependencies(
            answer_mapper=ScriptedMapper([]),
            explanation_service=ScriptedExplanation(),
            decision_graph=graph,
            business_repository=repository,
        ),
        terminal_dependencies=TerminalConfirmationDependencies(
            business_repository=repository,
        ),
        first_turn_extractor=DeterministicOnly(),
        load_default_guide=False,
    )
    result = _turn(processor, "我想自己交社保")
    text = result.response_text
    assert "就业" in text or "灵活就业" in text
    f12 = result.state["artifacts"]["f12"]
    assert f12["bound_business_id"] == "DEMO_SS_001"
    assert f12["knowledge_context_unique"] is True
