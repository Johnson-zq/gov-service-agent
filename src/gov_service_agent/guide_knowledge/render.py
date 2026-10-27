"""Template-first guide answers. Optional LLM wording cannot add facts."""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from gov_service_agent.guide_knowledge.service import KnowledgeFact, KnowledgeQueryResult, KnowledgeQueryStatus
from gov_service_agent.llm.provider import LlmProvider
from gov_service_agent.llm.structured import parse_structured_output
from gov_service_agent.llm.types import (
    DataClassification,
    LlmErrorCode,
    LlmMessage,
    LlmProviderError,
    LlmRequest,
    LlmRole,
    StructuredParseError,
)

_OUT_OF_GUIDE = "这个问题不在当前办事指南的记载范围内，我不能编造办理条件、材料、费用、地点或时限。"
_NOT_VERIFIED = "指南里有相关记载，但尚未核验，暂时不能当作办理事实回答。"
_NOT_FOUND = "当前办事指南没有这条已核验记载，我不能补充指南以外的事实。"
_NO_BUSINESS = "当前还没有对应到具体事项的办事指南。请先完成正在确认的办理选项。"
_DIGIT_RUN = re.compile(r"\d{2,}")
_FORBIDDEN_UNLESS_SOURCED = ("免费", "当天一定办结", "保证可以办理")


class GuideAnswerRenderer(Protocol):
    def render_facts(self, result: KnowledgeQueryResult) -> str: ...


class TemplateGuideRenderer:
    """Render only the supplied verified fact text and its source section."""

    def render_facts(self, result: KnowledgeQueryResult) -> str:
        if result.status is KnowledgeQueryStatus.NOT_VERIFIED:
            return _NOT_VERIFIED
        if result.status is not KnowledgeQueryStatus.FOUND or not result.facts:
            return _NOT_FOUND
        composed = _compose_related(result.facts)
        if composed is not None:
            return composed
        blocks = [_render_fact(fact) for fact in result.facts]
        return "\n\n".join(blocks)


def render_out_of_guide() -> str:
    return _OUT_OF_GUIDE


def render_smalltalk(user_text: str) -> str:
    text = user_text.strip()
    if "笑话" in text:
        return "当然可以。为什么电脑怕冷？因为它喜欢开窗口。"
    if any(phrase in text for phrase in ("谢谢", "感谢")):
        return "不客气。办理上还有想了解的，可以直接问我。"
    if "天气" in text:
        return "我这边不查天气预报。办理上的问题，我可以按当前办事指南回答。"
    if any(phrase in text for phrase in ("再见", "拜拜")):
        return "好的，需要继续办理时再告诉我。"
    return "我在。您可以继续问这项业务的办理问题。"


def render_business_not_ready() -> str:
    return _NO_BUSINESS


def render_matter_unclear() -> str:
    return "当前还有多项可能的业务，请先说明要办理哪一项，我再按对应的办事指南回答。"


def render_uncertain_guide() -> str:
    return "我还不能确定您想了解哪一部分。您可以直接说材料补正、缴费方式，或银行扣缴协议。"


def render_clarification(labels: tuple[str, ...]) -> str:
    label_set = set(labels)
    if {"办理地点", "办理流程"} <= label_set:
        return "您是想了解去哪里办理、窗口办理的具体流程，还是想确认是否需要到现场？"
    choices = "、".join(labels)
    return f"您是想了解{choices}？请直接说明其中一项。"


def append_resume(answer: str, resume_question: str | None) -> str:
    if resume_question is None or not resume_question.strip():
        return answer
    return f"{answer.strip()}\n\n我们继续刚才的问题：\n{resume_question.strip()}"


def _compose_related(facts: list[KnowledgeFact]) -> str | None:
    topics = {fact.topic for fact in facts}
    subtopics = {fact.subtopic for fact in facts}
    if "channels" in topics and "bank_withholding" in subtopics:
        channel = next(fact for fact in facts if fact.topic == "channels")
        bank = next(fact for fact in facts if fact.subtopic == "bank_withholding")
        direct = _present_phrase(
            channel.text,
            "可登录支付宝、微信端的“浙江税务社保缴费”小程序办理缴费，并可选择开通自助缴费功能",
        )
        alipay = _present_phrase(
            bank.text,
            "支付宝：搜索“浙江税务社保缴费”小程序，通过“银行缴费协议”办理",
        )
        wechat = _present_phrase(
            bank.text,
            "微信：搜索“浙江税务社保缴费”小程序，添加人员信息后通过“银行缴费协议”办理",
        )
        body = (
            "根据办事指南，直接缴费和银行扣缴协议是两种不同办理方式。\n"
            f"直接缴费：{direct}。"
            "指南没有记载小程序里的逐步点击操作。\n"
            "银行扣缴协议是签约后委托银行从签约账户代扣，不是一次性直接缴费。"
            f"{wechat}。{alipay}。\n"
            "您想先了解直接缴费，还是办理银行扣缴协议签约？"
        )
        return _with_sources(body, [channel, bank])
    return None


def _present_phrase(text: str, phrase: str) -> str:
    if phrase in text:
        return phrase
    return text.strip().strip("。")


def _render_fact(fact: KnowledgeFact) -> str:
    return f"{_natural_sentence(fact)}\n（来源：{fact.source_section}）"


def _natural_sentence(fact: KnowledgeFact) -> str:
    text = fact.text.strip()
    topic = fact.topic
    if fact.subtopic == "material_correction":
        return (
            "材料不齐全或不符合法定形式时，受理环节会制作《税务事项通知书》（补正通知），"
            "一次性告知需补正的内容。"
        )
    if fact.subtopic == "out_of_scope":
        return (
            "依法不属于本机关职权或本业务受理范围的，会制作《税务事项通知书》（不予受理通知），"
            "并告知不予受理的原因。"
        )
    if fact.subtopic == "bank_withholding":
        return _bank_agreement_sentence(text)
    if topic == "materials" and "未记载" not in text:
        material = text.split("：", 1)[-1].strip("。")
        if material:
            return f"办理这项业务需要准备{material}。"
    if topic == "completion_time" and "即办" in text:
        caveat = ""
        if "补正" in text:
            caveat = "如果材料需要补正，或审核不通过需要退回，仍要按照指南记载的流程处理。"
        return f"根据办事指南，这项业务的承诺办结时限为“即办”。{caveat}"
    if topic == "consultation":
        phone = _phone_in(text)
        if phone is not None:
            return f"您可以拨打 {phone} 咨询。"
    if topic == "complaints":
        phone = _phone_in(text)
        if phone is not None:
            return f"您可以拨打 {phone} 投诉。"
    if topic == "handling_locations":
        address = _parenthetical(text)
        if address is not None:
            return f"可以到办事指南记载的受理地点办理，具体地址为{address}。"
    if topic == "channels" and "浙江税务社保缴费" in text and "支付宝" in text:
        return (
            "可以。根据办事指南，您可以通过支付宝的“浙江税务社保缴费”小程序办理缴费，"
            "也可以使用指南记载的其他缴费渠道。"
        )
    if topic == "fees":
        return (
            "办事指南列出了收费栏目，但没有记载具体收费项目、收费标准或减免说明，"
            "因此不能判断这项业务是否收费。"
        )
    return text


def _bank_agreement_sentence(text: str) -> str:
    parts = ["办理银行扣缴协议，是委托银行从签约账户代扣社保费，不是直接缴费。"]
    for phrase in (
        "银行窗口：支持社保费代征的银行各网点均可办理签约。",
        "微信：搜索“浙江税务社保缴费”小程序，添加人员信息后通过“银行缴费协议”办理。",
        "支付宝：搜索“浙江税务社保缴费”小程序，通过“银行缴费协议”办理。",
        "税务自助办税终端：通过“我的缴费协议”办理。",
        "电子税务局：登录“浙江省电子税务局”，办理自然人用户注册后，通过“社保费办理”中的“我的缴费协议”办理。",
    ):
        if phrase.rstrip("。") in text or phrase in text:
            parts.append(phrase if phrase.endswith("。") else f"{phrase}。")
    return "".join(parts)


def _phone_in(text: str) -> str | None:
    match = re.search(r"0\d{2,3}-\d{5,8}", text)
    if match is None:
        return None
    return match.group(0)


def _parenthetical(text: str) -> str | None:
    match = re.search(r"（([^）]+)）", text)
    if match is None:
        return None
    return match.group(1)


class _RenderedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)


class FactConstrainedLlmRenderer:
    """Rewrite verified facts. Reject outputs that introduce new numbers or claims."""

    def __init__(self, provider: LlmProvider, fallback: GuideAnswerRenderer) -> None:
        self._provider = provider
        self._fallback = fallback

    def render_facts(self, result: KnowledgeQueryResult) -> str:
        fallback_text = self._fallback.render_facts(result)
        if result.status is not KnowledgeQueryStatus.FOUND:
            return fallback_text
        source = "\n".join(fact.text for fact in result.facts)
        request = LlmRequest(
            messages=[
                LlmMessage(
                    role=LlmRole.SYSTEM,
                    content=(
                        "Rewrite the verified guide facts in plain language. "
                        'Return STRICT JSON only: {"text":"..."}. '
                        "Do not add fees, locations, deadlines, materials, phones, "
                        "or legal provisions that are absent from the facts."
                    ),
                    classifications=frozenset({DataClassification.SYSTEM_CONTROL_DATA}),
                ),
                LlmMessage(
                    role=LlmRole.USER,
                    content=f"verified_facts:\n{source}",
                    classifications=frozenset(
                        {DataClassification.PUBLIC_BUSINESS_METADATA}
                    ),
                ),
            ],
            operation="f15_render_verified_facts",
        )
        try:
            response = self._provider.complete(request)
            parsed = parse_structured_output(response.content, _RenderedAnswer)
        except (LlmProviderError, StructuredParseError):
            return fallback_text
        if _introduces_facts(parsed.value.text, source):
            return fallback_text
        return _with_sources(parsed.value.text, result.facts)


def _with_sources(text: str, facts: list[KnowledgeFact]) -> str:
    lines = [text.strip()]
    seen: set[str] = set()
    for fact in facts:
        if fact.source_section in seen:
            continue
        seen.add(fact.source_section)
        lines.append(f"（来源：{fact.source_section}）")
    return "\n".join(lines)


def _introduces_facts(output: str, source: str) -> bool:
    for token in _FORBIDDEN_UNLESS_SOURCED:
        if token in output and token not in source:
            return True
    for run in _DIGIT_RUN.findall(output):
        if run not in source:
            return True
    if LlmErrorCode.EMPTY_CONTENT.value in output:
        return True
    return False
