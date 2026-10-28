"""F16-2 resident ID card replace/reissue (领证未满五年). Fake Provider only."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from redis import Redis

from gov_service_agent.agent.explanation import (
    ExplanationRequest,
    ExplanationResult,
    ExplanationStatus,
)
from gov_service_agent.agent.first_turn_extract import deterministic_slot_candidates
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
from gov_service_agent.guide_knowledge.service import (
    GovernmentKnowledgeService,
    KnowledgeQueryStatus,
)
from gov_service_agent.matters.registry import MatterRegistry, load_matter_registry
from gov_service_agent.retrieval.admission import draft_online_documents, load_admission_policy
from gov_service_agent.retrieval.types import RetrievalCandidate, RetrievalResult, RetrievalStatus
from gov_service_agent.session.models import (
    AuditEvent,
    CachedRequestResult,
    SessionCheckpoint,
    SessionMeta,
    SessionTurnRequest,
)
from gov_service_agent.session.service import SessionTurnService
from gov_service_agent.session.store import RedisSessionConfig, RedisSessionStore

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEMO_GRAPH = _REPO_ROOT / "data" / "graphs" / "demo" / "social_security.json"
_DEMO_BUSINESS = _REPO_ROOT / "data" / "demo" / "demo_ss_001.json"
_DEMO_GUIDE = _REPO_ROOT / "data" / "guides" / "DEMO_SS_001.guide.json"
_ID_GRAPH = _REPO_ROOT / "data" / "graphs" / "demo" / "idcard_replace_lt5y.json"
_ID_BUSINESS = _REPO_ROOT / "data" / "demo" / "idcard_rc_lt5y.json"
_REF_BUSINESS = _REPO_ROOT / "data" / "demo" / "referral_yidi_ba.json"
_ID_GUIDE = _REPO_ROOT / "data" / "guides" / "IDCARD_RC_LT5Y.guide.json"
_REGISTRY = _REPO_ROOT / "data" / "matters" / "registry.json"
_POLICY = _REPO_ROOT / "data" / "retrieval" / "f06_online_eligibility.json"
_ID = "IDCARD_RC_LT5Y"
_SS = "DEMO_SS_001"
_REF = "REFERRAL_YIDI_BA"


class ScriptedMapper:
    def __init__(self, outputs: list[AnswerMapperOutput] | None = None) -> None:
        self._outputs = list(outputs or [])
        self.requests: list[AnswerMappingRequest] = []

    def map_answer(self, request: AnswerMappingRequest) -> AnswerMapperOutput:
        self.requests.append(request)
        if not self._outputs:
            raise AssertionError(
                f"unexpected mapper call for {request.required_slot}"
            )
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


class DeterministicExtractor:
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


def _cand(business_id: str, *, rank: int = 1, score: float = 0.91) -> RetrievalCandidate:
    return RetrievalCandidate(
        business_id=business_id,
        display_name=business_id,
        score=score,
        rank=rank,
        direction="fixture",
        eligibility_scope="ONLINE",
    )


def _slot(value: str, confidence: float = 0.95) -> AnswerMapperOutput:
    return AnswerMapperOutput(
        kind=MapperUtteranceKind.SLOT_ANSWER,
        mapped_value=value,
        confidence=confidence,
    )


def _registry() -> MatterRegistry:
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
    with_extractor: bool = True,
) -> GovernmentAgentTurnProcessor:
    registry = _registry()
    repository = _repo()
    graph = registry.require_graph(_ID)
    guide = None
    if with_guide:
        docs = {
            _SS: load_guide_document(_DEMO_GUIDE),
            _ID: load_guide_document(_ID_GUIDE),
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
        first_turn_extractor=DeterministicExtractor() if with_extractor else None,
        load_default_guide=False,
    )


def _turn(processor: GovernmentAgentTurnProcessor, text: str, restored=None):
    return processor.process_turn(
        session_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        input_text=text,
        restored_state=restored,
    )


def _reach_confirmation(processor: GovernmentAgentTurnProcessor, mapper: ScriptedMapper):
    pending = _turn(processor, "我的身份证丢了，想补办", None).state
    assert pending["artifacts"]["f12"]["bound_business_id"] == _ID
    # Explicit guide phrases are absorbed deterministically (no mapper).
    answers = [
        "现场照片是本人",
        "相貌没有变化",
        "没有不良信用",
        "是，未满五年且有效",
        "有效期十年及以上",
        "户口在浙江",
    ]
    state = pending
    for text in answers:
        state = _turn(processor, text, state).state
    del mapper  # Mapper reserved for unclear utterances in other tests.
    return state


def test_registry_and_admission_include_idcard() -> None:
    registry = _registry()
    assert registry.has(_ID)
    assert registry.require_graph(_ID).graph_id == "idcard_replace_lt5y"
    policy = load_admission_policy(_POLICY)
    assert _ID in policy.allow_ids() and _SS in policy.allow_ids()
    drafts = draft_online_documents(_repo(), policy)
    assert _ID in {d.business_id for d in drafts}
    assert "居民身份证换补领" in next(
        d.retrieval_text for d in drafts if d.business_id == _ID
    )


def test_idcard_and_ss_guides_are_isolated() -> None:
    service = GovernmentKnowledgeService(
        {
            _SS: load_guide_document(_DEMO_GUIDE),
            _ID: load_guide_document(_ID_GUIDE),
        }
    )
    id_materials = service.query(_ID, "materials")
    ss_materials = service.query(_SS, "materials")
    assert id_materials.status is KnowledgeQueryStatus.FOUND
    assert "现场正面照片" in id_materials.facts[0].text
    assert "身份证" in ss_materials.facts[0].text
    assert "现场正面照片" not in ss_materials.facts[0].text
    fees = service.query(_ID, "fees")
    assert "40元/证" in fees.facts[0].text
    assert "不能据此判断存在减免或免费" in fees.facts[0].text
    deadline = service.query(_ID, "completion_time")
    assert "10工作日" in deadline.facts[0].text
    assert "60日" in deadline.facts[0].text


def test_first_turn_lost_id_enters_idcard_graph() -> None:
    retrieval = ScriptedRetrieval([_cand(_ID)])
    result = _turn(_processor(retrieval), "身份证丢了，要补办")
    assert result.state["artifacts"]["f12"]["bound_business_id"] == _ID
    assert result.state["artifacts"]["f12"]["bound_graph_id"] == "idcard_replace_lt5y"
    assert "丢失需要补领" in result.response_text
    assert "是您本人吗" in result.response_text or "现场正面照片" in result.response_text
    assert "是不是非申请人本人" not in result.response_text
    assert "没有这些情形" not in result.response_text
    assert "需要线下办理" not in result.response_text


def test_ss_intent_still_uses_ss_graph() -> None:
    retrieval = ScriptedRetrieval([_cand(_SS)])
    registry = _registry()
    repository = _repo()
    graph = registry.require_graph(_SS)
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
        first_turn_extractor=DeterministicExtractor(),
        load_default_guide=False,
    )
    result = _turn(processor, "我想自己交社保")
    assert result.state["artifacts"]["f12"]["bound_business_id"] == _SS
    assert result.state["artifacts"]["f12"]["bound_graph_id"] == "social_security"


def test_multi_candidate_does_not_pick_top_score() -> None:
    retrieval = ScriptedRetrieval(
        [_cand(_ID, rank=1, score=0.99), _cand(_SS, rank=2, score=0.98)]
    )
    result = _turn(_processor(retrieval, with_guide=False), "我想办事")
    assert "多项可能的业务" in result.response_text
    assert result.state["artifacts"]["f12"].get("bound_business_id") in (None, "")


def test_appearance_change_routes_offline_not_rejection() -> None:
    retrieval = ScriptedRetrieval([_cand(_ID)])
    result = _turn(_processor(retrieval), "身份证损坏了，相貌变化比较大，可以网上补办吗？")
    assert "线下窗口" in result.response_text or "线下" in result.response_text
    assert "不是拒绝" in result.response_text
    # Concise offline divert: full station list only on explicit location ask.
    assert "清波" not in result.response_text
    assert "九堡" not in result.response_text
    assert "办理地点" in result.response_text
    assert result.public_status.value == "COMPLETED"
    assert result.requires_user_input is False
    assert result.response_text.count("（一）") == 0
    assert read_f10(result.state["artifacts"]).get("confirmed_business_id") in (None, "")


def test_photo_not_self_routes_offline() -> None:
    result = _turn(
        _processor(ScriptedRetrieval([_cand(_ID)])),
        "身份证丢了，现场照片不是本人",
    )
    assert "线下" in result.response_text
    assert "不是拒绝" in result.response_text
    assert result.public_status.value == "COMPLETED"
    assert result.requires_user_input is False
    assert "清波" not in result.response_text
    assert read_f10(result.state["artifacts"]).get("confirmed_business_id") in (None, "")


def test_ineligible_condition_routes_to_offline_guidance() -> None:
    # Photo/appearance/credit phrases are deterministic; only biometric needs mapper.
    mapper = ScriptedMapper([_slot("not_valid")])
    processor = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=mapper)
    pending = _turn(processor, "身份证损坏要换领", None).state
    mid = _turn(processor, "现场照片是本人", pending).state
    mid = _turn(processor, "相貌没有变化", mid).state
    mid = _turn(processor, "没有不良信用", mid).state
    assert (
        mid["artifacts"]["f09"]["business_transition"]["current_node_id"]
        == "biometric_info_status"
    )
    result = _turn(processor, "不是", mid)
    assert "不符合" in result.response_text or "线下窗口" in result.response_text
    assert result.public_status.value == "COMPLETED"
    assert read_f10(result.state["artifacts"]).get("confirmed_business_id") in (None, "")


def test_unclear_slot_does_not_advance() -> None:
    mapper = ScriptedMapper(
        [
            AnswerMapperOutput(
                kind=MapperUtteranceKind.OTHER,
                mapped_value=None,
                confidence=None,
            )
        ]
    )
    processor = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=mapper)
    pending = _turn(processor, "身份证丢了", None).state
    before = pending["artifacts"]["f09"]["business_transition"]["current_node_id"]
    again = _turn(processor, "随便吧", pending)
    f09 = again.state["artifacts"]["f09"]
    slot = f09.get("slot_context") or {}
    transition = f09.get("business_transition") or {}
    assert (transition.get("current_node_id") or slot.get("current_node_id")) == before
    assert again.requires_user_input is True
    assert read_f10(again.state["artifacts"]).get("confirmed_business_id") in (None, "")


def test_guide_facts_and_early_query() -> None:
    mapper = ScriptedMapper([])
    processor = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=mapper)
    pending = _turn(processor, "身份证丢了", None).state
    before = copy.deepcopy(pending["artifacts"]["f09"])
    fees = _turn(processor, "补办要多少钱？", pending)
    assert "40元" in fees.response_text
    assert fees.state["artifacts"]["f09"] == before
    deadline = _turn(processor, "多久能办好？", fees.state)
    assert "10工作日" in deadline.response_text
    assert "60日" in deadline.response_text
    assert "当天一定" not in deadline.response_text
    onsite = _turn(processor, "要不要去现场？", deadline.state)
    assert "全程网办" in onsite.response_text or "0次" in onsite.response_text


def test_ss_phrases_do_not_apply_on_idcard() -> None:
    recognition = recognize_guide_utterance(
        "银行扣缴协议怎么签？",
        pending_question_text=None,
        active_business_id=_ID,
    )
    assert not (
        recognition.kind is RecognitionKind.TOPIC
        and recognition.subtopic == "bank_withholding"
    )


def test_f10_f13_closed_loop_once() -> None:
    mapper = ScriptedMapper([])
    base = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=mapper)
    preview = ConfirmedBusinessMaterialsPreviewProcessor(
        base_processor=base,
        business_repository=_repo(),
    )
    state = _reach_confirmation(base, mapper)
    assert read_f10(state["artifacts"]).get("confirmed_business_id") in (None, "")
    confirmed = _turn(preview, "确认", state)
    assert read_f10(confirmed.state["artifacts"])["confirmed_business_id"] == _ID
    assert "现场正面照片" in confirmed.response_text
    assert confirmed.response_text.count("需要准备的材料") == 1
    materials_section = confirmed.response_text.split("需要准备的材料")[-1]
    assert "交社保" not in materials_section
    later = _turn(preview, "还需要什么材料？", confirmed.state)
    assert later.response_text.count("需要准备的材料") == 0
    assert read_f10(later.state["artifacts"])["confirmed_business_id"] == _ID
    assert later.state["artifacts"]["f12"]["bound_graph_id"] == "idcard_replace_lt5y"


def test_memory_checkpoint_keeps_bound_graph() -> None:
    from tests.test_f12_session_integration import MemoryStore

    mapper = ScriptedMapper([])
    processor = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=mapper)
    store = MemoryStore()
    service = SessionTurnService(
        store=store,  # type: ignore[arg-type]
        processor=processor,
        max_input_chars=2000,
        session_ttl_seconds=3600,
    )
    first = service.handle_turn(
        SessionTurnRequest(
            request_id=str(uuid.uuid4()),
            session_id=None,
            input_text="身份证丢了要补领",
        )
    )
    session_id = first.session_id
    assert first.requires_user_input is True
    checkpoint = store.sessions[session_id][1]
    f12 = checkpoint.state.artifacts["f12"]
    assert f12["bound_business_id"] == _ID
    assert f12["bound_graph_id"] == "idcard_replace_lt5y"
    second = service.handle_turn(
        SessionTurnRequest(
            request_id=str(uuid.uuid4()),
            session_id=session_id,
            input_text="补办要收多少钱？",
        )
    )
    assert "40元" in second.response_text
    restored = store.sessions[session_id][1].state.artifacts["f12"]
    assert restored["bound_business_id"] == _ID
    assert restored["bound_graph_id"] == "idcard_replace_lt5y"


def test_redis_checkpoint_bind_restore() -> None:
    client = Redis(host="127.0.0.1", port=6379, decode_responses=True)
    try:
        client.ping()
    except Exception as exc:  # pragma: no cover - environment
        pytest.skip(f"Redis 6379 unavailable: {exc}")
    prefix = f"govagent:f16id:{uuid.uuid4().hex[:8]}"
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
    mapper = ScriptedMapper([])
    processor = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=mapper)
    service = SessionTurnService(
        store=store,
        processor=processor,
        max_input_chars=2000,
        session_ttl_seconds=120,
    )
    try:
        first = service.handle_turn(
            SessionTurnRequest(
                request_id=str(uuid.uuid4()),
                session_id=None,
                input_text="身份证遗失补办",
            )
        )
        second = service.handle_turn(
            SessionTurnRequest(
                request_id=str(uuid.uuid4()),
                session_id=first.session_id,
                input_text="需要什么材料？",
            )
        )
        assert "现场正面照片" in second.response_text
        _meta, checkpoint = store.load_active_session(
            first.session_id,
            now=datetime.now(timezone.utc),
        )
        f12 = checkpoint.state.artifacts["f12"]
        assert f12["bound_business_id"] == _ID
        assert f12["bound_graph_id"] == "idcard_replace_lt5y"
    finally:
        for key in client.scan_iter(match=f"{prefix}*"):
            client.delete(key)


def test_f11_public_fields_unchanged() -> None:
    from gov_service_agent.session.models import SessionTurnSuccess

    assert set(SessionTurnSuccess.model_fields) == {
        "session_id",
        "request_id",
        "status",
        "response_text",
        "requires_user_input",
    }


def test_owner_confirmed_and_condition_group() -> None:
    from gov_service_agent.business_data.models import VerificationStatus

    conditions = _repo().get_conditions(_ID)
    cond = next(c for c in conditions if c.condition_id == "cond-condition-group-and")
    assert cond.source_status is VerificationStatus.VERIFIED
    assert cond.normalized_values == ["AND"]
    assert "Owner" in (cond.source_text or "")
    assert "不是办事指南原文" in (cond.source_text or "")
    assert not any(c.condition_id == "cond-tc-condition-group-logic" for c in conditions)


def test_field_photo_does_not_force_offline_slot() -> None:
    graph = load_decision_graph(_ID_GRAPH)
    # On-site capture alone must not map to offline-exception facts.
    for text in (
        "我已经拍了现场正面照片，可以在线申请吗",
        "现场正面照片采集好了",
        "需要现场拍照片然后网办",
    ):
        slots = deterministic_slot_candidates(text, graph, business_id=_ID)
        assert slots.get("submitted_photo_not_self") != "yes", text
        assert slots.get("appearance_change_major") != "yes", text
        assert slots.get("bad_credit_record") != "yes", text
    assert (
        deterministic_slot_candidates(
            "现场照片不是本人",
            graph,
            business_id=_ID,
        ).get("submitted_photo_not_self")
        == "yes"
    )
    assert (
        deterministic_slot_candidates(
            "现场照片是本人",
            graph,
            business_id=_ID,
        ).get("submitted_photo_not_self")
        == "no"
    )
    # Saying photo is self must NOT skip the appearance-change check.
    assert (
        deterministic_slot_candidates(
            "现场照片是本人",
            graph,
            business_id=_ID,
        ).get("appearance_change_major")
        is None
    )


def test_field_photo_question_routes_to_materials_not_offline_only() -> None:
    recognition = recognize_guide_utterance(
        "现场正面照片怎么准备？拍了是不是只能线下办？",
        pending_question_text=None,
        active_business_id=_ID,
    )
    assert recognition.kind is RecognitionKind.TOPIC
    assert recognition.topic == "materials"
    service = GovernmentKnowledgeService(
        {_ID: load_guide_document(_ID_GUIDE)},
        business_repository=_repo(),
    )
    result = service.query(_ID, "materials")
    assert result.status is KnowledgeQueryStatus.FOUND
    joined = "\n".join(f.text for f in result.facts)
    assert "现场正面照片" in joined
    assert "Owner业务规则确认" in joined
    assert "不等于整个申请必须线下" in joined
    assert "三类" in joined or "线下窗口" in joined


def test_and_eligibility_still_requires_all_slots() -> None:
    """AND path: skip one eligibility answer → no F10 confirm."""
    processor = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=ScriptedMapper([]))
    state = _turn(processor, "身份证丢了", None).state
    state = _turn(processor, "现场照片是本人", state).state
    state = _turn(processor, "相貌没有变化", state).state
    state = _turn(processor, "没有不良信用", state).state
    state = _turn(processor, "是，未满五年且有效", state).state
    state = _turn(processor, "有效期十年及以上", state).state
    node = state["artifacts"]["f09"]["business_transition"]["current_node_id"]
    assert node == "hukou_region"
    assert read_f10(state["artifacts"]).get("confirmed_business_id") in (None, "")


def test_field_photo_utterance_keeps_clarifying_photo_slot() -> None:
    mapper = ScriptedMapper(
        [
            AnswerMapperOutput(
                kind=MapperUtteranceKind.OTHER,
                mapped_value=None,
                confidence=None,
            )
        ]
    )
    processor = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=mapper)
    pending = _turn(processor, "身份证丢了", None).state
    assert (
        pending["artifacts"]["f09"]["business_transition"]["current_node_id"]
        == "submitted_photo_not_self"
    )
    again = _turn(processor, "我已经拍了现场正面照片", pending)
    f09 = again.state["artifacts"]["f09"]
    slot = f09.get("slot_context") or {}
    transition = f09.get("business_transition") or {}
    current = transition.get("current_node_id") or slot.get("current_node_id")
    assert current == "submitted_photo_not_self"
    assert "应当通过线下" not in again.response_text
    assert read_f10(again.state["artifacts"]).get("confirmed_business_id") in (None, "")


def test_handling_locations_cover_all_guide_stations() -> None:
    locs = _repo().get_handling_locations(_ID)
    names = {loc.name for loc in locs}
    expected = {
        "清波派出所",
        "湖滨派出所",
        "小营派出所",
        "南星派出所",
        "紫阳派出所",
        "望江派出所",
        "凯旋派出所",
        "采荷派出所",
        "闸弄口派出所",
        "四季青派出所",
        "彭埠派出所",
        "笕桥派出所",
        "丁兰派出所",
        "九堡派出所",
    }
    assert names == expected
    assert all(loc.address_status.value == "SOURCE_EXPLICIT" for loc in locs)
    guide = load_guide_document(_ID_GUIDE)
    locations = next(i for i in guide.knowledge_items if i.item_id == "ki-locations")
    assert locations.value.kind.value == "list"
    assert locations.value.items is not None
    joined = "\n".join(locations.value.items)
    assert "九堡派出所" in joined and "清波派出所" in joined
    assert "不是仅清波、湖滨两家" in joined


def test_first_turn_fee_consult_answers_without_binding_graph() -> None:
    result = _turn(
        _processor(ScriptedRetrieval([_cand(_ID)])),
        "补办身份证需要多少钱？",
    )
    assert "40元" in result.response_text
    assert result.state["artifacts"]["f12"]["knowledge_context_business_id"] == _ID
    assert result.state["artifacts"]["f12"].get("bound_business_id") in (None, "")
    assert result.state["artifacts"].get("f09") in (None, {})
    assert read_f10(result.state["artifacts"]).get("confirmed_business_id") in (None, "")
    assert "相貌" not in result.response_text


def test_lost_intent_does_not_repeat_handling_case() -> None:
    result = _turn(
        _processor(ScriptedRetrieval([_cand(_ID)])),
        "我的身份证丢了，想在网上补办。",
    )
    assert "丢失需要补领" in result.response_text
    assert "丢失需要补领，还是证件损坏" not in result.response_text
    node = result.state["artifacts"]["f09"]["business_transition"]["current_node_id"]
    assert node == "submitted_photo_not_self"


def test_guide_during_handling_keeps_progress() -> None:
    mapper = ScriptedMapper([])
    processor = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=mapper)
    pending = _turn(processor, "身份证丢了", None).state
    before = copy.deepcopy(pending["artifacts"]["f09"])
    answered = _turn(processor, "需要什么材料？", pending)
    assert "现场正面照片" in answered.response_text
    assert answered.state["artifacts"]["f09"] == before
    assert answered.state["artifacts"]["f12"]["bound_business_id"] == _ID


# ---------------------------------------------------------------------------
# F16-2 Multi-turn Fix — session-level coverage
# ---------------------------------------------------------------------------


def _slots(state) -> dict[str, str]:
    f09 = state["artifacts"].get("f09") or {}
    payload = f09.get("slot_context")
    if isinstance(payload, dict):
        current = payload.get("current_slots") or {}
        if isinstance(current, dict):
            return {k: v for k, v in current.items() if isinstance(k, str) and isinstance(v, str)}
    return {}


def _node(state) -> str | None:
    f09 = state["artifacts"].get("f09") or {}
    transition = f09.get("business_transition") or {}
    if isinstance(transition, dict):
        node = transition.get("current_node_id")
        if isinstance(node, str):
            return node
    return None


def _bound(state) -> str | None:
    f12 = state["artifacts"].get("f12") or {}
    bound = f12.get("bound_business_id")
    return bound if isinstance(bound, str) and bound.strip() else None


def _confirmed(state) -> str | None:
    value = read_f10(state["artifacts"]).get("confirmed_business_id")
    return value if isinstance(value, str) and value.strip() else None


def test_photo_not_self_eligibility_not_materials() -> None:
    """问题 A：资格事实 + 网上补办咨询 → 线下答复，非材料列表。"""
    result = _turn(
        _processor(ScriptedRetrieval([_cand(_ID)])),
        "我准备提交的现场照片不是我本人，可以网上补办身份证吗？",
    )
    assert "线下" in result.response_text
    assert "不是拒绝" in result.response_text
    assert "现场正面照片须" not in result.response_text
    assert "需要准备的材料" not in result.response_text
    assert "清波" not in result.response_text
    assert result.public_status.value == "COMPLETED"
    assert result.requires_user_input is False
    assert "等待您补充" not in result.response_text
    assert _confirmed(result.state) is None


def test_combined_photo_and_appearance_facts_skip_satisfied() -> None:
    """问题 B：一句话吸收两事实，跳过已满足条件。"""
    processor = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=ScriptedMapper([]))
    pending = _turn(processor, "身份证丢了要补办", None)
    assert _node(pending.state) == "submitted_photo_not_self"
    next_turn = _turn(
        processor,
        "我的现场正面照片已经拍好了，是我本人，相貌也没有明显变化。",
        pending.state,
    )
    slots = _slots(next_turn.state)
    assert slots.get("submitted_photo_not_self") == "no"
    assert slots.get("appearance_change_major") == "no"
    assert _node(next_turn.state) == "bad_credit_record"
    assert "是本人" not in next_turn.response_text or "不良" in next_turn.response_text
    assert "非申请人本人" not in next_turn.response_text
    assert _bound(next_turn.state) == _ID
    assert _confirmed(next_turn.state) is None


def test_photo_self_does_not_infer_appearance() -> None:
    graph = load_decision_graph(_ID_GRAPH)
    only_photo = deterministic_slot_candidates(
        "照片是本人",
        graph,
        business_id=_ID,
    )
    assert only_photo.get("submitted_photo_not_self") == "no"
    assert "appearance_change_major" not in only_photo
    only_appearance = deterministic_slot_candidates(
        "相貌没有明显变化",
        graph,
        business_id=_ID,
    )
    assert only_appearance.get("appearance_change_major") == "no"
    assert "submitted_photo_not_self" not in only_appearance
    not_self = deterministic_slot_candidates(
        "照片不是我本人",
        graph,
        business_id=_ID,
    )
    assert not_self.get("submitted_photo_not_self") == "yes"
    assert not_self.get("appearance_change_major") != "yes"
    ready_only = deterministic_slot_candidates(
        "现场正面照片已经拍好了",
        graph,
        business_id=_ID,
    )
    assert ready_only.get("submitted_photo_not_self") is None


def test_bad_credit_offline_divert() -> None:
    result = _turn(
        _processor(ScriptedRetrieval([_cand(_ID)])),
        "身份证丢了，有不良信用记录，可以网上办吗？",
    )
    assert "线下" in result.response_text
    assert result.public_status.value == "COMPLETED"
    assert result.requires_user_input is False
    assert _confirmed(result.state) is None


def test_fresh_session_photo_phrase_does_not_force_idcard_without_intent() -> None:
    """全新会话：纯照片短语不得错误绑定身份证业务。"""
    recognition = recognize_guide_utterance(
        "现场正面照片已经拍好了",
        pending_question_text=None,
        active_business_id=None,
    )
    # Without matter context, materials-like photo talk is OK; must not invent eligibility.
    assert recognition.kind is RecognitionKind.TOPIC
    assert recognition.topic == "materials"
    graph = load_decision_graph(_ID_GRAPH)
    slots = deterministic_slot_candidates(
        "现场正面照片已经拍好了",
        graph,
        business_id=_ID,
    )
    assert slots.get("handling_case") is None
    assert slots.get("submitted_photo_not_self") is None


def test_conflict_does_not_silently_overwrite() -> None:
    processor = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=ScriptedMapper([]))
    state = _turn(processor, "身份证丢了", None).state
    state = _turn(processor, "现场照片是本人", state).state
    assert _slots(state).get("submitted_photo_not_self") == "no"
    # Conflict on already-recorded photo fact while answering appearance.
    conflicted = _turn(processor, "照片不是我本人，相貌没有变化", state)
    assert "不一致" in conflicted.response_text
    assert _slots(conflicted.state).get("submitted_photo_not_self") == "no"
    assert _node(conflicted.state) == "appearance_change_major"
    assert _confirmed(conflicted.state) is None


def test_fee_interjection_does_not_advance_graph() -> None:
    processor = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=ScriptedMapper([]))
    pending = _turn(processor, "身份证丢了", None).state
    before_node = _node(pending)
    before_slots = _slots(pending)
    fee = _turn(processor, "补办需要多少钱？", pending)
    assert "40元" in fee.response_text
    assert _node(fee.state) == before_node
    assert _slots(fee.state) == before_slots
    assert _bound(fee.state) == _ID
    resumed = _turn(processor, "现场照片是本人", fee.state)
    assert _slots(resumed.state).get("submitted_photo_not_self") == "no"
    assert _node(resumed.state) == "appearance_change_major"


def test_materials_interjection_then_resume() -> None:
    processor = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=ScriptedMapper([]))
    pending = _turn(processor, "身份证丢了", None).state
    before = _node(pending)
    materials = _turn(processor, "需要准备什么材料？", pending)
    assert "现场正面照片" in materials.response_text
    assert _node(materials.state) == before
    resumed = _turn(processor, "是我本人", materials.state)
    assert _slots(resumed.state).get("submitted_photo_not_self") == "no"
    assert _node(resumed.state) == "appearance_change_major"


def test_deadline_interjection_keeps_matter() -> None:
    processor = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=ScriptedMapper([]))
    pending = _turn(processor, "身份证丢了", None).state
    deadline = _turn(processor, "多久可以办好？", pending)
    assert "10工作日" in deadline.response_text or "工作日" in deadline.response_text
    assert _bound(deadline.state) == _ID
    assert _node(deadline.state) == _node(pending)


def test_offline_then_ask_locations_lists_all_stations() -> None:
    processor = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=ScriptedMapper([]))
    offline = _turn(
        processor,
        "我的身份证损坏了，而且相貌变化比较大，可以网上补办吗？",
        None,
    )
    assert offline.public_status.value == "COMPLETED"
    assert "清波" not in offline.response_text
    locations = _turn(processor, "办理地点在哪里？", offline.state)
    assert "清波派出所" in locations.response_text
    assert "九堡派出所" in locations.response_text
    assert locations.response_text.count("派出所") >= 14
    assert _confirmed(locations.state) is None


def test_full_idcard_online_path_to_f10_f13() -> None:
    mapper = ScriptedMapper([])
    base = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=mapper)
    preview = ConfirmedBusinessMaterialsPreviewProcessor(
        base_processor=base,
        business_repository=_repo(),
    )
    turns: list[tuple[str, object]] = []
    result = _turn(base, "我的身份证丢了，想网上补办", None)
    turns.append(("start", result))
    assert _bound(result.state) == _ID
    assert _node(result.state) == "submitted_photo_not_self"
    assert _confirmed(result.state) is None

    result = _turn(base, "是我本人，相貌没有明显变化", result.state)
    turns.append(("photo+appearance", result))
    assert _slots(result.state).get("submitted_photo_not_self") == "no"
    assert _slots(result.state).get("appearance_change_major") == "no"
    assert _node(result.state) == "bad_credit_record"

    result = _turn(base, "没有不良信用", result.state)
    turns.append(("credit", result))
    assert _node(result.state) == "biometric_info_status"

    result = _turn(base, "采集未满五年且信息有效", result.state)
    turns.append(("bio", result))
    assert _node(result.state) == "id_validity_band"

    result = _turn(base, "有效期十年及以上", result.state)
    turns.append(("validity", result))
    assert _node(result.state) == "hukou_region"

    result = _turn(base, "户口在浙江", result.state)
    turns.append(("hukou→F10", result))
    assert result.state["artifacts"]["f09"]["business_transition"]["status"] == (
        "TERMINAL_CANDIDATE"
    )
    assert _confirmed(result.state) is None
    assert "确认" in result.response_text

    confirmed = _turn(preview, "确认", result.state)
    turns.append(("F13", confirmed))
    assert _confirmed(confirmed.state) == _ID
    assert confirmed.response_text.count("需要准备的材料") == 1
    assert "现场正面照片" in confirmed.response_text
    assert confirmed.state["artifacts"]["f12"]["bound_business_id"] == _ID
    assert len(turns) == 7


def test_ss_multi_turn_not_regressed() -> None:
    retrieval = ScriptedRetrieval([_cand(_SS)])
    registry = _registry()
    repository = _repo()
    graph = registry.require_graph(_SS)
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
        first_turn_extractor=DeterministicExtractor(),
        load_default_guide=False,
    )
    first = _turn(processor, "我想自己交社保", None)
    assert _bound(first.state) == _SS
    assert "就业" in first.response_text or "灵活" in first.response_text
    assert _confirmed(first.state) is None


def test_two_matters_knowledge_isolation_in_session() -> None:
    id_proc = _processor(ScriptedRetrieval([_cand(_ID)]))
    id_turn = _turn(id_proc, "补办身份证要多少钱？")
    assert "40元" in id_turn.response_text
    assert "现场正面照片" not in id_turn.response_text or "材料" not in id_turn.response_text

    ss_retrieval = ScriptedRetrieval([_cand(_SS)])
    registry = _registry()
    repository = _repo()
    graph = registry.require_graph(_SS)
    docs = {
        _SS: load_guide_document(_DEMO_GUIDE),
        _ID: load_guide_document(_ID_GUIDE),
    }
    guide = GuideQueryHandler(
        decision_graph=graph,
        knowledge_service=GovernmentKnowledgeService(
            docs,
            business_repository=repository,
        ),
        matter_registry=registry,
    )
    ss_proc = GovernmentAgentTurnProcessor(
        decision_graph=graph,
        matter_registry=registry,
        business_repository=repository,
        retrieval_service=ss_retrieval,  # type: ignore[arg-type]
        slot_dependencies=SlotInteractionDependencies(
            answer_mapper=ScriptedMapper([]),
            explanation_service=ScriptedExplanation(),
            decision_graph=graph,
            business_repository=repository,
        ),
        terminal_dependencies=TerminalConfirmationDependencies(
            business_repository=repository,
        ),
        guide_handler=guide,
        first_turn_extractor=DeterministicExtractor(),
        load_default_guide=False,
    )
    ss_turn = _turn(ss_proc, "交社保需要什么材料？")
    assert "现场正面照片" not in ss_turn.response_text


# ---------------------------------------------------------------------------
# F16-2 Session-Fix — SessionService + checkpoint persistence
# ---------------------------------------------------------------------------


def _session_service(
    *,
    store=None,
    mapper: ScriptedMapper | None = None,
    business_id: str = _ID,
):
    from tests.test_f12_session_integration import MemoryStore

    retrieval = ScriptedRetrieval([_cand(business_id)])
    processor = _processor(retrieval, mapper=mapper or ScriptedMapper([]))
    mem = store if store is not None else MemoryStore()
    service = SessionTurnService(
        store=mem,  # type: ignore[arg-type]
        processor=processor,
        max_input_chars=4000,
        session_ttl_seconds=3600,
    )
    return service, mem, processor


def _sturn(service: SessionTurnService, text: str, session_id: str | None = None):
    return service.handle_turn(
        SessionTurnRequest(
            request_id=str(uuid.uuid4()),
            session_id=session_id,
            input_text=text,
        )
    )


def _snap(service_result, store, session_id: str) -> dict:
    checkpoint = store.sessions[session_id][1]
    state = checkpoint.state
    f09 = state.artifacts.get("f09") or {}
    f12 = state.artifacts.get("f12") or {}
    tr = f09.get("business_transition") or {}
    sc = f09.get("slot_context") or {}
    return {
        "node_id": tr.get("current_node_id"),
        "pending_slot": tr.get("required_slot") or sc.get("required_slot"),
        "slots": dict(sc.get("current_slots") or {}),
        "bound_business_id": f12.get("bound_business_id"),
        "bound_graph_id": f12.get("bound_graph_id"),
        "knowledge_context_business_id": f12.get("knowledge_context_business_id"),
        "confirmed_business_id": read_f10(state.artifacts).get("confirmed_business_id"),
        "status": service_result.status.value
        if hasattr(service_result.status, "value")
        else str(service_result.status),
        "requires_user_input": service_result.requires_user_input,
        "response_text": service_result.response_text,
    }


def test_session_fix_new_vs_bound_photo_not_self() -> None:
    """A/B: 新会话与已绑定会话对「照片不是本人」均应线下分流。"""
    # A — fresh session, fact + online ask
    svc_a, store_a, _ = _session_service()
    a1 = _sturn(
        svc_a,
        "我准备提交的现场照片不是本人，可以网上补办身份证吗？",
    )
    sa = _snap(a1, store_a, a1.session_id)
    assert "线下" in a1.response_text
    assert a1.requires_user_input is False
    assert sa["status"] == "COMPLETED"
    assert sa["confirmed_business_id"] in (None, "")
    assert "清波" not in a1.response_text

    # B — bound session after fees/materials/resume
    svc_b, store_b, _ = _session_service()
    b1 = _sturn(svc_b, "我的身份证丢了，想在网上补办。")
    sid = b1.session_id
    s1 = _snap(b1, store_b, sid)
    assert s1["bound_business_id"] == _ID
    assert s1["bound_graph_id"] == "idcard_replace_lt5y"
    assert s1["pending_slot"] == "submitted_photo_not_self"
    assert "是您本人吗" in b1.response_text

    b2 = _sturn(svc_b, "补办身份证需要多少钱？", sid)
    s2 = _snap(b2, store_b, sid)
    assert "40元" in b2.response_text
    assert s2["node_id"] == s1["node_id"]
    assert s2["pending_slot"] == "submitted_photo_not_self"
    assert s2["bound_business_id"] == _ID

    b3 = _sturn(svc_b, "需要准备什么材料？", sid)
    s3 = _snap(b3, store_b, sid)
    assert "现场正面照片" in b3.response_text
    assert s3["pending_slot"] == "submitted_photo_not_self"

    b4 = _sturn(svc_b, "继续刚才的办理。", sid)
    s4 = _snap(b4, store_b, sid)
    assert "是您本人吗" in b4.response_text
    assert "我还不能确定您的意思" not in b4.response_text
    assert s4["pending_slot"] == "submitted_photo_not_self"
    assert s4["bound_business_id"] == _ID

    b5 = _sturn(
        svc_b,
        "我准备提交的现场照片不是本人，可以网上补办身份证吗？",
        sid,
    )
    s5 = _snap(b5, store_b, sid)
    assert "线下" in b5.response_text
    assert b5.requires_user_input is False
    assert s5["status"] == "COMPLETED"
    assert s5["confirmed_business_id"] in (None, "")
    assert "等待您补充" not in b5.response_text


def test_session_fix_bound_short_answers_and_multi_fact() -> None:
    """C/D/E: 不是本人 / 是本人 / 多事实。"""
    svc, store, _ = _session_service()
    first = _sturn(svc, "我的身份证丢了，想在网上补办。")
    sid = first.session_id

    # Parallel session: short “不是本人”
    svc2, store2, _ = _session_service()
    p1 = _sturn(svc2, "我的身份证丢了，想在网上补办。")
    p2 = _sturn(svc2, "不是本人。", p1.session_id)
    sp = _snap(p2, store2, p1.session_id)
    assert "线下" in p2.response_text
    assert p2.requires_user_input is False
    assert sp["status"] == "COMPLETED"

    # D — 是本人 advances to appearance
    d2 = _sturn(svc, "是本人。", sid)
    sd = _snap(d2, store, sid)
    assert sd["pending_slot"] == "appearance_change_major"
    assert sd["slots"].get("submitted_photo_not_self") == "no"
    assert "线下" not in d2.response_text

    # Fresh for multi-fact E
    svc3, store3, _ = _session_service()
    e1 = _sturn(svc3, "身份证丢了要补办")
    e2 = _sturn(
        svc3,
        "现场照片是我本人，相貌也没有明显变化。",
        e1.session_id,
    )
    se = _snap(e2, store3, e1.session_id)
    assert se["slots"].get("submitted_photo_not_self") == "no"
    assert se["slots"].get("appearance_change_major") == "no"
    assert se["pending_slot"] == "bad_credit_record"


def test_session_fix_guide_interjections_and_resume() -> None:
    """F/G/H/I/J: Guide 插话不推进；继续办理恢复；再答推进。"""
    svc, store, _ = _session_service()
    t1 = _sturn(svc, "身份证丢了，想补办")
    sid = t1.session_id
    before = _snap(t1, store, sid)
    assert before["pending_slot"] == "submitted_photo_not_self"

    fee = _sturn(svc, "补办需要多少钱？", sid)
    assert "40元" in fee.response_text
    assert _snap(fee, store, sid)["pending_slot"] == before["pending_slot"]

    mat = _sturn(svc, "需要准备什么材料？", sid)
    assert "现场正面照片" in mat.response_text
    assert _snap(mat, store, sid)["node_id"] == before["node_id"]

    deadline = _sturn(svc, "多久可以办好？", sid)
    assert "工作日" in deadline.response_text
    assert _snap(deadline, store, sid)["bound_graph_id"] == "idcard_replace_lt5y"

    resume = _sturn(svc, "继续刚才的办理", sid)
    assert "是您本人吗" in resume.response_text
    assert "我还不能确定" not in resume.response_text
    assert _snap(resume, store, sid)["pending_slot"] == "submitted_photo_not_self"

    again = _sturn(svc, "刚才问到哪里了", sid)
    assert "是您本人吗" in again.response_text

    advanced = _sturn(svc, "是我自己的照片", sid)
    sa = _snap(advanced, store, sid)
    assert sa["slots"].get("submitted_photo_not_self") == "no"
    assert sa["pending_slot"] == "appearance_change_major"


def test_session_fix_redis_checkpoint_continue() -> None:
    """K: Redis 写入后再读继续回答。"""
    client = Redis(host="127.0.0.1", port=6379, decode_responses=True)
    try:
        client.ping()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Redis 6379 unavailable: {exc}")
    prefix = f"govagent:f16fix:{uuid.uuid4().hex[:8]}"
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
    processor = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=ScriptedMapper([]))
    service = SessionTurnService(
        store=store,
        processor=processor,
        max_input_chars=4000,
        session_ttl_seconds=120,
    )
    try:
        first = service.handle_turn(
            SessionTurnRequest(
                request_id=str(uuid.uuid4()),
                session_id=None,
                input_text="身份证丢了要补办",
            )
        )
        fee = service.handle_turn(
            SessionTurnRequest(
                request_id=str(uuid.uuid4()),
                session_id=first.session_id,
                input_text="补办需要多少钱？",
            )
        )
        assert "40元" in fee.response_text
        _meta, checkpoint = store.load_active_session(
            first.session_id,
            now=datetime.now(timezone.utc),
        )
        f09 = checkpoint.state.artifacts["f09"]
        assert f09["business_transition"]["required_slot"] == "submitted_photo_not_self"
        assert checkpoint.state.artifacts["f12"]["bound_business_id"] == _ID

        # New service instance, same Redis store — simulate process restart.
        service2 = SessionTurnService(
            store=store,
            processor=_processor(
                ScriptedRetrieval([_cand(_ID)]),
                mapper=ScriptedMapper([]),
            ),
            max_input_chars=4000,
            session_ttl_seconds=120,
        )
        resumed = service2.handle_turn(
            SessionTurnRequest(
                request_id=str(uuid.uuid4()),
                session_id=first.session_id,
                input_text="继续刚才的办理",
            )
        )
        assert "是您本人吗" in resumed.response_text
        answered = service2.handle_turn(
            SessionTurnRequest(
                request_id=str(uuid.uuid4()),
                session_id=first.session_id,
                input_text="不是本人",
            )
        )
        assert "线下" in answered.response_text
        assert answered.requires_user_input is False
    finally:
        for key in client.scan_iter(match=f"{prefix}*"):
            client.delete(key)


def test_session_fix_full_and_path_f10_f13() -> None:
    """L/M: AND 条件走完 → F10 → F13 一次。"""
    from tests.test_f12_session_integration import MemoryStore

    mapper = ScriptedMapper([])
    base = _processor(ScriptedRetrieval([_cand(_ID)]), mapper=mapper)
    preview = ConfirmedBusinessMaterialsPreviewProcessor(
        base_processor=base,
        business_repository=_repo(),
    )
    store = MemoryStore()
    service = SessionTurnService(
        store=store,  # type: ignore[arg-type]
        processor=preview,
        max_input_chars=4000,
        session_ttl_seconds=3600,
    )
    texts = [
        "我的身份证丢了，想网上补办",
        "是我本人，相貌没有明显变化",
        "没有不良信用",
        "采集未满五年且信息有效",
        "有效期十年及以上",
        "户口在浙江",
        "确认",
    ]
    session_id = None
    last = None
    for text in texts:
        last = _sturn(service, text, session_id)
        session_id = last.session_id
    assert last is not None
    snap = _snap(last, store, session_id)
    assert snap["confirmed_business_id"] == _ID
    assert last.response_text.count("需要准备的材料") == 1
    again = _sturn(service, "还需要什么材料？", session_id)
    assert again.response_text.count("需要准备的材料") == 0


def test_session_fix_ss_multi_turn_regression() -> None:
    """O: 社保多轮不回退。"""
    from tests.test_f12_session_integration import MemoryStore

    registry = _registry()
    repository = _repo()
    graph = registry.require_graph(_SS)
    docs = {
        _SS: load_guide_document(_DEMO_GUIDE),
        _ID: load_guide_document(_ID_GUIDE),
    }
    guide = GuideQueryHandler(
        decision_graph=graph,
        knowledge_service=GovernmentKnowledgeService(
            docs,
            business_repository=repository,
        ),
        matter_registry=registry,
    )
    processor = GovernmentAgentTurnProcessor(
        decision_graph=graph,
        matter_registry=registry,
        business_repository=repository,
        retrieval_service=ScriptedRetrieval([_cand(_SS)]),  # type: ignore[arg-type]
        slot_dependencies=SlotInteractionDependencies(
            answer_mapper=ScriptedMapper([]),
            explanation_service=ScriptedExplanation(),
            decision_graph=graph,
            business_repository=repository,
        ),
        terminal_dependencies=TerminalConfirmationDependencies(
            business_repository=repository,
        ),
        guide_handler=guide,
        first_turn_extractor=DeterministicExtractor(),
        load_default_guide=False,
    )
    store = MemoryStore()
    service = SessionTurnService(
        store=store,  # type: ignore[arg-type]
        processor=processor,
        max_input_chars=4000,
        session_ttl_seconds=3600,
    )
    first = _sturn(service, "我想自己交社保")
    snap = _snap(first, store, first.session_id)
    assert snap["bound_business_id"] == _SS
    assert snap["bound_graph_id"] == "social_security"
    assert snap["confirmed_business_id"] in (None, "")
    fee = _sturn(service, "交社保要多少钱？", first.session_id)
    assert _snap(fee, store, first.session_id)["bound_business_id"] == _SS
    assert _snap(fee, store, first.session_id)["pending_slot"] == snap["pending_slot"]


def test_photo_polarity_phrases_and_positive_question() -> None:
    graph = load_decision_graph(_ID_GRAPH)
    node = next(n for n in graph.nodes if n.node_id == "submitted_photo_not_self")
    assert node.question_text == "您准备提交的现场正面照片是您本人吗？"
    assert "是不是非申请人" not in (node.question_text or "")
    cases = [
        ("是本人", "no"),
        ("是我自己的照片", "no"),
        ("照片就是我本人", "no"),
        ("不是本人", "yes"),
        ("不是我的照片", "yes"),
        ("照片是别人的", "yes"),
        ("没拍", None),
        ("不确定", None),
    ]
    for text, expected in cases:
        got = deterministic_slot_candidates(text, graph, business_id=_ID).get(
            "submitted_photo_not_self"
        )
        assert got == expected, (text, got, expected)
