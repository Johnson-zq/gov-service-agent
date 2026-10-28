"""F16-3 remote referral filing (异地转诊人员备案). Fake Provider only."""

from __future__ import annotations

import copy
import uuid
from pathlib import Path

import pytest
from redis import Redis

from gov_service_agent.agent.explanation import (
    ExplanationRequest,
    ExplanationResult,
    ExplanationStatus,
)
from gov_service_agent.agent.guide_route import GuideQueryHandler
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
from gov_service_agent.guide_knowledge.render import TemplateGuideRenderer
from gov_service_agent.guide_knowledge.service import (
    GovernmentKnowledgeService,
    KnowledgeQueryStatus,
)
from gov_service_agent.matters.registry import load_matter_registry
from gov_service_agent.retrieval.admission import draft_online_documents, load_admission_policy
from gov_service_agent.retrieval.types import RetrievalCandidate, RetrievalResult, RetrievalStatus
from gov_service_agent.session.models import SessionTurnRequest
from gov_service_agent.session.service import SessionTurnService
from gov_service_agent.session.store import RedisSessionConfig, RedisSessionStore

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEMO_BUSINESS = _REPO_ROOT / "data" / "demo" / "demo_ss_001.json"
_ID_BUSINESS = _REPO_ROOT / "data" / "demo" / "idcard_rc_lt5y.json"
_REF_BUSINESS = _REPO_ROOT / "data" / "demo" / "referral_yidi_ba.json"
_DEMO_GUIDE = _REPO_ROOT / "data" / "guides" / "DEMO_SS_001.guide.json"
_ID_GUIDE = _REPO_ROOT / "data" / "guides" / "IDCARD_RC_LT5Y.guide.json"
_REF_GUIDE = _REPO_ROOT / "data" / "guides" / "REFERRAL_YIDI_BA.guide.json"
_REF_GRAPH = _REPO_ROOT / "data" / "graphs" / "demo" / "referral_yidi_ba.json"
_REGISTRY = _REPO_ROOT / "data" / "matters" / "registry.json"
_POLICY = _REPO_ROOT / "data" / "retrieval" / "f06_online_eligibility.json"
_SS = "DEMO_SS_001"
_ID = "IDCARD_RC_LT5Y"
_REF = "REFERRAL_YIDI_BA"


class ScriptedMapper:
    def __init__(self, outputs: list[AnswerMapperOutput] | None = None) -> None:
        self._outputs = list(outputs or [])
        self.requests: list[AnswerMappingRequest] = []

    def map_answer(self, request: AnswerMappingRequest) -> AnswerMapperOutput:
        self.requests.append(request)
        if not self._outputs:
            raise AssertionError(f"unexpected mapper call for {request.required_slot}")
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


def _registry():
    return load_matter_registry(_REGISTRY, repo_root=_REPO_ROOT)


def _repo() -> JsonBusinessRepository:
    return JsonBusinessRepository.from_paths(
        [_DEMO_BUSINESS, _ID_BUSINESS, _REF_BUSINESS]
    )


def _processor(
    retrieval: ScriptedRetrieval,
    *,
    mapper: ScriptedMapper | None = None,
    with_guide: bool = True,
) -> GovernmentAgentTurnProcessor:
    registry = _registry()
    repository = _repo()
    graph = registry.require_graph(_REF)
    guide = None
    if with_guide:
        docs = {
            _SS: load_guide_document(_DEMO_GUIDE),
            _ID: load_guide_document(_ID_GUIDE),
            _REF: load_guide_document(_REF_GUIDE),
        }
        guide = GuideQueryHandler(
            decision_graph=graph,
            knowledge_service=GovernmentKnowledgeService(
                docs,
                business_repository=repository,
            ),
            matter_registry=registry,
        )
    return GovernmentAgentTurnProcessor(
        decision_graph=graph,
        matter_registry=registry,
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


def test_registry_admission_and_shallow_graph() -> None:
    registry = _registry()
    assert registry.has(_REF)
    assert registry.require_graph(_REF).graph_id == "referral_yidi_ba"
    policy = load_admission_policy(_POLICY)
    assert policy.allow_ids() == frozenset({_SS, _ID, _REF})
    drafts = draft_online_documents(_repo(), policy)
    assert [d.business_id for d in drafts] == [_SS, _ID, _REF]
    assert "异地转诊人员备案" in drafts[2].retrieval_text
    graph = load_decision_graph(_REF_GRAPH)
    assert all(node.node_type.value != "SLOT_GATE" for node in graph.nodes)
    snap = _repo().get_snapshot(_REF)
    assert snap.conditions == []
    assert len(snap.materials) == 2
    zheliban = next(ch for ch in snap.channels if ch.channel_id == "ch-zheliban")
    assert zheliban.source_name == "浙里办APP"
    assert zheliban.channel_type.value == "ONLINE"
    assert zheliban.channel_type.value != "MINI_PROGRAM"
    assert all(ch.source_name != "浙里办小程序" for ch in snap.channels)


def test_guide_covers_core_topics_without_inventing_fees() -> None:
    service = GovernmentKnowledgeService(
        {_REF: load_guide_document(_REF_GUIDE)},
        business_repository=_repo(),
    )
    materials = service.query(_REF, "materials")
    assert materials.status is KnowledgeQueryStatus.FOUND
    joined = "\n".join(f.text for f in materials.facts)
    assert "异地转诊备案表" in joined
    assert "医保电子凭证" in joined or "身份证件" in joined

    fees = service.query(_REF, "fees")
    assert "未记载" in fees.facts[0].text
    assert "不能据此判断是否收费" in fees.facts[0].text
    assert "免费" not in fees.facts[0].text or "不能写成不收费" in fees.facts[0].text

    deadline = service.query(_REF, "completion_time")
    assert "即办" in deadline.facts[0].text

    locations = service.query(_REF, "handling_locations")
    assert "塘潮街6号" in locations.facts[0].text

    faq = service.query(_REF, "faq", "agencies")
    assert "浙里办APP" in faq.facts[0].text
    assert "浙江政务服务网" in faq.facts[0].text
    assert "小程序" not in faq.facts[0].text

    channels = service.query(_REF, "channels")
    assert channels.status is KnowledgeQueryStatus.FOUND
    channel_text = "\n".join(f.text for f in channels.facts)
    assert "浙里办APP" in channel_text
    assert "小程序" not in channel_text

    rendered = TemplateGuideRenderer().render_facts(channels)
    assert "浙里办APP" in rendered
    assert "小程序" not in rendered
    rendered_faq = TemplateGuideRenderer().render_facts(faq)
    assert "浙里办APP" in rendered_faq
    assert "小程序" not in rendered_faq


def test_shallow_graph_reaches_f10_without_slots() -> None:
    result = _turn(_processor(ScriptedRetrieval([_cand(_REF)])), "我想办理异地转诊备案")
    assert result.state["artifacts"]["f12"]["bound_business_id"] == _REF
    assert result.state["artifacts"]["f12"]["bound_graph_id"] == "referral_yidi_ba"
    f10 = read_f10(result.state["artifacts"])
    assert f10.get("confirmed_business_id") in (None, "")
    assert f10["terminal_context"]["candidate_business_id"] == _REF
    assert "确认" in result.response_text
    assert result.requires_user_input is True


def test_f10_confirm_then_f13_materials_once() -> None:
    base = _processor(ScriptedRetrieval([_cand(_REF)]))
    preview = ConfirmedBusinessMaterialsPreviewProcessor(
        base_processor=base,
        business_repository=_repo(),
    )
    pending = _turn(base, "异地转诊人员备案", None).state
    confirmed = _turn(preview, "确认", pending)
    assert read_f10(confirmed.state["artifacts"])["confirmed_business_id"] == _REF
    assert "需要准备的材料" in confirmed.response_text
    assert confirmed.response_text.count("需要准备的材料") == 1
    assert "异地转诊备案表" in confirmed.response_text
    again = _turn(preview, "还需要什么材料？", confirmed.state)
    assert again.response_text.count("需要准备的材料") == 0
    assert "异地转诊备案表" in again.response_text or "现场正面照片" not in again.response_text


def test_guide_during_confirmation_and_after_confirm() -> None:
    base = _processor(ScriptedRetrieval([_cand(_REF)]))
    preview = ConfirmedBusinessMaterialsPreviewProcessor(
        base_processor=base,
        business_repository=_repo(),
    )
    pending = _turn(base, "办异地转诊备案", None).state
    before = copy.deepcopy(pending["artifacts"]["f10"])
    fee = _turn(base, "备案要收多少钱？", pending)
    assert "没有记载具体收费" in fee.response_text or "不能判断" in fee.response_text
    assert fee.state["artifacts"]["f10"]["terminal_context"] == before["terminal_context"]
    assert read_f10(fee.state["artifacts"]).get("confirmed_business_id") in (None, "")

    confirmed = _turn(preview, "确认", fee.state)
    assert read_f10(confirmed.state["artifacts"])["confirmed_business_id"] == _REF
    agencies = _turn(preview, "哪些经办机构可以办理？", confirmed.state)
    assert "浙里办APP" in agencies.response_text
    assert "小程序" not in agencies.response_text
    assert agencies.state["artifacts"]["f12"]["bound_business_id"] == _REF
    assert read_f10(agencies.state["artifacts"])["confirmed_business_id"] == _REF


def test_three_matters_knowledge_isolation() -> None:
    service = GovernmentKnowledgeService(
        {
            _SS: load_guide_document(_DEMO_GUIDE),
            _ID: load_guide_document(_ID_GUIDE),
            _REF: load_guide_document(_REF_GUIDE),
        },
        business_repository=_repo(),
    )
    ref_mat = "\n".join(f.text for f in service.query(_REF, "materials").facts)
    id_mat = "\n".join(f.text for f in service.query(_ID, "materials").facts)
    ss_mat = "\n".join(f.text for f in service.query(_SS, "materials").facts)
    assert "异地转诊备案表" in ref_mat
    assert "现场正面照片" not in ref_mat
    assert "现场正面照片" in id_mat
    assert "异地转诊备案表" not in id_mat
    assert "异地转诊备案表" not in ss_mat


def test_ss_and_idcard_still_bind_own_graphs() -> None:
    registry = _registry()
    repository = _repo()

    def _one(business_id: str, text: str, expected_graph: str) -> None:
        graph = registry.require_graph(business_id)
        docs = {
            _SS: load_guide_document(_DEMO_GUIDE),
            _ID: load_guide_document(_ID_GUIDE),
            _REF: load_guide_document(_REF_GUIDE),
        }
        processor = GovernmentAgentTurnProcessor(
            decision_graph=graph,
            matter_registry=registry,
            business_repository=repository,
            retrieval_service=ScriptedRetrieval([_cand(business_id)]),  # type: ignore[arg-type]
            slot_dependencies=SlotInteractionDependencies(
                answer_mapper=ScriptedMapper([]),
                explanation_service=ScriptedExplanation(),
                decision_graph=graph,
                business_repository=repository,
            ),
            terminal_dependencies=TerminalConfirmationDependencies(
                business_repository=repository,
            ),
            guide_handler=GuideQueryHandler(
                decision_graph=graph,
                knowledge_service=GovernmentKnowledgeService(
                    docs,
                    business_repository=repository,
                ),
                matter_registry=registry,
            ),
            load_default_guide=False,
        )
        result = _turn(processor, text)
        assert result.state["artifacts"]["f12"]["bound_business_id"] == business_id
        assert result.state["artifacts"]["f12"]["bound_graph_id"] == expected_graph

    _one(_SS, "我想自己交社保", "social_security")
    _one(_ID, "身份证丢了要补办", "idcard_replace_lt5y")


def test_medical_not_out_of_guide_when_referral_active() -> None:
    recognition = recognize_guide_utterance(
        "医保窗口在哪里？",
        pending_question_text=None,
        active_business_id=_REF,
    )
    assert recognition.kind is RecognitionKind.TOPIC
    assert recognition.topic == "handling_locations"


def test_session_multi_turn_referral_with_memory_store() -> None:
    from tests.test_f12_session_integration import MemoryStore

    processor = _processor(ScriptedRetrieval([_cand(_REF)]))
    preview = ConfirmedBusinessMaterialsPreviewProcessor(
        base_processor=processor,
        business_repository=_repo(),
    )
    store = MemoryStore()
    service = SessionTurnService(
        store=store,  # type: ignore[arg-type]
        processor=preview,
        max_input_chars=4000,
        session_ttl_seconds=3600,
    )
    first = service.handle_turn(
        SessionTurnRequest(
            request_id=str(uuid.uuid4()),
            session_id=None,
            input_text="我想办异地转诊人员备案",
        )
    )
    sid = first.session_id
    assert "确认" in first.response_text
    mid = service.handle_turn(
        SessionTurnRequest(
            request_id=str(uuid.uuid4()),
            session_id=sid,
            input_text="需要什么材料？",
        )
    )
    assert "异地转诊备案表" in mid.response_text
    assert read_f10(store.sessions[sid][1].state.artifacts).get(
        "confirmed_business_id"
    ) in (None, "")
    confirmed = service.handle_turn(
        SessionTurnRequest(
            request_id=str(uuid.uuid4()),
            session_id=sid,
            input_text="确认",
        )
    )
    assert read_f10(store.sessions[sid][1].state.artifacts)[
        "confirmed_business_id"
    ] == _REF
    assert "需要准备的材料" in confirmed.response_text


def test_redis_checkpoint_referral_bind() -> None:
    client = Redis(host="127.0.0.1", port=6379, decode_responses=True)
    try:
        client.ping()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Redis 6379 unavailable: {exc}")
    prefix = f"govagent:f16ref:{uuid.uuid4().hex[:8]}"
    store = RedisSessionStore(
        client,
        RedisSessionConfig(
            key_prefix=prefix,
            session_ttl_seconds=120,
            session_expired_marker_ttl_seconds=60,
            audit_ttl_seconds=120,
            request_dedup_ttl_seconds=120,
            request_lock_ttl_seconds=5,
            session_lock_ttl_seconds=5,
        ),
    )
    service = SessionTurnService(
        store=store,
        processor=_processor(ScriptedRetrieval([_cand(_REF)])),
        max_input_chars=4000,
        session_ttl_seconds=120,
    )
    try:
        first = service.handle_turn(
            SessionTurnRequest(
                request_id=str(uuid.uuid4()),
                session_id=None,
                input_text="异地转诊备案",
            )
        )
        second = service.handle_turn(
            SessionTurnRequest(
                request_id=str(uuid.uuid4()),
                session_id=first.session_id,
                input_text="多久能办好？",
            )
        )
        assert "即办" in second.response_text
        from datetime import datetime, timezone

        _meta, checkpoint = store.load_active_session(
            first.session_id,
            now=datetime.now(timezone.utc),
        )
        assert checkpoint.state.artifacts["f12"]["bound_business_id"] == _REF
        assert checkpoint.state.artifacts["f12"]["bound_graph_id"] == "referral_yidi_ba"
    finally:
        for key in client.scan_iter(match=f"{prefix}*"):
            client.delete(key)
