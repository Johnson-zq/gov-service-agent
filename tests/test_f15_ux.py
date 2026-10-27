"""F15 dialogue UX: first-turn slots, topic clarification, natural guide answers."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from gov_service_agent.agent.first_turn_extract import (
    LlmFirstTurnExtractor,
    SlotProposal,
    accept_slot_candidates,
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
from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.business_graph.loader import load_decision_graph
from gov_service_agent.guide_knowledge.models import load_guide_document
from gov_service_agent.guide_knowledge.render import (
    FactConstrainedLlmRenderer,
    TemplateGuideRenderer,
)
from gov_service_agent.guide_knowledge.service import GovernmentKnowledgeService
from gov_service_agent.llm.types import (
    LlmErrorCode,
    LlmProviderError,
    LlmResponse,
    RemoteDataPolicyProfile,
)
from gov_service_agent.retrieval.types import RetrievalCandidate, RetrievalResult, RetrievalStatus

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GRAPH_PATH = _REPO_ROOT / "data" / "graphs" / "demo" / "social_security.json"
_BUSINESS_PATH = _REPO_ROOT / "data" / "demo" / "demo_ss_001.json"
_GUIDE_PATH = _REPO_ROOT / "data" / "guides" / "DEMO_SS_001.guide.json"
_SERVICE_QUESTION = "您主要想办理社保缴费、社保转移，还是查询或其他业务？"
_ACTOR_QUESTION = "这次社保缴费主要是单位缴，还是您自己缴？"
_EMPLOYMENT_QUESTION = (
    "您属于哪种灵活就业情况？例如个体户、未在单位参保的非全日制人员，或其他灵活就业人员。"
)


class FakeRetrieval:
    def retrieve(self, query: str) -> RetrievalResult:
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
    def __init__(self, outputs: list[AnswerMapperOutput] | None = None) -> None:
        self._outputs = list(outputs or [])
        self.requests: list[AnswerMappingRequest] = []

    def map_answer(self, request: AnswerMappingRequest) -> AnswerMapperOutput:
        self.requests.append(request)
        if not self._outputs:
            raise AssertionError("mapper called unexpectedly")
        return self._outputs.pop(0)


class ExplodingExtractor:
    def accepted_slots(self, user_text: str) -> dict[str, str]:
        del user_text
        raise RuntimeError("extractor boom")


class FakeLlm:
    def __init__(self, content: str = "{}", error: Exception | None = None) -> None:
        self.content = content
        self.error = error
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
        if self.error is not None:
            raise self.error
        return LlmResponse(content=self.content, provider_name="FAKE", model_id="fake")


def _payload(rows: list[dict[str, object]]) -> str:
    return json.dumps({"slots": rows}, ensure_ascii=False)


def _explicit(slot: str, value: str, evidence: str) -> dict[str, object]:
    return {
        "slot": slot,
        "value": value,
        "evidence": evidence,
        "certainty": "EXPLICIT",
    }


def _unknown(slot: str) -> dict[str, object]:
    return {"slot": slot, "value": None, "evidence": None, "certainty": "UNKNOWN"}


def _processor(
    provider: FakeLlm,
    *,
    profile: RemoteDataPolicyProfile = RemoteDataPolicyProfile.DEMO_APPROVED,
    mapper: ScriptedMapper | None = None,
) -> GovernmentAgentTurnProcessor:
    graph = load_decision_graph(_GRAPH_PATH)
    repository = JsonBusinessRepository.from_paths([_BUSINESS_PATH])
    scripted = mapper or ScriptedMapper()
    extractor = LlmFirstTurnExtractor(
        provider,  # type: ignore[arg-type]
        graph,
        remote_data_policy_profile=profile,
    )
    return GovernmentAgentTurnProcessor(
        decision_graph=graph,
        business_repository=repository,
        retrieval_service=FakeRetrieval(),  # type: ignore[arg-type]
        slot_dependencies=SlotInteractionDependencies(
            answer_mapper=scripted,
            explanation_service=_NoExplanation(),
            decision_graph=graph,
            business_repository=repository,
        ),
        terminal_dependencies=TerminalConfirmationDependencies(
            business_repository=repository,
        ),
        first_turn_extractor=extractor,
    )


class _NoExplanation:
    def explain(self, request: object) -> object:
        del request
        raise AssertionError("explanation should not run")


def _turn(processor: GovernmentAgentTurnProcessor, text: str, restored: AgentState | None = None):
    return processor.process_turn(
        session_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        input_text=text,
        restored_state=restored,
    )


def _slots(state: AgentState) -> dict[str, object]:
    f09 = state["artifacts"]["f09"]
    slot = f09["slot_context"]
    assert isinstance(slot, dict)
    current = slot["current_slots"]
    assert isinstance(current, dict)
    return current


def test_first_turn_accepts_payment_and_self_and_asks_employment() -> None:
    text = "我辞职了，没有单位，想自己交社保。"
    provider = FakeLlm(
        _payload(
            [
                _explicit("service_action", "payment", "想自己交社保"),
                _explicit("payment_actor", "self_payment", "自己交"),
                _unknown("employment_type"),
            ]
        )
    )
    result = _turn(_processor(provider), text)
    assert provider.calls == 1
    assert "明白了，您想自己缴纳社保" in result.response_text
    assert _EMPLOYMENT_QUESTION in result.response_text
    assert _SERVICE_QUESTION not in result.response_text
    assert _slots(result.state) == {
        "service_action": "payment",
        "payment_actor": "self_payment",
    }
    assert read_f10(result.state["artifacts"]).get("confirmed_business_id") in (None, "")


def test_payment_only_does_not_invent_actor() -> None:
    provider = FakeLlm(_payload([_explicit("service_action", "payment", "交社保")]))
    result = _turn(_processor(provider), "我想交社保。")
    assert _slots(result.state) == {"service_action": "payment"}
    assert _ACTOR_QUESTION in result.response_text
    assert "自己缴纳" not in result.response_text


def test_resignation_does_not_fill_employment_type() -> None:
    graph = load_decision_graph(_GRAPH_PATH)
    accepted = accept_slot_candidates(
        "我辞职了，没有单位，想自己交社保。",
        graph,
        [
            SlotProposal(
                slot="employment_type",
                value="other_flexible_employment",
                evidence="辞职",
                certainty="EXPLICIT",
            )
        ],
    )
    assert accepted == {}


def test_self_employed_reaches_confirmation_without_auto_confirm() -> None:
    text = "我是个体户，想自己交社保。"
    provider = FakeLlm(
        _payload(
            [
                _explicit("service_action", "payment", "交社保"),
                _explicit("payment_actor", "self_payment", "自己交"),
                _explicit(
                    "employment_type",
                    "self_employed_without_employees",
                    "个体户",
                ),
            ]
        )
    )
    result = _turn(_processor(provider), text)
    assert "请确认是否办理" in result.response_text
    assert read_f10(result.state["artifacts"]).get("confirmed_business_id") in (None, "")
    confirmed = _turn(_processor(provider), "确认", result.state)
    assert read_f10(confirmed.state["artifacts"])["confirmed_business_id"] == "DEMO_SS_001"


def test_unclear_intent_keeps_original_first_question() -> None:
    provider = FakeLlm(
        _payload([_explicit("service_action", "payment", "社保怎么办")])
    )
    result = _turn(_processor(provider), "我离职了，社保怎么办？")
    assert provider.calls == 1
    assert result.response_text == _SERVICE_QUESTION
    assert "f09" not in result.state["artifacts"] or _no_slots(result.state)


def _no_slots(state: AgentState) -> bool:
    f09 = state["artifacts"].get("f09")
    if not isinstance(f09, dict):
        return True
    slot = f09.get("slot_context")
    if not isinstance(slot, dict):
        return True
    return slot.get("current_slots") in ({}, None)


def test_employer_payment_follows_existing_graph() -> None:
    provider = FakeLlm(
        _payload(
            [
                _explicit("service_action", "payment", "交社保"),
                _explicit("payment_actor", "employer_payment", "公司帮"),
            ]
        )
    )
    result = _turn(_processor(provider), "公司帮我交社保。")
    assert _EMPLOYMENT_QUESTION not in result.response_text
    assert "当前办理路径暂时无法继续" in result.response_text
    assert read_f10(result.state["artifacts"]).get("confirmed_business_id") in (None, "")


def test_dual_service_intent_is_not_forced() -> None:
    provider = FakeLlm(
        _payload([_explicit("service_action", "payment", "交社保")])
    )
    result = _turn(_processor(provider), "我想交社保，也想办理社保转移。")
    assert result.response_text == _SERVICE_QUESTION


def test_conflicting_actor_is_not_written() -> None:
    provider = FakeLlm(
        _payload([_explicit("payment_actor", "self_payment", "自己交")])
    )
    result = _turn(_processor(provider), "公司给我交，也想自己交。")
    assert _slots(result.state) == {"service_action": "payment"}
    assert _ACTOR_QUESTION in result.response_text


def test_extractor_failure_keeps_deterministic_slots() -> None:
    provider = FakeLlm(
        error=LlmProviderError(LlmErrorCode.TIMEOUT, message="timeout", retryable=True)
    )
    result = _turn(_processor(provider), "我辞职了，没有单位，想自己交社保。")
    assert provider.calls == 1
    assert _slots(result.state) == {
        "service_action": "payment",
        "payment_actor": "self_payment",
    }
    assert _EMPLOYMENT_QUESTION in result.response_text


def test_unclear_utterance_falls_back_when_extractor_fails() -> None:
    provider = FakeLlm(
        error=LlmProviderError(LlmErrorCode.TIMEOUT, message="timeout", retryable=True)
    )
    result = _turn(_processor(provider), "我离职了，社保怎么办？")
    assert provider.calls == 1
    assert result.response_text == _SERVICE_QUESTION


def test_invalid_json_keeps_deterministic_payment() -> None:
    provider = FakeLlm("not-json")
    result = _turn(_processor(provider), "我想交社保。")
    assert provider.calls == 1
    assert _slots(result.state) == {"service_action": "payment"}
    assert _ACTOR_QUESTION in result.response_text


def test_policy_denial_does_not_call_model() -> None:
    provider = FakeLlm(_payload([_explicit("service_action", "payment", "交社保")]))
    result = _turn(
        _processor(provider, profile=RemoteDataPolicyProfile.DEFAULT),
        "我想交社保。",
    )
    assert provider.calls == 0
    assert _slots(result.state) == {"service_action": "payment"}
    assert _ACTOR_QUESTION in result.response_text


def test_extractor_exception_does_not_break_turn() -> None:
    graph = load_decision_graph(_GRAPH_PATH)
    repository = JsonBusinessRepository.from_paths([_BUSINESS_PATH])
    processor = GovernmentAgentTurnProcessor(
        decision_graph=graph,
        business_repository=repository,
        retrieval_service=FakeRetrieval(),  # type: ignore[arg-type]
        slot_dependencies=SlotInteractionDependencies(
            answer_mapper=ScriptedMapper(),
            explanation_service=_NoExplanation(),
            decision_graph=graph,
            business_repository=repository,
        ),
        terminal_dependencies=TerminalConfirmationDependencies(
            business_repository=repository,
        ),
        first_turn_extractor=ExplodingExtractor(),
    )
    result = _turn(processor, "我想交社保。")
    assert result.response_text == _SERVICE_QUESTION


def test_future_slot_is_not_persisted_before_its_node() -> None:
    provider = FakeLlm(
        _payload(
            [
                _explicit(
                    "employment_type",
                    "self_employed_without_employees",
                    "个体户",
                )
            ]
        )
    )
    result = _turn(_processor(provider), "我是个体户。")
    assert result.response_text == _SERVICE_QUESTION


def _employment_state() -> tuple[GovernmentAgentTurnProcessor, AgentState]:
    mapper = ScriptedMapper(
        [
            AnswerMapperOutput(
                kind=MapperUtteranceKind.SLOT_ANSWER,
                mapped_value="payment",
                confidence=0.95,
            ),
            AnswerMapperOutput(
                kind=MapperUtteranceKind.SLOT_ANSWER,
                mapped_value="self_payment",
                confidence=0.95,
            ),
        ]
    )
    graph = load_decision_graph(_GRAPH_PATH)
    repository = JsonBusinessRepository.from_paths([_BUSINESS_PATH])
    processor = GovernmentAgentTurnProcessor(
        decision_graph=graph,
        business_repository=repository,
        retrieval_service=FakeRetrieval(),  # type: ignore[arg-type]
        slot_dependencies=SlotInteractionDependencies(
            answer_mapper=mapper,
            explanation_service=_NoExplanation(),
            decision_graph=graph,
            business_repository=repository,
        ),
        terminal_dependencies=TerminalConfirmationDependencies(
            business_repository=repository,
        ),
    )
    state = None
    for text in ("我想办社保", "缴费", "自己缴"):
        state = _turn(processor, text, state).state
    assert state is not None
    return processor, state


def test_topic_clarification_omits_business_question() -> None:
    processor, state = _employment_state()
    before = _slots(state)
    first = _turn(processor, "线下怎么办？", state)
    assert "去哪里办理" in first.response_text
    assert _EMPLOYMENT_QUESTION not in first.response_text
    assert _slots(first.state) == before
    second = _turn(processor, "我想问具体去哪里办理。", first.state)
    assert "建国南路42号" in second.response_text
    assert "我们继续刚才的问题" in second.response_text
    assert _EMPLOYMENT_QUESTION in second.response_text
    assert _slots(second.state) == before
    assert second.state["artifacts"]["f15"]["pending_clarification"] is None


def test_repeated_clarification_does_not_write_slots() -> None:
    processor, state = _employment_state()
    before = _slots(state)
    first = _turn(processor, "线下怎么办？", state)
    second = _turn(processor, "还是不太明白。", first.state)
    assert "去哪里办理" in second.response_text
    assert _EMPLOYMENT_QUESTION not in second.response_text
    assert _slots(second.state) == before
    assert second.state["artifacts"]["f15"]["pending_clarification"] is not None


def test_confirmation_clarification_restores_prompt_only_after_answer() -> None:
    mapper = ScriptedMapper(
        [
            AnswerMapperOutput(
                kind=MapperUtteranceKind.SLOT_ANSWER,
                mapped_value=value,
                confidence=0.95,
            )
            for value in ("payment", "self_payment", "self_employed_without_employees")
        ]
    )
    graph = load_decision_graph(_GRAPH_PATH)
    repository = JsonBusinessRepository.from_paths([_BUSINESS_PATH])
    processor = GovernmentAgentTurnProcessor(
        decision_graph=graph,
        business_repository=repository,
        retrieval_service=FakeRetrieval(),  # type: ignore[arg-type]
        slot_dependencies=SlotInteractionDependencies(
            answer_mapper=mapper,
            explanation_service=_NoExplanation(),
            decision_graph=graph,
            business_repository=repository,
        ),
        terminal_dependencies=TerminalConfirmationDependencies(
            business_repository=repository,
        ),
    )
    state = None
    for text in ("我想办社保", "缴费", "自己缴", "个体户"):
        state = _turn(processor, text, state).state
    assert state is not None
    assert read_f10(state["artifacts"]).get("confirmed_business_id") in (None, "")
    asked = _turn(processor, "线下怎么办？", state)
    assert "去哪里办理" in asked.response_text
    assert "请确认是否办理" not in asked.response_text
    answered = _turn(processor, "我想问去哪里。", asked.state)
    assert "建国南路42号" in answered.response_text
    assert "请确认是否办理" in answered.response_text
    assert read_f10(answered.state["artifacts"]).get("confirmed_business_id") in (None, "")


def test_confirmed_guide_answer_does_not_repeat_materials_preview() -> None:
    mapper = ScriptedMapper(
        [
            AnswerMapperOutput(
                kind=MapperUtteranceKind.SLOT_ANSWER,
                mapped_value=value,
                confidence=0.95,
            )
            for value in ("payment", "self_payment", "self_employed_without_employees")
        ]
    )
    graph = load_decision_graph(_GRAPH_PATH)
    repository = JsonBusinessRepository.from_paths([_BUSINESS_PATH])
    processor = GovernmentAgentTurnProcessor(
        decision_graph=graph,
        business_repository=repository,
        retrieval_service=FakeRetrieval(),  # type: ignore[arg-type]
        slot_dependencies=SlotInteractionDependencies(
            answer_mapper=mapper,
            explanation_service=_NoExplanation(),
            decision_graph=graph,
            business_repository=repository,
        ),
        terminal_dependencies=TerminalConfirmationDependencies(
            business_repository=repository,
        ),
    )
    preview = ConfirmedBusinessMaterialsPreviewProcessor(
        base_processor=processor,
        business_repository=repository,
    )
    state = None
    result = None
    for text in ("我想办社保", "缴费", "自己缴", "个体户", "确认"):
        result = preview.process_turn(
            session_id=str(uuid.uuid4()),
            request_id=str(uuid.uuid4()),
            input_text=text,
            restored_state=state,
        )
        state = result.state
    assert result is not None
    later = preview.process_turn(
        session_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        input_text="这个事项需要什么材料？",
        restored_state=state,
    )
    assert "办理这项业务需要准备身份证。" in later.response_text
    assert "（来源：九、申请材料）" in later.response_text
    assert "需要准备的材料：" not in later.response_text
    assert "我们继续刚才的问题" not in later.response_text


def test_natural_completion_time_is_not_an_unconditional_promise() -> None:
    document = load_guide_document(_GUIDE_PATH)
    service = GovernmentKnowledgeService({document.business_id: document})
    rendered = TemplateGuideRenderer().render_facts(
        service.query("DEMO_SS_001", "completion_time")
    )
    assert "承诺办结时限为“即办”" in rendered
    assert "补正" in rendered
    assert "保证当天办完" not in rendered
    assert "当天一定办结" not in rendered


def test_natural_fees_do_not_say_free() -> None:
    document = load_guide_document(_GUIDE_PATH)
    service = GovernmentKnowledgeService({document.business_id: document})
    rendered = TemplateGuideRenderer().render_facts(service.query("DEMO_SS_001", "fees"))
    assert "未记载" not in rendered or "不能判断" in rendered
    assert "不能判断这项业务是否收费" in rendered
    assert "免费" not in rendered


def test_llm_added_fact_and_timeout_fall_back_to_template() -> None:
    document = load_guide_document(_GUIDE_PATH)
    service = GovernmentKnowledgeService({document.business_id: document})
    result = service.query("DEMO_SS_001", "consultation")
    added = FakeLlm('{"text":"咨询电话是99999，而且免费。"}')
    rendered = FactConstrainedLlmRenderer(added, TemplateGuideRenderer()).render_facts(result)  # type: ignore[arg-type]
    assert "99999" not in rendered
    assert "免费" not in rendered
    assert "0571-86438110" in rendered
    assert "（来源：" in rendered
    timed_out = FakeLlm(
        error=LlmProviderError(LlmErrorCode.TIMEOUT, message="timeout", retryable=True)
    )
    fallback = FactConstrainedLlmRenderer(timed_out, TemplateGuideRenderer()).render_facts(result)  # type: ignore[arg-type]
    assert "0571-86438110" in fallback
    assert timed_out.calls == 1
