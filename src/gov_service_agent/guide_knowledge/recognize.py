"""Deterministic guide-topic recognition. Runs before slot-answer mapping."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from gov_service_agent.agent.interaction import detect_explanation_request


class RecognitionKind(StrEnum):
    FALL_THROUGH = "fall_through"
    TOPIC = "topic"
    AMBIGUOUS = "ambiguous"
    OUT_OF_GUIDE = "out_of_guide"
    UNCERTAIN = "uncertain"
    SMALLTALK = "smalltalk"


@dataclass(frozen=True)
class ClarificationOption:
    topic: str
    label: str
    phrases: tuple[str, ...]


@dataclass(frozen=True)
class Recognition:
    kind: RecognitionKind
    topic: str | None = None
    subtopic: str | None = None
    options: tuple[ClarificationOption, ...] = ()
    lookups: tuple[tuple[str, str | None], ...] = ()


_OFFLINE_OPTIONS: tuple[ClarificationOption, ...] = (
    ClarificationOption(
        "handling_locations",
        "办理地点",
        ("地点", "去哪", "哪里", "地址", "在哪"),
    ),
    ClarificationOption(
        "process",
        "办理流程",
        ("流程", "步骤", "环节"),
    ),
    ClarificationOption(
        "on_site_requirement",
        "是否必须到现场",
        ("现场", "跑几次", "到现场"),
    ),
)

_CORRECTION_PHRASES = (
    "不齐全",
    "材料不全",
    "资料不全",
    "材料不齐",
    "资料不齐",
    "不符合法定形式",
    "材料缺失",
    "缺材料",
    "缺资料",
    "少了一份",
    "少了材料",
    "少了资料",
    "资料少",
    "材料少",
    "漏交",
    "漏了材料",
    "少交材料",
)
_OUT_OF_SCOPE_PHRASES = (
    "不予受理",
    "不属于受理范围",
    "不在受理范围",
    "不属于本机关",
    "受理范围外",
)
_AGREEMENT_PHRASES = (
    "扣缴协议",
    "银行扣缴",
    "银行缴费协议",
    "签约",
    "自动扣费",
    "自动扣缴",
    "银行代扣",
    "银行自动",
    "开通银行",
)
_FOREIGN_TOPICS = ("医保", "公积金", "户口", "护照", "不动产")
_GUIDE_HINTS = ("材料", "资料", "缴费", "社保", "支付宝", "微信", "补正", "扣费", "办理")
_HOW_MARKERS = ("怎么", "如何", "怎样")
_CHANNEL_WORDS = ("支付宝", "微信", "小程序")
_SMALLTALK_PHRASES = (
    "笑话",
    "你好",
    "您好",
    "早上好",
    "晚上好",
    "谢谢",
    "感谢",
    "再见",
    "拜拜",
    "你是谁",
    "你叫什么",
    "天气",
    "在吗",
    "吃饭",
    "哈哈",
)

_TOPIC_RULES: tuple[tuple[tuple[str, ...], str, str | None], ...] = (
    (("什么材料", "哪些材料", "要材料", "准备材料", "携带什么", "带什么", "需要材料"), "materials", None),
    (("多久", "多长时间", "办结时限", "办理时限", "几天", "即办"), "completion_time", None),
    (("几点", "上班", "受理时间", "接待时间", "工作时间", "营业时间"), "handling_time", None),
    (("去哪", "在哪", "哪里办", "办理地点", "受理地点", "什么地址", "办公地址"), "handling_locations", None),
    (("法律依据", "政策依据", "哪条法律", "社会保险法"), "legal_basis", None),
    (("咨询电话", "咨询方式", "咨询"), "consultation", None),
    (("投诉",), "complaints", None),
    (("必须去现场", "必须到现场", "要不要去现场", "到现场吗", "现场次数", "跑几次"), "on_site_requirement", None),
    (("收费", "费用", "多少钱", "免费"), "fees", None),
    (("特别提示", "注意事项", "禁止性"), "special_notice", None),
    (("流程图",), "flow_chart", None),
    (("办理流程", "流程"), "process", None),
    (("常见问题",), "faq", None),
    (("缴费渠道", "办税服务厅", "自助办税"), "channels", None),
    (("实施主体", "哪个部门", "哪个局"), "implementing_authority", None),
    (("适用范围", "申报条件", "申请条件", "谁可以"), "applicant_scope", None),
    (("办结结果",), "result", None),
)

_QUESTION_MARKERS: tuple[str, ...] = (
    "?",
    "？",
    "吗",
    "什么",
    "哪里",
    "哪儿",
    "怎么",
    "如何",
    "多久",
    "几点",
    "多少",
    "是否",
    "能不能",
    "可不可以",
    "哪些",
)


def recognize_guide_utterance(
    user_text: str,
    *,
    pending_question_text: str | None,
) -> Recognition:
    text = user_text.strip()
    if not text:
        return Recognition(RecognitionKind.FALL_THROUGH)
    if pending_question_text and detect_explanation_request(text, pending_question_text):
        return Recognition(RecognitionKind.FALL_THROUGH)
    if _is_offline_ambiguous(text):
        return Recognition(RecognitionKind.AMBIGUOUS, options=_OFFLINE_OPTIONS)
    specific = _specific_guide_recognition(text)
    if specific is not None:
        return specific
    for phrases, topic, subtopic in _TOPIC_RULES:
        if any(phrase in text for phrase in phrases):
            return Recognition(RecognitionKind.TOPIC, topic=topic, subtopic=subtopic)
    if _is_smalltalk(text):
        return Recognition(RecognitionKind.SMALLTALK)
    if any(topic in text for topic in _FOREIGN_TOPICS):
        return Recognition(RecognitionKind.OUT_OF_GUIDE)
    asks_question = any(marker in text for marker in _QUESTION_MARKERS)
    if asks_question and any(hint in text for hint in _GUIDE_HINTS):
        return Recognition(RecognitionKind.UNCERTAIN)
    if asks_question:
        return Recognition(RecognitionKind.OUT_OF_GUIDE)
    return Recognition(RecognitionKind.FALL_THROUGH)


def _specific_guide_recognition(text: str) -> Recognition | None:
    if any(phrase in text for phrase in _OUT_OF_SCOPE_PHRASES):
        return _topic("process", "out_of_scope")
    if any(phrase in text for phrase in _CORRECTION_PHRASES):
        return _topic("process", "material_correction")
    if any(phrase in text for phrase in _AGREEMENT_PHRASES):
        return _topic("faq", "bank_withholding")
    asks_how = any(marker in text for marker in _HOW_MARKERS)
    mentions_channel = any(word in text for word in _CHANNEL_WORDS)
    asks_payment = any(word in text for word in ("缴", "交社保", "缴费"))
    if asks_how and asks_payment and (mentions_channel or "社保" in text):
        return Recognition(
            kind=RecognitionKind.TOPIC,
            topic="channels",
            lookups=(("channels", None), ("faq", "bank_withholding")),
        )
    if mentions_channel and asks_payment:
        return _topic("channels", None)
    if any(phrase in text for phrase in ("需要核实", "核实材料", "材料核实")):
        return _topic("process", None)
    if any(phrase in text for phrase in ("身份证件", "上门办理", "上门办税")):
        return _topic("faq", "identity_document")
    if "材料" in text:
        return _topic("materials", None)
    return None


def _topic(topic: str, subtopic: str | None) -> Recognition:
    return Recognition(
        kind=RecognitionKind.TOPIC,
        topic=topic,
        subtopic=subtopic,
        lookups=((topic, subtopic),),
    )


def _is_smalltalk(text: str) -> bool:
    return any(phrase in text for phrase in _SMALLTALK_PHRASES)


def match_clarification_topic(
    user_text: str,
    options: tuple[ClarificationOption, ...],
) -> str | None:
    text = user_text.strip()
    matched = [
        option.topic
        for option in options
        if any(phrase in text for phrase in option.phrases)
    ]
    unique = list(dict.fromkeys(matched))
    if len(unique) != 1:
        return None
    return unique[0]


def _is_offline_ambiguous(text: str) -> bool:
    if "线下" not in text:
        return False
    return any(marker in text for marker in ("怎么办", "如何办", "怎么办理", "如何办理"))
