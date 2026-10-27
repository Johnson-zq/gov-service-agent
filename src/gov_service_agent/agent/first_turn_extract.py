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

# Phrases that may support a graph value. A slot is accepted only when the
# utterance supports exactly one value and the quoted evidence contains it.
_SUPPORT: dict[str, dict[str, tuple[str, ...]]] = {
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
}


class FirstTurnSlotExtractor(Protocol):
    def accepted_slots(self, user_text: str) -> dict[str, str]: ...


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

    def accepted_slots(self, user_text: str) -> dict[str, str]:
        request = _extraction_request(user_text, self._graph)
        decision = evaluate_request_remote_policy(request, profile=self._profile)
        decided = deterministic_slot_candidates(user_text, self._graph)
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
            self._graph,
            parsed.value.slots,
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
) -> dict[str, str]:
    """Accept a slot only when the utterance supports exactly one allowed value."""
    allowed = _graph_allowed_values(graph)
    text = user_text.strip()
    accepted: dict[str, str] = {}
    for slot_name, value_phrases in _SUPPORT.items():
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
) -> dict[str, str]:
    """Keep candidates the graph allows and the utterance unambiguously supports."""
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
        if not _evidence_supports(evidence, slot_name, value):
            logger.info(
                "message=first_turn_slot_decision slot=%s outcome=reject reason=evidence_unsupported",
                slot_name,
            )
            continue
        supported = _supported_values(text, slot_name)
        if supported != {value}:
            reason = "conflict" if len(supported) > 1 else "evidence_unsupported"
            if any(_negated(text, phrase) for phrase in _SUPPORT.get(slot_name, {}).get(value, ())):
                reason = "negation"
            logger.info(
                "message=first_turn_slot_decision slot=%s outcome=reject reason=%s",
                slot_name,
                reason,
            )
            continue
        accepted[slot_name] = value
    return accepted


def _graph_allowed_values(graph: DecisionGraph) -> dict[str, set[str]]:
    allowed: dict[str, set[str]] = {}
    for node in graph.nodes:
        if node.node_type is not NodeType.SLOT_GATE:
            continue
        if not node.slot_name or not node.allowed_values:
            continue
        allowed[node.slot_name] = set(node.allowed_values)
    return allowed


def _evidence_supports(evidence: str, slot_name: str, value: str) -> bool:
    phrases = _SUPPORT.get(slot_name, {}).get(value, ())
    return any(
        phrase in evidence and not _negated(evidence, phrase) for phrase in phrases
    )


def _supported_values(text: str, slot_name: str) -> set[str]:
    found: set[str] = set()
    for value, phrases in _SUPPORT.get(slot_name, {}).items():
        if any(phrase in text and not _negated(text, phrase) for phrase in phrases):
            found.add(value)
    return found


def _negated(text: str, phrase: str) -> bool:
    return (
        f"不{phrase}" in text
        or f"不是{phrase}" in text
        or f"非{phrase}" in text
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
