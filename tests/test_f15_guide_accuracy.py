"""Guide answer accuracy: materials, payment channels, and smalltalk."""

from __future__ import annotations

import uuid

from gov_service_agent.agent.materials_preview import (
    ConfirmedBusinessMaterialsPreviewProcessor,
)
from gov_service_agent.agent.turn_processor import GovernmentAgentTurnProcessor
from gov_service_agent.business_data.repository import JsonBusinessRepository
from tests.test_f15_guide_qa import (
    _BUSINESS_PATH,
    _EMPLOYMENT_QUESTION,
    _build,
    _business_snapshot,
    _reach_employment,
    _slot,
    _turn,
)
from tests.test_f15_guide_qa import ScriptedExplanation, ScriptedMapper
from tests.test_f15_ux import (
    _explicit,
    _payload,
    _processor,
    _slots,
    _unknown,
)
from tests.test_f15_ux import FakeLlm
from tests.test_f15_ux import _turn as _ux_turn


def _at_employment() -> tuple[GovernmentAgentTurnProcessor, object]:
    processor, _, _mapper = _build(
        ScriptedMapper([_slot("payment"), _slot("self_payment")])
    )
    return processor, _reach_employment(processor)


def test_material_list_questions_name_identity_card() -> None:
    processor, state = _at_employment()
    for text in ("需要什么材料？", "要准备哪些材料？", "办理时要带什么？"):
        result = _turn(processor, text, state)
        assert "身份证" in result.response_text
        assert "补正通知" not in result.response_text
        assert "（来源：九、申请材料）" in result.response_text


def test_incomplete_materials_explain_correction() -> None:
    processor, state = _at_employment()
    before = _business_snapshot(state)
    for text in ("申请材料不齐全怎么办？", "资料不齐怎么处理？"):
        result = _turn(processor, text, state)
        assert "补正通知" in result.response_text
        assert "一次性告知" in result.response_text
        assert "（来源：十、办理流程）" in result.response_text
        assert "需要准备身份证" not in result.response_text
        assert _business_snapshot(result.state) == before


def test_noncompliant_form_uses_correction_not_material_list() -> None:
    processor, state = _at_employment()
    for text in ("材料不符合法定形式怎么办？", "提交的材料不符合法定形式如何处理？"):
        result = _turn(processor, text, state)
        assert "补正通知" in result.response_text
        assert "（来源：十、办理流程）" in result.response_text
        assert "需要准备身份证" not in result.response_text


def test_out_of_scope_uses_refusal_notice() -> None:
    processor, state = _at_employment()
    for text in ("如果不属于受理范围怎么办？", "这件事如果不在受理范围内呢？"):
        result = _turn(processor, text, state)
        assert "不予受理通知" in result.response_text
        assert "补正通知" not in result.response_text
        assert "（来源：十、办理流程）" in result.response_text


def test_alipay_capability_stays_short() -> None:
    processor, state = _at_employment()
    for text in ("支付宝可以缴社保吗？", "用支付宝交社保行吗？"):
        result = _turn(processor, text, state)
        assert "支付宝" in result.response_text
        assert "浙江税务社保缴费" in result.response_text
        assert "可以" in result.response_text


def test_alipay_how_to_pay_distinguishes_direct_and_agreement() -> None:
    processor, state = _at_employment()
    for text in ("支付宝怎么缴纳社保费？", "用支付宝怎样交社保费？"):
        result = _turn(processor, text, state)
        assert "直接缴费" in result.response_text
        assert "银行扣缴协议" in result.response_text
        assert "浙江税务社保缴费" in result.response_text
        assert "银行缴费协议" in result.response_text
        assert "不是一次性直接缴费" in result.response_text
        assert "逐步点击" in result.response_text
        assert "十九、常见问题" in result.response_text


def test_alipay_agreement_steps_come_from_faq() -> None:
    processor, state = _at_employment()
    for text in ("支付宝怎么签银行缴费协议？", "支付宝如何办理银行缴费协议？"):
        result = _turn(processor, text, state)
        assert "银行缴费协议" in result.response_text
        assert "浙江税务社保缴费" in result.response_text
        assert "搜索" in result.response_text
        assert "不是直接缴费" in result.response_text
        assert "（来源：十九、常见问题 1）" in result.response_text


def test_wechat_agreement_includes_profile_step() -> None:
    processor, state = _at_employment()
    for text in ("微信怎么办理银行扣缴协议？", "微信如何签银行扣缴？"):
        result = _turn(processor, text, state)
        assert "添加人员信息" in result.response_text
        assert "银行缴费协议" in result.response_text
        assert "浙江税务社保缴费" in result.response_text


def test_joke_is_friendly_and_not_a_fact_warning() -> None:
    processor, state = _at_employment()
    before = _business_snapshot(state)
    for text in ("你会讲笑话吗？", "讲个笑话吧"):
        result = _turn(processor, text, state)
        assert "笑话" in text
        assert "不能编造" not in result.response_text
        assert "窗口" in result.response_text or "当然可以" in result.response_text
        assert _business_snapshot(result.state) == before


def test_unknown_fee_is_not_invented() -> None:
    processor, state = _at_employment()
    for text in ("当前业务收费多少？", "这个事项要交多少钱？"):
        result = _turn(processor, text, state)
        assert "不能判断这项业务是否收费" in result.response_text
        assert "免费" not in result.response_text


def test_unsupported_government_question_stays_bounded() -> None:
    processor, state = _at_employment()
    before = _business_snapshot(state)
    result = _turn(processor, "外省的医保报销比例是多少？", state)
    assert "不能编造" in result.response_text
    assert _EMPLOYMENT_QUESTION in result.response_text
    assert _business_snapshot(result.state) == before


def test_guide_answers_do_not_confirm_or_repeat_preview() -> None:
    processor, _, _mapper = _build(
        ScriptedMapper(
            [
                _slot("payment"),
                _slot("self_payment"),
                _slot("self_employed_without_employees"),
            ]
        )
    )
    state = None
    for text in ("我想办社保", "缴费", "自己缴", "个体户"):
        state = _turn(processor, text, state).state
    assert state is not None
    waiting = _turn(processor, "申请材料不齐全怎么办？", state)
    assert "补正通知" in waiting.response_text
    assert "请确认是否办理" in waiting.response_text
    assert waiting.state["artifacts"]["f10"].get("confirmed_business_id") in (None, "")
    preview_processor, _, _preview_mapper = _build(
        ScriptedMapper(
            [
                _slot("payment"),
                _slot("self_payment"),
                _slot("self_employed_without_employees"),
            ]
        )
    )
    repository = JsonBusinessRepository.from_paths([_BUSINESS_PATH])
    preview = ConfirmedBusinessMaterialsPreviewProcessor(
        base_processor=preview_processor,
        business_repository=repository,
    )
    confirmed = None
    for text in ("我想办社保", "缴费", "自己缴", "个体户", "确认"):
        confirmed = preview.process_turn(
            session_id=str(uuid.uuid4()),
            request_id=str(uuid.uuid4()),
            input_text=text,
            restored_state=None if confirmed is None else confirmed.state,
        )
    assert confirmed is not None
    later = preview.process_turn(
        session_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        input_text="支付宝怎么缴纳社保费？",
        restored_state=confirmed.state,
    )
    assert "直接缴费" in later.response_text
    assert "需要准备的材料：" not in later.response_text


def test_topic_clarification_still_hides_business_question() -> None:
    processor, state = _at_employment()
    before = _business_snapshot(state)
    first = _turn(processor, "线下怎么办？", state)
    assert "去哪里办理" in first.response_text
    assert _EMPLOYMENT_QUESTION not in first.response_text
    second = _turn(processor, "我想问具体去哪里办理。", first.state)
    assert "建国南路42号" in second.response_text
    assert _EMPLOYMENT_QUESTION in second.response_text
    assert _business_snapshot(second.state) == before


def test_faq_signing_keeps_every_recorded_channel() -> None:
    processor, state = _at_employment()
    result = _turn(processor, "银行窗口和电子税务局怎么签约？", state)
    assert "银行各网点" in result.response_text
    assert "我的缴费协议" in result.response_text
    assert "浙江省电子税务局" in result.response_text
    assert "添加人员信息" in result.response_text
    checked = _turn(processor, "材料需要核实怎么办？", state)
    assert "核实相关材料" in checked.response_text
    assert "需要准备身份证" not in checked.response_text
    identity = _turn(processor, "上门办理要带身份证件吗？", state)
    assert "身份证件原件" in identity.response_text
    assert "免于提供个人身份证件" in identity.response_text


def test_partial_llm_cannot_drop_deterministic_self_payment() -> None:
    provider = FakeLlm(_payload([_explicit("service_action", "payment", "交社保")]))
    result = _ux_turn(_processor(provider), "我没工作了，社保想自己缴。")
    assert _slots(result.state) == {
        "service_action": "payment",
        "payment_actor": "self_payment",
    }
    assert "employment_type" not in _slots(result.state)
    assert "您属于哪种灵活就业情况" in result.response_text


def test_company_payment_and_dual_intent_stay_safe() -> None:
    employer = _ux_turn(
        _processor(FakeLlm("{}")),
        "公司给我交社保。",
    )
    assert "您属于哪种灵活就业情况" not in employer.response_text
    assert "当前办理路径暂时无法继续" in employer.response_text
    mixed = _ux_turn(
        _processor(FakeLlm("{}")),
        "我想缴费也想转移。",
    )
    assert mixed.response_text == "您主要想办理社保缴费、社保转移，还是查询或其他业务？"


def test_material_variants_and_alipay_auto_debit() -> None:
    processor, state = _at_employment()
    before = _business_snapshot(state)
    missing = _turn(processor, "资料少了一份会怎么样？", state)
    assert "补正通知" in missing.response_text
    assert "一次性告知" in missing.response_text
    omitted = _turn(processor, "漏交材料了怎么办？", state)
    assert "补正通知" in omitted.response_text
    assert "需要准备身份证" not in omitted.response_text
    debit = _turn(processor, "我现在在支付宝上开通银行自动扣费，怎么操作？", state)
    assert "银行缴费协议" in debit.response_text
    assert "浙江税务社保缴费" in debit.response_text
    assert "不能编造" not in debit.response_text
    direct = _turn(processor, "怎么用支付宝交社保？", state)
    assert "直接缴费" in direct.response_text
    assert "银行扣缴协议" in direct.response_text
    where = _turn(processor, "支付宝银行缴费协议在哪里办？", state)
    assert "银行缴费协议" in where.response_text
    capable = _turn(processor, "支付宝能直接缴费吗？", state)
    assert "可以" in capable.response_text
    assert "浙江税务社保缴费" in capable.response_text
    assert _business_snapshot(debit.state) == before


def test_multiple_retrieval_candidates_do_not_answer_a_specific_guide() -> None:
    from gov_service_agent.agent.workflow import (
        SlotInteractionDependencies,
        TerminalConfirmationDependencies,
    )
    from gov_service_agent.business_graph.loader import load_decision_graph
    from gov_service_agent.retrieval.types import (
        RetrievalCandidate,
        RetrievalResult,
        RetrievalStatus,
    )
    from tests.test_f15_guide_qa import _GRAPH_PATH

    class TwoCandidates:
        def retrieve(self, query: str) -> RetrievalResult:
            candidate = RetrievalCandidate(
                business_id="DEMO_SS_001",
                display_name="demo",
                score=0.91,
                rank=1,
                direction="social_security",
                eligibility_scope="ONLINE",
            )
            other = RetrievalCandidate(
                business_id="DEMO_SS_001",
                display_name="demo-2",
                score=0.9,
                rank=2,
                direction="social_security",
                eligibility_scope="ONLINE",
            )
            return RetrievalResult(
                status=RetrievalStatus.CANDIDATES,
                query=query,
                candidates=[candidate, other],
            )

    graph = load_decision_graph(_GRAPH_PATH)
    repository = JsonBusinessRepository.from_paths([_BUSINESS_PATH])
    processor = GovernmentAgentTurnProcessor(
        decision_graph=graph,
        business_repository=repository,
        retrieval_service=TwoCandidates(),  # type: ignore[arg-type]
        slot_dependencies=SlotInteractionDependencies(
            answer_mapper=ScriptedMapper([]),
            explanation_service=ScriptedExplanation(),
            decision_graph=graph,
            business_repository=repository,
        ),
        terminal_dependencies=TerminalConfirmationDependencies(
            business_repository=repository,
        ),
    )
    pending = _turn(processor, "我想办社保", None).state
    result = _turn(processor, "需要什么材料？", pending)
    assert "身份证" not in result.response_text
    assert "多项可能的业务" in result.response_text


def test_early_unique_context_answers_guide_without_advancing() -> None:
    processor, _, mapper = _build(ScriptedMapper([]))
    pending = _turn(processor, "我想办社保", None).state
    before = _business_snapshot(pending)
    result = _turn(processor, "资料少了一份会怎么样？", pending)
    assert "如果您咨询的是" in result.response_text
    assert "补正通知" in result.response_text
    assert "您主要想办理社保缴费" in result.response_text
    assert _business_snapshot(result.state) == before
    assert len(mapper.requests) == 0


def test_first_turn_multi_slot_still_skips_repeated_questions() -> None:
    text = "我没有单位，想自己交社保。"
    provider = FakeLlm(
        _payload(
            [
                _explicit("service_action", "payment", "想自己交社保"),
                _explicit("payment_actor", "self_payment", "自己交"),
                _unknown("employment_type"),
            ]
        )
    )
    result = _ux_turn(_processor(provider), text)
    assert "自己缴纳社保" in result.response_text
    assert "您属于哪种灵活就业情况" in result.response_text
    assert _slots(result.state)["service_action"] == "payment"
    assert _slots(result.state)["payment_actor"] == "self_payment"
    assert "employment_type" not in _slots(result.state)
