"""F08 LangGraph workflow build/compile/invoke tests (local, deterministic)."""

from __future__ import annotations

import copy

import pytest

from gov_service_agent.agent import (
    AgentPhase,
    AgentStateValidationError,
    WorkflowStatus,
    build_agent_workflow,
    create_initial_state,
    run_agent_workflow,
)


def test_build_agent_workflow_compiles():
    compiled = build_agent_workflow()
    assert compiled is not None


def test_normal_workflow_result():
    initial = create_initial_state("req-001", "synthetic workflow input")
    final = run_agent_workflow(initial)
    assert final["phase"] is AgentPhase.COMPLETED
    assert final["status"] is WorkflowStatus.COMPLETED
    assert final["error"] is None
    assert final["orchestration_trace"] == ["prepare", "complete"]
    assert final["request_id"] == "req-001"
    assert final["input_text"] == "synthetic workflow input"
    assert set(final.keys()) == {
        "request_id",
        "input_text",
        "phase",
        "status",
        "artifacts",
        "error",
        "orchestration_trace",
    }
    assert "next_node" not in final
    assert "business_id" not in final
    assert "candidate_business_id" not in final
    assert "materials" not in final
    assert "rule_result" not in final


def test_artifacts_preserved():
    artifacts = {"source": "synthetic", "nested": {"value": 1}}
    initial = create_initial_state(
        "req-001",
        "synthetic workflow input",
        artifacts=artifacts,
    )
    final = run_agent_workflow(initial)
    assert final["artifacts"] == {"source": "synthetic", "nested": {"value": 1}}


def test_trace_exact_order_and_semantics():
    final = run_agent_workflow(
        create_initial_state("req-001", "synthetic workflow input")
    )
    assert final["orchestration_trace"] == ["prepare", "complete"]
    assert "START" not in final["orchestration_trace"]
    assert "END" not in final["orchestration_trace"]
    assert "validation" not in final["orchestration_trace"]


def test_workflow_determinism_independent_states():
    a = create_initial_state("req-001", "synthetic workflow input")
    b = create_initial_state("req-001", "synthetic workflow input")
    assert a is not b
    result_a = run_agent_workflow(a)
    result_b = run_agent_workflow(b)
    assert result_a == result_b


def test_repeated_invocation_isolation():
    first = run_agent_workflow(
        create_initial_state("req-001", "synthetic workflow input")
    )
    second = run_agent_workflow(
        create_initial_state("req-002", "synthetic workflow input two")
    )
    assert first["request_id"] == "req-001"
    assert second["request_id"] == "req-002"
    assert first["orchestration_trace"] == ["prepare", "complete"]
    assert second["orchestration_trace"] == ["prepare", "complete"]


def test_caller_initial_state_not_mutated():
    initial = create_initial_state(
        "req-001",
        "synthetic workflow input",
        artifacts={"nested": {"items": [1, 2]}},
    )
    before = copy.deepcopy(initial)
    final = run_agent_workflow(initial)
    assert initial == before
    assert initial["phase"] is AgentPhase.RECEIVED
    assert final["phase"] is AgentPhase.COMPLETED
    assert initial["artifacts"]["nested"]["items"] == [1, 2]
    assert final is not initial


def test_invalid_initial_state_controlled_reject():
    initial = create_initial_state("req-001", "synthetic workflow input")
    before = copy.deepcopy(initial)
    bad = dict(initial)
    bad["phase"] = AgentPhase.COMPLETED
    bad["status"] = WorkflowStatus.RUNNING
    with pytest.raises(AgentStateValidationError):
        run_agent_workflow(bad)  # type: ignore[arg-type]
    assert initial == before


def test_invalid_extra_key_rejected_before_invoke():
    initial = create_initial_state("req-001", "synthetic workflow input")
    before = copy.deepcopy(initial)
    bad = dict(initial)
    bad["business_id"] = "FAKE_BUSINESS_ID"
    with pytest.raises(AgentStateValidationError):
        run_agent_workflow(bad)  # type: ignore[arg-type]
    assert initial == before


def test_no_auto_repair_plain_string_phase():
    initial = create_initial_state("req-001", "synthetic workflow input")
    bad = dict(initial)
    bad["phase"] = "received"
    with pytest.raises(AgentStateValidationError):
        run_agent_workflow(bad)  # type: ignore[arg-type]

# ---------------------------------------------------------------------------
# F09 specialized slot-interaction workflow tests
# ---------------------------------------------------------------------------

from pathlib import Path

from gov_service_agent.agent import (
    AnswerMapperOutput,
    ExplanationRequest,
    ExplanationResult,
    ExplanationStatus,
    InteractionFailureKind,
    LlmAnswerMapper,
    LlmExplanationService,
    MapperUtteranceKind,
    MappingPolicy,
    MappingValidationStatus,
    SlotInteractionContext,
    SlotInteractionDependencies,
    UtteranceKind,
    build_slot_interaction_context,
    build_slot_interaction_workflow,
    run_slot_interaction_workflow,
)
from gov_service_agent.agent.explanation import is_safe_explanation_text
from gov_service_agent.business_graph import load_decision_graph
from gov_service_agent.business_graph.transition import TransitionStatus as F04Status
from gov_service_agent.llm.types import (
    DataClassification,
    LlmErrorCode,
    LlmProviderError,
    LlmRequest,
    LlmResponse,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = REPO_ROOT / "data" / "graphs" / "demo" / "social_security.json"


class CapturingLlmProvider:
    def __init__(
        self,
        *,
        content: str = '{"explanation":"safe concept"}',
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


class FakeAnswerMapper:
    def __init__(self, output: AnswerMapperOutput | Exception) -> None:
        self.calls = 0
        self._output = output

    def map_answer(self, request):  # type: ignore[no-untyped-def]
        self.calls += 1
        if isinstance(self._output, Exception):
            raise self._output
        return self._output


class FakeExplanationService:
    def __init__(self, result: ExplanationResult | Exception) -> None:
        self.calls = 0
        self.requests: list[ExplanationRequest] = []
        self._result = result

    def explain(self, request: ExplanationRequest) -> ExplanationResult:
        self.calls += 1
        self.requests.append(request)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _service_action_context(**overrides):  # type: ignore[no-untyped-def]
    data = {
        "transition_status": F04Status.NEED_SLOT,
        "current_node_id": "social_security_action",
        "required_slot": "service_action",
        "allowed_values": ("payment", "transfer", "inquiry", "other"),
        "question_text": (
            "您主要想办理社保缴费、社保转移，还是查询或其他业务？"
        ),
        "invalid_value": None,
        "current_slots": {},
    }
    data.update(overrides)
    return SlotInteractionContext(**data)


def _deps(
    *,
    mapper: FakeAnswerMapper | None = None,
    explanation: FakeExplanationService | None = None,
    graph=None,  # type: ignore[no-untyped-def]
    policy: MappingPolicy | None = None,
) -> SlotInteractionDependencies:
    if mapper is None:
        mapper = FakeAnswerMapper(
            AnswerMapperOutput(
                kind=MapperUtteranceKind.OTHER,
                mapped_value=None,
                confidence=None,
            )
        )
    if explanation is None:
        explanation = FakeExplanationService(
            ExplanationResult(
                status=ExplanationStatus.ANSWERED,
                topic="社保转移",
                text="社保转移一般指保险关系转移接续。",
            )
        )
    if graph is None:
        graph = load_decision_graph(GRAPH_PATH)
    return SlotInteractionDependencies(
        answer_mapper=mapper,
        explanation_service=explanation,
        decision_graph=graph,
        mapping_policy=policy or MappingPolicy(),
    )


def test_f09_builder_compiles():
    compiled = build_slot_interaction_workflow(_deps())
    assert compiled is not None


def test_golden_explanation_workflow(monkeypatch: pytest.MonkeyPatch):
    mapper = FakeAnswerMapper(
        AnswerMapperOutput(
            kind=MapperUtteranceKind.SLOT_ANSWER,
            mapped_value="transfer",
            confidence=1.0,
        )
    )
    explanation = FakeExplanationService(
        ExplanationResult(
            status=ExplanationStatus.ANSWERED,
            topic="社保转移",
            text="社保转移一般指保险关系转移接续。",
        )
    )
    calls = {"f04": 0}
    real = __import__(
        "gov_service_agent.agent.nodes", fromlist=["advance_until_blocked"]
    ).advance_until_blocked

    def _spy(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["f04"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(
        "gov_service_agent.agent.nodes.advance_until_blocked",
        _spy,
    )
    question = "您主要想办理社保缴费、社保转移，还是查询或其他业务？"
    ctx = _service_action_context(question_text=question)
    initial = create_initial_state("req-exp-001", "什么是社保转移？")
    before_slots = dict(ctx.current_slots)
    final = run_slot_interaction_workflow(initial, ctx, _deps(mapper=mapper, explanation=explanation))
    f09 = final["artifacts"]["f09"]
    assert final["phase"] is AgentPhase.COMPLETED
    assert mapper.calls == 0
    assert explanation.calls == 1
    assert calls["f04"] == 0
    assert f09["interpretation"]["kind"] == UtteranceKind.EXPLANATION_REQUEST.value
    assert f09["validated_slot"] is None
    assert f09["business_transition"] is None
    assert f09["slot_context"]["current_node_id"] == "social_security_action"
    assert "社保转移一般指" in f09["response_text"]
    assert f09["response_text"].endswith(question)
    assert ctx.current_slots == before_slots
    assert "confirmed_business_id" not in f09
    assert "confirmed_business_id" not in final


def test_golden_explanation_remote_payload_minimization():
    provider = CapturingLlmProvider(
        content='{"explanation":"社保转移是公共概念说明。"}'
    )
    question = (
        "您主要想办理社保缴费、社保转移，还是查询或其他业务？"
        " QUESTION_TEXT_LOCAL_ONLY_SENTINEL"
    )
    raw = "什么是社保转移？"
    ctx = _service_action_context(question_text=question)
    deps = SlotInteractionDependencies(
        answer_mapper=FakeAnswerMapper(
            AnswerMapperOutput(
                kind=MapperUtteranceKind.OTHER,
                mapped_value=None,
                confidence=None,
            )
        ),
        explanation_service=LlmExplanationService(provider),
        decision_graph=load_decision_graph(GRAPH_PATH),
        mapping_policy=MappingPolicy(),
    )
    final = run_slot_interaction_workflow(
        create_initial_state("req-exp-cap", raw),
        ctx,
        deps,
    )
    assert final["artifacts"]["f09"]["interpretation"]["kind"] == (
        UtteranceKind.EXPLANATION_REQUEST.value
    )
    assert provider.requests
    blob = "".join(m.content for m in provider.requests[0].messages)
    cats = set()
    for m in provider.requests[0].messages:
        cats.update(m.classifications)
    assert raw not in blob
    assert "QUESTION_TEXT_LOCAL_ONLY_SENTINEL" not in blob
    assert "社保转移" in blob
    assert DataClassification.USER_FREE_TEXT not in cats


def test_generic_explanation_workflow():
    explanation = FakeExplanationService(
        ExplanationResult(
            status=ExplanationStatus.ANSWERED,
            topic="事项A",
            text="事项A是公共概念。",
        )
    )
    mapper = FakeAnswerMapper(
        AnswerMapperOutput(
            kind=MapperUtteranceKind.SLOT_ANSWER,
            mapped_value="事项A",
            confidence=1.0,
        )
    )
    ctx = SlotInteractionContext(
        transition_status=F04Status.NEED_SLOT,
        current_node_id="n1",
        required_slot="choice",
        allowed_values=("事项A", "事项B"),
        question_text="您要办理事项A还是事项B？",
        invalid_value=None,
        current_slots={},
    )
    final = run_slot_interaction_workflow(
        create_initial_state("req-gen", "什么是事项A？"),
        ctx,
        _deps(mapper=mapper, explanation=explanation),
    )
    assert mapper.calls == 0
    assert explanation.calls == 1
    assert final["artifacts"]["f09"]["interpretation"]["kind"] == (
        UtteranceKind.EXPLANATION_REQUEST.value
    )


def test_unknown_topic_workflow_no_explanation():
    explanation = FakeExplanationService(
        ExplanationResult(
            status=ExplanationStatus.ANSWERED,
            topic="x",
            text="should not run",
        )
    )
    mapper = FakeAnswerMapper(
        AnswerMapperOutput(
            kind=MapperUtteranceKind.OTHER,
            mapped_value=None,
            confidence=None,
        )
    )
    final = run_slot_interaction_workflow(
        create_initial_state("req-unk", "什么是养老金计算？"),
        _service_action_context(),
        _deps(mapper=mapper, explanation=explanation),
    )
    assert explanation.calls == 0
    assert mapper.calls == 1
    assert final["artifacts"]["f09"]["interpretation"]["kind"] == (
        UtteranceKind.OTHER.value
    )
    assert final["artifacts"]["f09"]["business_transition"] is None


def test_accepted_real_f04_employment_integration(monkeypatch: pytest.MonkeyPatch):
    graph = load_decision_graph(GRAPH_PATH)
    mapper = FakeAnswerMapper(
        AnswerMapperOutput(
            kind=MapperUtteranceKind.SLOT_ANSWER,
            mapped_value="other_flexible_employment",
            confidence=0.95,
        )
    )
    explanation = FakeExplanationService(
        ExplanationResult(
            status=ExplanationStatus.UNSUPPORTED,
            topic="x",
            text=None,
        )
    )
    calls = {"f04": 0}
    real = __import__(
        "gov_service_agent.agent.nodes", fromlist=["advance_until_blocked"]
    ).advance_until_blocked

    def _spy(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["f04"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(
        "gov_service_agent.agent.nodes.advance_until_blocked",
        _spy,
    )
    need = real(
        graph,
        "social_security_entry",
        {
            "service_action": "payment",
            "payment_actor": "self_payment",
        },
    )
    assert need.status == F04Status.NEED_SLOT
    assert need.required_slot == "employment_type"
    ctx = build_slot_interaction_context(
        need,
        {
            "service_action": "payment",
            "payment_actor": "self_payment",
        },
    )
    caller_slots = {
        "service_action": "payment",
        "payment_actor": "self_payment",
    }
    ctx = build_slot_interaction_context(need, caller_slots)
    final = run_slot_interaction_workflow(
        create_initial_state("req-emp", "平时接零活，没有固定单位"),
        ctx,
        _deps(mapper=mapper, explanation=explanation, graph=graph),
    )
    f09 = final["artifacts"]["f09"]
    assert calls["f04"] == 1
    assert f09["mapping_validation"]["status"] == (
        MappingValidationStatus.ACCEPTED.value
    )
    assert f09["business_transition"]["status"] == (
        F04Status.TERMINAL_CANDIDATE.value
    )
    assert f09["business_transition"]["candidate_business_id"] == "DEMO_SS_001"
    assert "visited_node_ids" in f09["business_transition"]
    assert "confirmed_business_id" not in f09
    assert "confirmed_business_id" not in final
    assert caller_slots == {
        "service_action": "payment",
        "payment_actor": "self_payment",
    }


def test_hallucinated_and_low_confidence_no_f04(monkeypatch: pytest.MonkeyPatch):
    calls = {"f04": 0}

    def _boom(*_a, **_k):  # type: ignore[no-untyped-def]
        calls["f04"] += 1
        raise AssertionError("F04 must not run")

    monkeypatch.setattr(
        "gov_service_agent.agent.nodes.advance_until_blocked",
        _boom,
    )
    invented = FakeAnswerMapper(
        AnswerMapperOutput(
            kind=MapperUtteranceKind.SLOT_ANSWER,
            mapped_value="invented_value",
            confidence=1.0,
        )
    )
    final_inv = run_slot_interaction_workflow(
        create_initial_state("req-inv", "随便说点"),
        _service_action_context(),
        _deps(mapper=invented),
    )
    assert (
        final_inv["artifacts"]["f09"]["mapping_validation"]["status"]
        == MappingValidationStatus.INVALID_VALUE.value
    )
    assert calls["f04"] == 0
    assert final_inv["artifacts"]["f09"]["response_text"].endswith(
        _service_action_context().question_text
    )

    low = FakeAnswerMapper(
        AnswerMapperOutput(
            kind=MapperUtteranceKind.SLOT_ANSWER,
            mapped_value="transfer",
            confidence=0.79,
        )
    )
    final_low = run_slot_interaction_workflow(
        create_initial_state("req-low", "可能是转移"),
        _service_action_context(),
        _deps(mapper=low),
    )
    assert (
        final_low["artifacts"]["f09"]["mapping_validation"]["status"]
        == MappingValidationStatus.LOW_CONFIDENCE.value
    )
    assert calls["f04"] == 0


def test_threshold_080_accepted(monkeypatch: pytest.MonkeyPatch):
    graph = load_decision_graph(GRAPH_PATH)
    mapper = FakeAnswerMapper(
        AnswerMapperOutput(
            kind=MapperUtteranceKind.SLOT_ANSWER,
            mapped_value="transfer",
            confidence=0.80,
        )
    )
    calls = {"f04": 0}
    real = __import__(
        "gov_service_agent.agent.nodes", fromlist=["advance_until_blocked"]
    ).advance_until_blocked

    def _spy(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["f04"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(
        "gov_service_agent.agent.nodes.advance_until_blocked",
        _spy,
    )
    final = run_slot_interaction_workflow(
        create_initial_state("req-080", "我要转移"),
        _service_action_context(),
        _deps(mapper=mapper, graph=graph),
    )
    assert calls["f04"] == 1
    assert final["artifacts"]["f09"]["mapping_validation"]["status"] == (
        MappingValidationStatus.ACCEPTED.value
    )
    assert final["artifacts"]["f09"]["business_transition"]["status"] == (
        F04Status.UNSUPPORTED.value
    )


def test_uncertain_and_other_no_f04(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "gov_service_agent.agent.nodes.advance_until_blocked",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no f04")),
    )
    for kind in (MapperUtteranceKind.UNCERTAIN, MapperUtteranceKind.OTHER):
        mapper = FakeAnswerMapper(
            AnswerMapperOutput(kind=kind, mapped_value=None, confidence=None)
        )
        final = run_slot_interaction_workflow(
            create_initial_state("req-uo", "大厅几点下班？"),
            _service_action_context(),
            _deps(mapper=mapper),
        )
        assert final["artifacts"]["f09"]["business_transition"] is None
        assert final["artifacts"]["f09"]["response_text"]


def test_mapper_provider_and_parse_errors(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "gov_service_agent.agent.nodes.advance_until_blocked",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no f04")),
    )
    provider_err = FakeAnswerMapper(
        LlmProviderError(
            LlmErrorCode.TIMEOUT,
            message="controlled",
            retryable=True,
        )
    )
    final_p = run_slot_interaction_workflow(
        create_initial_state("req-mp", "随便"),
        _service_action_context(),
        _deps(mapper=provider_err),
    )
    assert final_p["artifacts"]["f09"]["failure"]["kind"] == (
        InteractionFailureKind.MAPPER_PROVIDER_ERROR.value
    )
    assert "Timeout" not in str(final_p["artifacts"]["f09"]["failure"])

    parse_mapper = LlmAnswerMapper(CapturingLlmProvider(content="<<<bad>>>"))
    final_parse = run_slot_interaction_workflow(
        create_initial_state("req-parse", "随便"),
        _service_action_context(),
        _deps(
            mapper=parse_mapper,  # type: ignore[arg-type]
            explanation=FakeExplanationService(
                ExplanationResult(
                    status=ExplanationStatus.UNSUPPORTED,
                    topic="x",
                    text=None,
                )
            ),
        ),
    )
    assert final_parse["artifacts"]["f09"]["failure"]["kind"] == (
        InteractionFailureKind.MAPPER_PARSE_ERROR.value
    )


def test_explanation_provider_parse_and_unsafe(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "gov_service_agent.agent.nodes.advance_until_blocked",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no f04")),
    )
    question = "您主要想办理社保缴费、社保转移，还是查询或其他业务？"
    ctx = _service_action_context(question_text=question)

    prov = FakeExplanationService(
        LlmProviderError(
            LlmErrorCode.TIMEOUT,
            message="controlled",
            retryable=False,
        )
    )
    final_prov = run_slot_interaction_workflow(
        create_initial_state("req-ep", "什么是社保转移？"),
        ctx,
        _deps(explanation=prov),
    )
    assert final_prov["artifacts"]["f09"]["failure"]["kind"] == (
        InteractionFailureKind.EXPLANATION_PROVIDER_ERROR.value
    )
    assert final_prov["artifacts"]["f09"]["response_text"].endswith(question)

    parse_svc = LlmExplanationService(CapturingLlmProvider(content="not-json"))
    final_parse = run_slot_interaction_workflow(
        create_initial_state("req-ep2", "什么是社保转移？"),
        ctx,
        SlotInteractionDependencies(
            answer_mapper=FakeAnswerMapper(
                AnswerMapperOutput(
                    kind=MapperUtteranceKind.OTHER,
                    mapped_value=None,
                    confidence=None,
                )
            ),
            explanation_service=parse_svc,
            decision_graph=load_decision_graph(GRAPH_PATH),
            mapping_policy=MappingPolicy(),
        ),
    )
    assert final_parse["artifacts"]["f09"]["failure"]["kind"] == (
        InteractionFailureKind.EXPLANATION_PARSE_ERROR.value
    )

    unsafe_text = "办理需要携带材料到窗口"
    assert is_safe_explanation_text(unsafe_text) is False
    unsafe = FakeExplanationService(
        ExplanationResult(
            status=ExplanationStatus.ANSWERED,
            topic="社保转移",
            text=unsafe_text,
        )
    )
    final_unsafe = run_slot_interaction_workflow(
        create_initial_state("req-unsafe", "什么是社保转移？"),
        ctx,
        _deps(explanation=unsafe),
    )
    f09 = final_unsafe["artifacts"]["f09"]
    assert f09["failure"]["kind"] == (
        InteractionFailureKind.EXPLANATION_UNSAFE_OUTPUT.value
    )
    assert f09["explanation"]["status"] == ExplanationStatus.UNSUPPORTED.value
    assert f09["explanation"]["text"] is None
    assert unsafe_text not in (f09["response_text"] or "")
    assert f09["response_text"].endswith(question)


def test_invalid_slot_context_can_remap(monkeypatch: pytest.MonkeyPatch):
    graph = load_decision_graph(GRAPH_PATH)
    calls = {"f04": 0}
    real = __import__(
        "gov_service_agent.agent.nodes", fromlist=["advance_until_blocked"]
    ).advance_until_blocked

    def _spy(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["f04"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(
        "gov_service_agent.agent.nodes.advance_until_blocked",
        _spy,
    )
    ctx = _service_action_context(
        transition_status=F04Status.INVALID_SLOT,
        invalid_value="invented",
    )
    mapper = FakeAnswerMapper(
        AnswerMapperOutput(
            kind=MapperUtteranceKind.SLOT_ANSWER,
            mapped_value="inquiry",
            confidence=0.9,
        )
    )
    final = run_slot_interaction_workflow(
        create_initial_state("req-invslot", "我要查询"),
        ctx,
        _deps(mapper=mapper, graph=graph),
    )
    assert calls["f04"] == 1
    assert final["artifacts"]["f09"]["business_transition"]["status"] == (
        F04Status.FALLBACK.value
    )


def test_artifact_preservation_and_f09_refresh():
    explanation = FakeExplanationService(
        ExplanationResult(
            status=ExplanationStatus.ANSWERED,
            topic="社保转移",
            text="概念说明。",
        )
    )
    initial = create_initial_state(
        "req-art",
        "什么是社保转移？",
        artifacts={
            "other_feature": {"x": "y"},
            "f09": {
                "interpretation": {"kind": "other"},
                "response_text": "stale",
            },
        },
    )
    before = copy.deepcopy(initial)
    final = run_slot_interaction_workflow(
        initial,
        _service_action_context(),
        _deps(explanation=explanation),
    )
    assert initial == before
    assert final["artifacts"]["other_feature"] == {"x": "y"}
    assert final["artifacts"]["f09"]["response_text"] != "stale"
    assert final["artifacts"]["f09"]["interpretation"]["kind"] == (
        UtteranceKind.EXPLANATION_REQUEST.value
    )


def test_repeated_slot_invocation_isolation():
    explanation = FakeExplanationService(
        ExplanationResult(
            status=ExplanationStatus.ANSWERED,
            topic="社保转移",
            text="概念说明。",
        )
    )
    deps = _deps(explanation=explanation)
    a = run_slot_interaction_workflow(
        create_initial_state("a", "什么是社保转移？"),
        _service_action_context(),
        deps,
    )
    b = run_slot_interaction_workflow(
        create_initial_state("b", "什么是社保转移？"),
        _service_action_context(),
        deps,
    )
    assert a["artifacts"]["f09"] is not b["artifacts"]["f09"]
    assert a["request_id"] == "a"
    assert b["request_id"] == "b"
