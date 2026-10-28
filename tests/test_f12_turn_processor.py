"""F12 GovernmentAgentTurnProcessor tests against the real Demo graph."""

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
from gov_service_agent.agent.state import AgentState
from gov_service_agent.agent.terminal import ConfirmationStatus, read_f10
from gov_service_agent.agent.turn_processor import GovernmentAgentTurnProcessor
from gov_service_agent.agent.workflow import (
    SlotInteractionDependencies,
    TerminalConfirmationDependencies,
)
from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.business_graph.loader import load_decision_graph
from gov_service_agent.business_graph.transition import TransitionStatus
from gov_service_agent.retrieval.types import (
    RetrievalCandidate,
    RetrievalResult,
    RetrievalStatus,
)
from gov_service_agent.session.models import SessionTurnPublicStatus

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GRAPH_PATH = _REPO_ROOT / "data" / "graphs" / "demo" / "social_security.json"
_BUSINESS_PATH = _REPO_ROOT / "data" / "demo" / "demo_ss_001.json"
_INITIAL = "我辞职了，现在没单位，想自己交社保"
_SERVICE_QUESTION = "您主要想办理社保缴费、社保转移，还是查询或其他业务？"
_PAYMENT_QUESTION = "这次社保缴费主要是单位缴，还是您自己缴？"
_EMPLOYMENT_QUESTION = (
    "您属于哪种灵活就业情况？例如个体户、未在单位参保的非全日制人员，或其他灵活就业人员。"
)
_NO_DIRECTION = "暂时无法确定您要办理的业务方向，请补充说明后重试。"
_SAFE_HOLD = "当前办理路径暂时无法继续，请换一种需求说明或开启新的会话。"
_UNSUPPORTED_REASON = "社会保险关系转移接续暂无正式办事指南数据"


class FakeRetrieval:
    def __init__(self, result: RetrievalResult) -> None:
        self._result = result
        self.queries: list[str | None] = []

    def retrieve(self, query: str | None) -> RetrievalResult:
        self.queries.append(query)
        return self._result


class ScriptedMapper:
    def __init__(self, outputs: list[AnswerMapperOutput | Exception]) -> None:
        self._outputs = list(outputs)
        self.requests: list[AnswerMappingRequest] = []

    def map_answer(self, request: AnswerMappingRequest) -> AnswerMapperOutput:
        self.requests.append(request)
        item = self._outputs.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class ScriptedExplanation:
    def __init__(self, text: str = "灵活就业是一种就业形式的说明") -> None:
        self.calls = 0
        self._text = text

    def explain(self, request: ExplanationRequest) -> ExplanationResult:
        self.calls += 1
        return ExplanationResult(
            status=ExplanationStatus.ANSWERED,
            topic=request.topic,
            text=self._text,
        )


def _candidate(business_id: str = "DEMO_SS_001") -> RetrievalCandidate:
    return RetrievalCandidate(
        business_id=business_id,
        display_name="demo",
        score=0.91,
        rank=1,
        direction="social_security",
        eligibility_scope="ONLINE",
    )


def _candidates_result(
    business_id: str = "DEMO_SS_001",
) -> RetrievalResult:
    return RetrievalResult(
        status=RetrievalStatus.CANDIDATES,
        query=_INITIAL,
        candidates=[_candidate(business_id)],
    )


def _status_result(status: RetrievalStatus) -> RetrievalResult:
    return RetrievalResult(status=status, query=_INITIAL, candidates=[])


def _slot_answer(value: str, confidence: float = 0.95) -> AnswerMapperOutput:
    return AnswerMapperOutput(
        kind=MapperUtteranceKind.SLOT_ANSWER,
        mapped_value=value,
        confidence=confidence,
    )


def _build(
    retrieval: FakeRetrieval,
    mapper: ScriptedMapper | None = None,
    explanation: ScriptedExplanation | None = None,
) -> GovernmentAgentTurnProcessor:
    graph = load_decision_graph(_GRAPH_PATH)
    repository = JsonBusinessRepository.from_paths([_BUSINESS_PATH])
    return GovernmentAgentTurnProcessor(
        decision_graph=graph,
        business_repository=repository,
        retrieval_service=retrieval,  # type: ignore[arg-type]
        slot_dependencies=SlotInteractionDependencies(
            answer_mapper=mapper or ScriptedMapper([]),
            explanation_service=explanation or ScriptedExplanation(),
            decision_graph=graph,
            business_repository=repository,
        ),
        terminal_dependencies=TerminalConfirmationDependencies(
            business_repository=repository,
        ),
    )


def _turn(
    processor: GovernmentAgentTurnProcessor,
    text: str,
    restored: AgentState | None,
) -> object:
    return processor.process_turn(
        session_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        input_text=text,
        restored_state=restored,
    )


def _f09(state: AgentState) -> dict:
    value = state["artifacts"]["f09"]
    assert isinstance(value, dict)
    return value


def _pending_service_action(
    processor: GovernmentAgentTurnProcessor,
    retrieval: FakeRetrieval,
) -> AgentState:
    result = _turn(processor, _INITIAL, None)
    assert retrieval.queries == [_INITIAL]
    assert result.public_status is SessionTurnPublicStatus.AWAITING_USER_INPUT
    return result.state


def test_confirmed_state_short_circuits_all_processing(monkeypatch: pytest.MonkeyPatch) -> None:
    retrieval = FakeRetrieval(_candidates_result())
    mapper = ScriptedMapper(
        [
            _slot_answer("payment"),
            _slot_answer("self_payment"),
            _slot_answer("self_employed_without_employees"),
        ]
    )
    processor = _build(retrieval, mapper)
    state: AgentState | None = None
    for text in (_INITIAL, "缴费", "自己缴", "无雇工的个体工商户", "确认"):
        result = _turn(processor, text, state)
        state = result.state
    assert read_f10(state["artifacts"])["confirmed_business_id"] == "DEMO_SS_001"
    retrieval_before = len(retrieval.queries)
    mapper_before = len(mapper.requests)
    resolve_calls = {"n": 0}
    import gov_service_agent.agent.turn_processor as turn_module

    real_resolve = turn_module.resolve_terminal_confirmation

    def _spy_resolve(*args, **kwargs):  # type: ignore[no-untyped-def]
        resolve_calls["n"] += 1
        return real_resolve(*args, **kwargs)

    monkeypatch.setattr(turn_module, "resolve_terminal_confirmation", _spy_resolve)
    again = _turn(processor, "还想问材料", state)
    assert again.public_status is SessionTurnPublicStatus.COMPLETED
    assert again.requires_user_input is False
    assert "身份证" in again.response_text
    assert read_f10(again.state["artifacts"])["confirmed_business_id"] == "DEMO_SS_001"
    assert len(retrieval.queries) == retrieval_before
    assert len(mapper.requests) == mapper_before
    assert resolve_calls["n"] == 0


def test_restored_state_is_not_mutated() -> None:
    retrieval = FakeRetrieval(_candidates_result())
    mapper = ScriptedMapper([_slot_answer("payment")])
    processor = _build(retrieval, mapper)
    pending = _pending_service_action(processor, retrieval)
    before = copy.deepcopy(pending)
    result = _turn(processor, "我想缴费", pending)
    assert pending == before
    assert result.state is not pending
    assert result.state["input_text"] == "我想缴费"
    assert result.state["request_id"] != pending["request_id"]
    assert pending["artifacts"] == before["artifacts"]
    assert pending["orchestration_trace"] == before["orchestration_trace"]
    assert pending["error"] == before["error"]


def test_initial_routing_enters_graph_but_does_not_confirm() -> None:
    retrieval = FakeRetrieval(_candidates_result())
    mapper = ScriptedMapper([])
    processor = _build(retrieval, mapper)
    result = _turn(processor, _INITIAL, None)
    f09 = _f09(result.state)
    transition = f09["business_transition"]
    assert retrieval.queries == [_INITIAL]
    assert result.public_status is SessionTurnPublicStatus.AWAITING_USER_INPUT
    assert result.requires_user_input is True
    assert result.response_text == _SERVICE_QUESTION
    assert transition["status"] == TransitionStatus.NEED_SLOT.value
    assert transition["required_slot"] == "service_action"
    assert transition["current_node_id"] == "social_security_action"
    assert transition["candidate_business_id"] is None
    assert "f10" not in result.state["artifacts"]
    assert len(mapper.requests) == 0
    direction = result.state["artifacts"]["f12"]
    assert direction["matched_business_id"] == "DEMO_SS_001"
    assert "query" not in direction


def test_unmatched_candidate_does_not_enter_graph() -> None:
    retrieval = FakeRetrieval(_candidates_result("NOT_ON_GRAPH"))
    processor = _build(retrieval, ScriptedMapper([]))
    result = _turn(processor, _INITIAL, None)
    assert result.response_text == _NO_DIRECTION
    assert result.requires_user_input is True
    assert result.public_status is SessionTurnPublicStatus.AWAITING_USER_INPUT
    assert result.state["artifacts"] == {}
    assert len(retrieval.queries) == 1


@pytest.mark.parametrize(
    "status",
    [RetrievalStatus.NO_USABLE_CANDIDATE, RetrievalStatus.INVALID_QUERY],
)
def test_non_candidate_retrieval_returns_clarification_without_graph(
    status: RetrievalStatus,
) -> None:
    retrieval = FakeRetrieval(_status_result(status))
    mapper = ScriptedMapper([])
    processor = _build(retrieval, mapper)
    result = _turn(processor, _INITIAL, None)
    assert result.response_text == _NO_DIRECTION
    assert result.requires_user_input is True
    assert result.state["artifacts"] == {}
    assert retrieval.queries == [_INITIAL]
    assert mapper.requests == []


@pytest.mark.parametrize(
    "status",
    [RetrievalStatus.UNAVAILABLE, RetrievalStatus.NOT_READY],
)
def test_required_retrieval_failure_propagates(status: RetrievalStatus) -> None:
    retrieval = FakeRetrieval(_status_result(status))
    processor = _build(retrieval, ScriptedMapper([]))
    with pytest.raises(RuntimeError, match="required semantic retrieval failed"):
        _turn(processor, _INITIAL, None)
    assert retrieval.queries == [_INITIAL]


def test_pending_slot_reuses_f09_and_advances_one_graph_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retrieval = FakeRetrieval(_candidates_result())
    mapper = ScriptedMapper([_slot_answer("payment")])
    processor = _build(retrieval, mapper)
    pending = _pending_service_action(processor, retrieval)
    import gov_service_agent.agent.turn_processor as turn_mod

    calls = {"n": 0}
    real = turn_mod.advance_until_blocked

    def _spy(graph, node_id, slots):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return real(graph, node_id, slots)

    monkeypatch.setattr(turn_mod, "advance_until_blocked", _spy)
    # Explicit DEMO phrase is absorbed deterministically (no mapper).
    result = _turn(processor, "社保缴费", pending)
    f09 = _f09(result.state)
    assert len(retrieval.queries) == 1
    assert len(mapper.requests) == 0
    assert calls["n"] == 1
    assert f09["business_transition"]["current_node_id"] == "payment_actor"
    assert f09["business_transition"]["required_slot"] == "payment_actor"
    assert f09["slot_context"]["current_node_id"] == "payment_actor"
    assert f09["slot_context"]["current_slots"] == {"service_action": "payment"}
    assert result.response_text == _PAYMENT_QUESTION
    assert f09["business_transition"]["candidate_business_id"] is None


def test_explanation_side_route_keeps_pending_employment_type() -> None:
    retrieval = FakeRetrieval(_candidates_result())
    mapper = ScriptedMapper(
        [_slot_answer("payment"), _slot_answer("self_payment")]
    )
    explanation = ScriptedExplanation()
    processor = _build(retrieval, mapper, explanation)
    state = _pending_service_action(processor, retrieval)
    state = _turn(processor, "缴费", state).state
    state = _turn(processor, "自己缴", state).state
    assert _f09(state)["slot_context"]["required_slot"] == "employment_type"
    mapper_before = len(mapper.requests)
    result = _turn(processor, "什么叫灵活就业？", state)
    f09 = _f09(result.state)
    assert explanation.calls == 1
    assert len(mapper.requests) == mapper_before
    assert len(retrieval.queries) == 1
    assert "灵活就业是一种就业形式的说明" in result.response_text
    assert _EMPLOYMENT_QUESTION in result.response_text
    assert f09["interpretation"]["kind"] == "explanation_request"
    assert f09["validated_slot"] is None
    assert f09["business_transition"] is None
    assert f09["slot_context"]["required_slot"] == "employment_type"
    assert f09["slot_context"]["current_node_id"] == "employment_type"
    assert f09["slot_context"]["question_text"] == _EMPLOYMENT_QUESTION
    assert "employment_type" not in f09["slot_context"]["current_slots"]
    assert "f10" not in result.state["artifacts"]
    assert result.requires_user_input is True


def test_low_confidence_does_not_advance_graph() -> None:
    retrieval = FakeRetrieval(_candidates_result())
    # payment / self_payment phrases are deterministic; only employment needs mapper.
    mapper = ScriptedMapper(
        [
            _slot_answer("other_flexible_employment", 0.75),
        ]
    )
    processor = _build(retrieval, mapper)
    state = _pending_service_action(processor, retrieval)
    state = _turn(processor, "缴费", state).state
    state = _turn(processor, "自己缴", state).state
    result = _turn(processor, "平时接零活，没有固定单位", state)
    f09 = _f09(result.state)
    assert f09["mapping_validation"]["status"] == "low_confidence"
    assert f09["interpretation"]["mapped_value"] == "other_flexible_employment"
    assert f09["interpretation"]["confidence"] == 0.75
    assert f09["validated_slot"] is None
    assert f09["business_transition"] is None
    assert f09["slot_context"]["required_slot"] == "employment_type"
    assert f09["slot_context"]["current_node_id"] == "employment_type"
    assert f09["slot_context"]["question_text"] == _EMPLOYMENT_QUESTION
    assert f09["slot_context"]["current_slots"] == {
        "service_action": "payment",
        "payment_actor": "self_payment",
    }
    assert "employment_type" not in f09["slot_context"]["current_slots"]
    assert _EMPLOYMENT_QUESTION in result.response_text
    assert len(mapper.requests) == 1
    assert len(retrieval.queries) == 1
    assert "f10" not in result.state["artifacts"]
    assert result.requires_user_input is True


def test_golden_flow_prepares_then_confirms_on_a_later_turn() -> None:
    retrieval = FakeRetrieval(_candidates_result())
    # Slot phrases are deterministic; mapper stays unused for this golden path.
    mapper = ScriptedMapper([])
    processor = _build(retrieval, mapper)
    first = _turn(processor, _INITIAL, None)
    assert first.requires_user_input is True
    assert _f09(first.state)["business_transition"]["required_slot"] == "service_action"
    assert "f10" not in first.state["artifacts"]

    second = _turn(processor, "我想缴费", first.state)
    assert _f09(second.state)["business_transition"]["required_slot"] == "payment_actor"

    third = _turn(processor, "自己缴", second.state)
    assert _f09(third.state)["business_transition"]["required_slot"] == "employment_type"
    assert _f09(third.state)["business_transition"]["candidate_business_id"] is None

    fourth = _turn(processor, "无雇工的个体工商户", third.state)
    f10 = read_f10(fourth.state["artifacts"])
    assert f10["mode"] == "prepare"
    assert f10["terminal_context"]["candidate_business_id"] == "DEMO_SS_001"
    assert f10["confirmed_business_id"] is None
    assert f10["confirmation"]["status"] == ConfirmationStatus.AWAITING_CONFIRMATION.value
    assert "灵活就业人员社会保险费申报缴费" in fourth.response_text
    assert fourth.public_status is SessionTurnPublicStatus.AWAITING_USER_INPUT
    assert fourth.requires_user_input is True
    assert len(retrieval.queries) == 1
    assert len(mapper.requests) == 0

    fifth = _turn(processor, "确认", fourth.state)
    confirmed = read_f10(fifth.state["artifacts"])
    assert confirmed["mode"] == "resolve"
    assert confirmed["confirmed_business_id"] == "DEMO_SS_001"
    assert confirmed["terminal_context"]["candidate_business_id"] == "DEMO_SS_001"
    assert fifth.public_status is SessionTurnPublicStatus.COMPLETED
    assert fifth.requires_user_input is False
    assert "已确认您要办理的事项" in fifth.response_text
    assert len(retrieval.queries) == 1
    assert len(mapper.requests) == 0


def test_terminal_confirmation_outranks_stale_slot_context() -> None:
    retrieval = FakeRetrieval(_candidates_result())
    mapper = ScriptedMapper(
        [
            _slot_answer("payment"),
            _slot_answer("self_payment"),
            _slot_answer("self_employed_without_employees"),
        ]
    )
    processor = _build(retrieval, mapper)
    state = None
    prepared = None
    for text in (_INITIAL, "缴费", "自己缴", "无雇工的个体工商户"):
        prepared = _turn(processor, text, state)
        state = prepared.state
    assert prepared is not None
    assert _f09(prepared.state)["slot_context"]["required_slot"] == "employment_type"
    mapper_before = len(mapper.requests)
    resolved = _turn(processor, "确认", prepared.state)
    assert len(mapper.requests) == mapper_before
    assert len(retrieval.queries) == 1
    assert read_f10(resolved.state["artifacts"])["confirmed_business_id"] == "DEMO_SS_001"


def test_rejection_keeps_candidate_and_does_not_retrieve_again() -> None:
    retrieval = FakeRetrieval(_candidates_result())
    mapper = ScriptedMapper(
        [
            _slot_answer("payment"),
            _slot_answer("self_payment"),
            _slot_answer("self_employed_without_employees"),
        ]
    )
    processor = _build(retrieval, mapper)
    state = None
    for text in (_INITIAL, "缴费", "自己缴", "无雇工的个体工商户"):
        state = _turn(processor, text, state).state
    rejected = _turn(processor, "不确认", state)
    f10 = read_f10(rejected.state["artifacts"])
    assert f10["confirmed_business_id"] is None
    assert f10["terminal_context"]["candidate_business_id"] == "DEMO_SS_001"
    assert f10["confirmation"]["status"] == ConfirmationStatus.REJECTED.value
    assert "已取消对当前候选事项" in rejected.response_text
    assert rejected.requires_user_input is True
    assert rejected.state["artifacts"]["f09"]["slot_context"] is not None
    assert len(retrieval.queries) == 1


def test_uncertain_confirmation_keeps_waiting() -> None:
    retrieval = FakeRetrieval(_candidates_result())
    mapper = ScriptedMapper(
        [
            _slot_answer("payment"),
            _slot_answer("self_payment"),
            _slot_answer("self_employed_without_employees"),
        ]
    )
    processor = _build(retrieval, mapper)
    state = None
    for text in (_INITIAL, "缴费", "自己缴", "无雇工的个体工商户"):
        state = _turn(processor, text, state).state
    uncertain = _turn(processor, "好像是吧", state)
    f10 = read_f10(uncertain.state["artifacts"])
    assert f10["confirmation"]["status"] == ConfirmationStatus.UNCERTAIN.value
    assert f10["confirmed_business_id"] is None
    assert f10["terminal_context"]["candidate_business_id"] == "DEMO_SS_001"
    assert uncertain.requires_user_input is True
    assert "请明确回复" in uncertain.response_text


@pytest.mark.parametrize(
    ("value", "expected_fragment"),
    [
        ("transfer", _UNSUPPORTED_REASON),
        ("inquiry", _SAFE_HOLD),
    ],
)
def test_fallback_and_unsupported_stay_without_retrieval(
    value: str,
    expected_fragment: str,
) -> None:
    retrieval = FakeRetrieval(_candidates_result())
    mapper = ScriptedMapper([_slot_answer(value)])
    processor = _build(retrieval, mapper)
    pending = _pending_service_action(processor, retrieval)
    held = _turn(processor, "其它方向", pending)
    transition = _f09(held.state)["business_transition"]
    assert transition["status"] in (
        TransitionStatus.FALLBACK.value,
        TransitionStatus.UNSUPPORTED.value,
    )
    assert transition["candidate_business_id"] is None
    assert "f10" not in held.state["artifacts"]
    assert expected_fragment in held.response_text
    # UNSUPPORTED ends the online path (no “等待补充”); FALLBACK still awaits.
    if transition["status"] == TransitionStatus.UNSUPPORTED.value:
        assert held.requires_user_input is False
        assert held.public_status is SessionTurnPublicStatus.COMPLETED
    else:
        assert held.requires_user_input is True
    assert len(retrieval.queries) == 1
    assert len(mapper.requests) == 1
    again = _turn(processor, "换个说法", held.state)
    assert len(retrieval.queries) == 1
    assert len(mapper.requests) == 1
    assert again.response_text == held.response_text


def test_mapper_exception_propagates_without_success_result() -> None:
    retrieval = FakeRetrieval(_candidates_result())
    mapper = ScriptedMapper([RuntimeError("controlled mapper failure")])
    processor = _build(retrieval, mapper)
    pending = _pending_service_action(processor, retrieval)
    # Avoid deterministic DEMO phrases so the mapper path is exercised.
    with pytest.raises(RuntimeError, match="controlled mapper failure"):
        _turn(processor, "就那个把钱交上的事儿", pending)
    assert len(mapper.requests) == 1
