"""First-turn multi-slot candidates. Acceptance stays deterministic."""

from __future__ import annotations

import logging
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from gov_service_agent.business_graph.models import DecisionGraph, NodeType
from gov_service_agent.llm.policy import evaluate_request_remote_policy
from gov_service_agent.llm.provider import LlmProvider
from gov_service_agent.llm.structured import parse_structured_output
from gov_service_agent.llm.types import (
    DataClassification,
    LlmMessage,
    LlmProviderError,
    LlmRequest,
    LlmRole,
    RemoteDataPolicyProfile,
    StructuredParseError,
)

logger = logging.getLogger("gov_service_agent")

# Matter-scoped phrase tables. A slot is accepted only when the utterance
# supports exactly one allowed graph value and evidence contains a support phrase.
_MATTER_SUPPORT: dict[str, dict[str, dict[str, tuple[str, ...]]]] = {
    "DEMO_SS_001": {
        "service_action": {
            "payment": ("交社保", "缴社保", "缴纳社保", "缴费", "自己交", "自己缴"),
            "transfer": ("社保转移", "转移社保", "办理转移", "想转移"),
            "inquiry": ("查询社保", "查社保"),
        },
        "payment_actor": {
            "self_payment": ("自己交", "自己缴", "自己缴纳", "本人缴", "个人缴"),
            "employer_payment": (
                "公司帮",
                "公司给我",
                "公司交",
                "单位缴",
                "单位交",
                "单位给我",
            ),
        },
        "employment_type": {
            "self_employed_without_employees": ("个体工商户", "个体户"),
            "part_time_without_employer_insurance": ("非全日制",),
            "other_flexible_employment": ("其他灵活就业",),
        },
    },
    "IDCARD_RC_LT5Y": {
        "handling_case": {
            "lost_reissue": (
                "身份证丢了",
                "身份证遗失",
                "证件丢失",
                "丢失补领",
                "补办身份证",
                "补领身份证",
                "身份证补领",
            ),
            "damaged_replace": (
                "身份证损坏",
                "证件损坏",
                "损坏换领",
                "换身份证",
                "身份证换领",
                "换证",
            ),
        },
        # Clause (二) OR: photo-not-self and appearance change are separate facts.
        "submitted_photo_not_self": {
            # Internal slot = “photo is NOT self”. yes ⇒ offline exception.
            "yes": (
                "照片不是本人",
                "现场照片不是本人",
                "照片不是我本人",
                "现场照片不是我本人",
                "不是我本人",
                "不是本人",
                "不是我的照片",
                "照片是别人",
                "照片非本人",
                "非申请人本人",
            ),
            "no": (
                "照片是本人",
                "现场照片是本人",
                "照片是我本人",
                "现场照片是我本人",
                "是我本人",
                "是本人",
                "是我自己的照片",
                "照片就是我本人",
                "照片就是本人",
                "是本人照片",
            ),
        },
        "appearance_change_major": {
            "yes": (
                "相貌变化",
                "相貌特征较大变化",
                "相貌变化比较大",
                "相貌变化很大",
            ),
            "no": (
                "相貌没有变化",
                "没有相貌变化",
                "相貌没有明显变化",
                "没有明显变化",
                "相貌无明显变化",
            ),
        },
        "bad_credit_record": {
            "yes": (
                "不良信用",
                "有不良信用",
                "信用记录不良",
            ),
            "no": (
                "没有不良信用",
                "无不良信用",
                "没有信用问题",
            ),
        },
        "biometric_info_status": {
            "within_5y_valid": (
                "未满五年",
                "未满5年",
                "采集未满五年",
                "信息有效",
                "领证未满五年",
            ),
            "not_valid": (
                "已满五年",
                "满五年了",
                "超过五年",
                "信息无效",
                "采集满五年",
            ),
        },
        "id_validity_band": {
            "ge_10_years": (
                "有效期十年",
                "有效期10年",
                "十年及以上",
                "10年及以上",
                "有效期够十年",
            ),
            "lt_10_years": (
                "有效期不到十年",
                "有效期不足十年",
                "不到10年",
                "不足10年",
            ),
        },
        "hukou_region": {
            "zhejiang": (
                "户口在浙江",
                "浙江户口",
                "户籍在浙江",
                "户口登记在浙江",
            ),
            "not_zhejiang": (
                "户口不在浙江",
                "外省户口",
                "不是浙江户口",
                "户籍不在浙江",
            ),
        },
    },
}


class FirstTurnSlotExtractor(Protocol):
    def accepted_slots(
        self,
        user_text: str,
        *,
        decision_graph: DecisionGraph | None = None,
        business_id: str | None = None,
    ) -> dict[str, str]: ...


class SlotProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: str
    value: str | None = None
    evidence: str | None = None
    certainty: str = "UNKNOWN"


class MultiSlotExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slots: list[SlotProposal] = Field(default_factory=list)


class LlmFirstTurnExtractor:
    """One structured call. Policy denial or any failure returns no slots."""

    def __init__(
        self,
        provider: LlmProvider,
        decision_graph: DecisionGraph,
        *,
        remote_data_policy_profile: RemoteDataPolicyProfile = (
            RemoteDataPolicyProfile.DEFAULT
        ),
    ) -> None:
        self._provider = provider
        self._graph = decision_graph
        self._profile = remote_data_policy_profile

    def accepted_slots(
        self,
        user_text: str,
        *,
        decision_graph: DecisionGraph | None = None,
        business_id: str | None = None,
    ) -> dict[str, str]:
        graph = decision_graph if decision_graph is not None else self._graph
        request = _extraction_request(user_text, graph)
        decision = evaluate_request_remote_policy(request, profile=self._profile)
        decided = deterministic_slot_candidates(
            user_text,
            graph,
            business_id=business_id,
        )
        if not decision.allowed:
            logger.info("message=first_turn_slots_skipped reason=policy_denied")
            _log_accepted(decided)
            return decided
        try:
            response = self._provider.complete(request)
            parsed = parse_structured_output(response.content, MultiSlotExtraction)
        except (LlmProviderError, StructuredParseError):
            logger.info("message=first_turn_slots_skipped reason=extractor_failed")
            _log_accepted(decided)
            return decided
        supplemental = accept_slot_candidates(
            user_text,
            graph,
            parsed.value.slots,
            business_id=business_id,
        )
        for slot_name, value in supplemental.items():
            if slot_name in decided:
                continue
            decided[slot_name] = value
            logger.info(
                "message=first_turn_slot_decision slot=%s outcome=accept reason=llm_supplement",
                slot_name,
            )
        _log_accepted(decided)
        return decided


def deterministic_slot_candidates(
    user_text: str,
    graph: DecisionGraph,
    *,
    business_id: str | None = None,
) -> dict[str, str]:
    """Accept a slot only when the utterance supports exactly one allowed value."""
    support = _support_table(business_id)
    allowed = _graph_allowed_values(graph)
    text = user_text.strip()
    accepted: dict[str, str] = {}
    for slot_name, value_phrases in support.items():
        if slot_name not in allowed:
            logger.info(
                "message=first_turn_slot_decision slot=%s outcome=reject reason=not_in_graph",
                slot_name,
            )
            continue
        supported = {
            value
            for value, phrases in value_phrases.items()
            if value in allowed[slot_name]
            and any(phrase in text and not _negated(text, phrase) for phrase in phrases)
        }
        if len(supported) == 1:
            value = next(iter(supported))
            accepted[slot_name] = value
            logger.info(
                "message=first_turn_slot_decision slot=%s outcome=accept reason=deterministic_unique",
                slot_name,
            )
            continue
        reason = "conflict" if len(supported) > 1 else "not_explicit"
        logger.info(
            "message=first_turn_slot_decision slot=%s outcome=reject reason=%s",
            slot_name,
            reason,
        )
    return accepted


def _log_accepted(accepted: dict[str, str]) -> None:
    logger.info(
        "message=first_turn_slots_accepted count=%s slots=%s",
        len(accepted),
        ",".join(sorted(accepted)),
    )


def accept_slot_candidates(
    user_text: str,
    graph: DecisionGraph,
    proposals: list[SlotProposal],
    *,
    business_id: str | None = None,
) -> dict[str, str]:
    """Keep candidates the graph allows and the utterance unambiguously supports."""
    support = _support_table(business_id)
    allowed = _graph_allowed_values(graph)
    text = user_text.strip()
    by_slot: dict[str, list[SlotProposal]] = {}
    for proposal in proposals:
        by_slot.setdefault(proposal.slot, []).append(proposal)

    accepted: dict[str, str] = {}
    for slot_name, items in by_slot.items():
        if slot_name not in allowed:
            logger.info(
                "message=first_turn_slot_decision slot=%s outcome=reject reason=not_in_graph",
                slot_name,
            )
            continue
        if any(item.certainty.strip().upper() == "CONFLICT" for item in items):
            logger.info(
                "message=first_turn_slot_decision slot=%s outcome=reject reason=conflict",
                slot_name,
            )
            continue
        explicit = [
            item
            for item in items
            if item.certainty.strip().upper() == "EXPLICIT"
            and isinstance(item.value, str)
            and item.value.strip()
            and isinstance(item.evidence, str)
            and item.evidence.strip()
        ]
        values = {item.value.strip() for item in explicit if item.value}
        if len(explicit) != 1 or len(values) != 1:
            logger.info(
                "message=first_turn_slot_decision slot=%s outcome=reject reason=llm_not_explicit",
                slot_name,
            )
            continue
        proposal = explicit[0]
        assert proposal.value is not None
        assert proposal.evidence is not None
        value = proposal.value.strip()
        evidence = proposal.evidence.strip()
        if value not in allowed[slot_name]:
            logger.info(
                "message=first_turn_slot_decision slot=%s outcome=reject reason=illegal_value",
                slot_name,
            )
            continue
        if evidence not in text:
            logger.info(
                "message=first_turn_slot_decision slot=%s outcome=reject reason=evidence_not_in_utterance",
                slot_name,
            )
            continue
        if not _evidence_supports(evidence, slot_name, value, support=support):
            logger.info(
                "message=first_turn_slot_decision slot=%s outcome=reject reason=evidence_unsupported",
                slot_name,
            )
            continue
        supported = _supported_values(text, slot_name, support=support)
        if supported != {value}:
            reason = "conflict" if len(supported) > 1 else "evidence_unsupported"
            if any(
                _negated(text, phrase)
                for phrase in support.get(slot_name, {}).get(value, ())
            ):
                reason = "negation"
            logger.info(
                "message=first_turn_slot_decision slot=%s outcome=reject reason=%s",
                slot_name,
                reason,
            )
            continue
        accepted[slot_name] = value
    return accepted


def _support_table(
    business_id: str | None,
) -> dict[str, dict[str, tuple[str, ...]]]:
    # Omit business_id only in legacy single-matter callers; default to DEMO phrases.
    key = business_id.strip() if isinstance(business_id, str) else "DEMO_SS_001"
    if not key:
        key = "DEMO_SS_001"
    return dict(_MATTER_SUPPORT.get(key, {}))


def _graph_allowed_values(graph: DecisionGraph) -> dict[str, set[str]]:
    allowed: dict[str, set[str]] = {}
    for node in graph.nodes:
        if node.node_type is not NodeType.SLOT_GATE:
            continue
        if not node.slot_name or not node.allowed_values:
            continue
        allowed[node.slot_name] = set(node.allowed_values)
    return allowed


def _evidence_supports(
    evidence: str,
    slot_name: str,
    value: str,
    *,
    support: dict[str, dict[str, tuple[str, ...]]],
) -> bool:
    phrases = support.get(slot_name, {}).get(value, ())
    return any(
        phrase in evidence and not _negated(evidence, phrase) for phrase in phrases
    )


def _supported_values(
    text: str,
    slot_name: str,
    *,
    support: dict[str, dict[str, tuple[str, ...]]],
) -> set[str]:
    found: set[str] = set()
    for value, phrases in support.get(slot_name, {}).items():
        if any(phrase in text and not _negated(text, phrase) for phrase in phrases):
            found.add(value)
    return found


def _negated(text: str, phrase: str) -> bool:
    # Cover 不/不是/非/没有/无, and 没+有… (e.g. 没有不良信用 ⊃ 有不良信用).
    return (
        f"不{phrase}" in text
        or f"不是{phrase}" in text
        or f"非{phrase}" in text
        or f"没有{phrase}" in text
        or f"没{phrase}" in text
        or f"无{phrase}" in text
    )


def _extraction_request(user_text: str, graph: DecisionGraph) -> LlmRequest:
    allowed = _graph_allowed_values(graph)
    catalog = "\n".join(
        f"{slot}: {', '.join(sorted(values))}"
        for slot, values in sorted(allowed.items())
    )
    system = (
        "Extract slot candidates from one government-service utterance.\n"
        'Return STRICT JSON only: {"slots":[{"slot":"...","value":null,'
        '"evidence":null,"certainty":"UNKNOWN"}]}.\n'
        "certainty is EXPLICIT, UNKNOWN, or CONFLICT.\n"
        "value must be one allowed value or null.\n"
        "evidence must be a short quote copied from the user utterance, or null.\n"
        "Do not output next_node, business_id, or confirmed_business_id.\n"
        "Use UNKNOWN when the utterance does not explicitly support a value.\n"
        "Use CONFLICT when the utterance supports more than one value for a slot.\n"
        f"allowed_values:\n{catalog}"
    )
    return LlmRequest(
        messages=[
            LlmMessage(
                role=LlmRole.SYSTEM,
                content=system,
                classifications=frozenset({DataClassification.SYSTEM_CONTROL_DATA}),
            ),
            LlmMessage(
                role=LlmRole.USER,
                content=f"user_text={user_text}",
                classifications=frozenset(
                    {
                        DataClassification.USER_FREE_TEXT,
                        DataClassification.SYSTEM_CONTROL_DATA,
                    }
                ),
            ),
        ],
        operation="f15_first_turn_slots",
    )
