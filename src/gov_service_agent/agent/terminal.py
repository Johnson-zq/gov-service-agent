"""F10 Terminal Validation / User Confirmation / Confirmed Business ID.

Domain models and deterministic services. LangGraph wrappers live in nodes.py /
workflow.py. Does not call advance_until_blocked, RAG, LLM, or Knowledge Graph.
"""

from __future__ import annotations

import copy
import re
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from gov_service_agent.business_data.models import Business
from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.business_graph.transition import (
    TransitionResult,
    TransitionStatus,
)
from gov_service_agent.business_rules.selection import (
    RuleSelectionResult,
    RuleSelectionStatus,
    select_executable_rules,
)

_F10_ARTIFACT_KEY = "f10"

_EDGE_PUNCTUATION = (
    "。．.!！?？,，、;；:：\"'“”‘’（）()[]【】《》<>…·—"
)
_EDGE_PUNCT_RE = re.compile(
    rf"^[{re.escape(_EDGE_PUNCTUATION)}]+|[{re.escape(_EDGE_PUNCTUATION)}]+$"
)
_MULTI_SPACE_RE = re.compile(r"\s+")

_POSITIVE_CONFIRMATIONS: frozenset[str] = frozenset(
    {
        "确认",
        "确认办理",
        "是的",
        "就是这个",
        "没错",
    }
)
_NEGATIVE_CONFIRMATIONS: frozenset[str] = frozenset(
    {
        "不确认",
        "不办理",
        "不是",
        "不是这个",
        "不是这个事项",
        "不是我要办的",
        "我办的不是这个",
        "不对",
    }
)

_MSG_INVALID_CONTEXT = "当前候选事项状态无效，暂不能进行最终事项确认。"
_MSG_CANDIDATE_NOT_FOUND = (
    "当前候选事项无法在业务数据中验证，暂不能进行最终事项确认。"
)
_MSG_ID_MISMATCH = (
    "当前候选事项的数据标识不一致，暂不能进行最终事项确认。"
)
_MSG_CANONICAL_UNAVAILABLE = (
    "当前候选事项缺少可靠的标准名称，暂不能进行最终事项确认。"
)
_MSG_RULES_UNEVALUATED_TMPL = (
    "当前候选事项“{canonical_name}”存在尚未完成确定性校验的业务规则，"
    "暂不能完成最终事项确认。"
)
_MSG_AWAITING_TMPL = (
    "当前候选办理事项为“{canonical_name}”。"
    "请确认是否办理该事项（请回复“确认”或“不确认”）。"
)
_MSG_CONFIRMED_TMPL = "已确认您要办理的事项为“{canonical_name}”。"
_MSG_REJECTED_TMPL = (
    "已取消对当前候选事项“{canonical_name}”的确认。本次不会确认该事项。"
)
_MSG_UNCERTAIN_TMPL = (
    "我还不能确定您是否要办理“{canonical_name}”。"
    "请明确回复“确认”或“不确认”。"
)


class TerminalConfirmationMode(StrEnum):
    PREPARE = "prepare"
    RESOLVE = "resolve"


class TerminalValidationStatus(StrEnum):
    READY_FOR_CONFIRMATION = "READY_FOR_CONFIRMATION"
    INVALID_TERMINAL_CONTEXT = "INVALID_TERMINAL_CONTEXT"
    CANDIDATE_NOT_FOUND = "CANDIDATE_NOT_FOUND"
    CANDIDATE_ID_MISMATCH = "CANDIDATE_ID_MISMATCH"
    CANONICAL_NAME_UNAVAILABLE = "CANONICAL_NAME_UNAVAILABLE"
    RULES_UNEVALUATED = "RULES_UNEVALUATED"


class ConfirmationIntent(StrEnum):
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    UNCERTAIN = "UNCERTAIN"


class ConfirmationStatus(StrEnum):
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    UNCERTAIN = "UNCERTAIN"
    BLOCKED = "BLOCKED"


class TerminalConfirmationFailureKind(StrEnum):
    INVALID_TERMINAL_CONTEXT = "INVALID_TERMINAL_CONTEXT"
    CANDIDATE_NOT_FOUND = "CANDIDATE_NOT_FOUND"
    CANDIDATE_ID_MISMATCH = "CANDIDATE_ID_MISMATCH"
    CANONICAL_NAME_UNAVAILABLE = "CANONICAL_NAME_UNAVAILABLE"
    RULES_UNEVALUATED = "RULES_UNEVALUATED"


def _require_nonblank(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-blank str")
    return value


@runtime_checkable
class BusinessRepositoryReader(Protocol):
    """Minimal read-only repository surface for F10 validation."""

    def has_business(self, business_id: str) -> bool: ...

    def get_business(self, business_id: str) -> Business: ...


def _select_executable_rules_adapter(
    business_id: str,
    repository: BusinessRepositoryReader,
) -> RuleSelectionResult:
    """Typing adapter only; Production semantics = F04 select_executable_rules.

    Does not reimplement VERIFIED/usable filtering or RuleSelectionStatus logic.
    """
    if not isinstance(repository, JsonBusinessRepository):
        raise TypeError(
            "default rule_selector requires JsonBusinessRepository; "
            "inject a custom rule_selector for other repository types"
        )
    return select_executable_rules(business_id, repository)


@dataclass(frozen=True, slots=True)
class TerminalConfirmationDependencies:
    business_repository: BusinessRepositoryReader
    rule_selector: Callable[
        [str, BusinessRepositoryReader], RuleSelectionResult
    ] = field(default=_select_executable_rules_adapter)


class TerminalCandidateContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    transition_status: TransitionStatus
    current_node_id: str
    candidate_business_id: str
    visited_node_ids: tuple[str, ...]
    traversed_edge_ids: tuple[str, ...]

    @field_validator("current_node_id", "candidate_business_id")
    @classmethod
    def _nonblank_str(cls, value: str) -> str:
        return _require_nonblank(value, field_name="field")

    @field_validator("visited_node_ids")
    @classmethod
    def _validate_visited(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("visited_node_ids must be non-empty")
        cleaned: list[str] = []
        for item in value:
            cleaned.append(
                _require_nonblank(item, field_name="visited_node_ids item")
            )
        return tuple(cleaned)

    @field_validator("traversed_edge_ids")
    @classmethod
    def _validate_edges(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned: list[str] = []
        for item in value:
            cleaned.append(
                _require_nonblank(item, field_name="traversed_edge_ids item")
            )
        return tuple(cleaned)

    @model_validator(mode="after")
    def _check_terminal_contract(self) -> TerminalCandidateContext:
        if self.transition_status != TransitionStatus.TERMINAL_CANDIDATE:
            raise ValueError(
                "transition_status must be TERMINAL_CANDIDATE"
            )
        if self.current_node_id != self.visited_node_ids[-1]:
            raise ValueError(
                "current_node_id must equal visited_node_ids[-1]"
            )
        if len(self.traversed_edge_ids) != len(self.visited_node_ids) - 1:
            raise ValueError(
                "len(traversed_edge_ids) must equal "
                "len(visited_node_ids) - 1"
            )
        return self


class RuleReadinessSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    selection_status: RuleSelectionStatus
    selected_rule_count: int = Field(ge=0)
    skipped_non_executable_count: int = Field(ge=0)
    evaluation_performed: bool = False

    @model_validator(mode="after")
    def _check_counts(self) -> RuleReadinessSnapshot:
        if self.evaluation_performed:
            raise ValueError(
                "Phase-1 evaluation_performed must be False"
            )
        if self.selection_status == RuleSelectionStatus.NO_RULES:
            if self.selected_rule_count != 0:
                raise ValueError(
                    "NO_RULES requires selected_rule_count == 0"
                )
        elif (
            self.selection_status
            == RuleSelectionStatus.RULES_AVAILABLE_UNEVALUATED
        ):
            if self.selected_rule_count <= 0:
                raise ValueError(
                    "RULES_AVAILABLE_UNEVALUATED requires "
                    "selected_rule_count > 0"
                )
        else:
            raise ValueError(
                f"unsupported RuleSelectionStatus: {self.selection_status}"
            )
        return self


class TerminalValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: TerminalValidationStatus
    candidate_business_id: str | None = None
    canonical_name: str | None = None
    rule_readiness: RuleReadinessSnapshot | None = None


class TerminalConfirmationFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: TerminalConfirmationFailureKind
    message: str

    @field_validator("message")
    @classmethod
    def _message_nonblank(cls, value: str) -> str:
        return _require_nonblank(value, field_name="message")


def build_terminal_candidate_context(
    result: TransitionResult,
) -> TerminalCandidateContext:
    """Build TerminalCandidateContext from a real F04 TransitionResult."""
    if result.status != TransitionStatus.TERMINAL_CANDIDATE:
        raise ValueError(
            "TerminalCandidateContext requires TERMINAL_CANDIDATE"
        )
    if (
        result.candidate_business_id is None
        or not result.candidate_business_id.strip()
    ):
        raise ValueError(
            "TERMINAL_CANDIDATE requires nonblank candidate_business_id"
        )
    return TerminalCandidateContext(
        transition_status=result.status,
        current_node_id=result.current_node_id,
        candidate_business_id=result.candidate_business_id,
        visited_node_ids=tuple(result.visited_node_ids),
        traversed_edge_ids=tuple(result.traversed_edge_ids),
    )


def _require_str_list(value: Any, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} items must be str")
        items.append(_require_nonblank(item, field_name=f"{field_name} item"))
    return tuple(items)


def terminal_candidate_context_from_business_transition(
    payload: Mapping[str, Any],
) -> TerminalCandidateContext:
    """Strict adapter from F09 controlled business_transition subset."""
    if not isinstance(payload, Mapping):
        raise ValueError("business_transition payload must be a mapping")
    status_raw = payload.get("status")
    if not isinstance(status_raw, str) or not status_raw.strip():
        raise ValueError("business_transition.status must be a nonblank str")
    try:
        status = TransitionStatus(status_raw)
    except ValueError as exc:
        raise ValueError(
            f"unsupported business_transition.status: {status_raw}"
        ) from exc
    if status != TransitionStatus.TERMINAL_CANDIDATE:
        raise ValueError(
            "business_transition.status must be TERMINAL_CANDIDATE"
        )

    current_node_id = payload.get("current_node_id")
    if not isinstance(current_node_id, str):
        raise ValueError("business_transition.current_node_id must be str")
    candidate_business_id = payload.get("candidate_business_id")
    if not isinstance(candidate_business_id, str):
        raise ValueError(
            "business_transition.candidate_business_id must be str"
        )
    visited = _require_str_list(
        payload.get("visited_node_ids"),
        field_name="visited_node_ids",
    )
    traversed = _require_str_list(
        payload.get("traversed_edge_ids"),
        field_name="traversed_edge_ids",
    )
    return TerminalCandidateContext(
        transition_status=status,
        current_node_id=current_node_id,
        candidate_business_id=candidate_business_id,
        visited_node_ids=visited,
        traversed_edge_ids=traversed,
    )


def rule_readiness_from_selection(
    result: RuleSelectionResult,
) -> RuleReadinessSnapshot:
    """Project F04 RuleSelectionResult into F10 readiness snapshot."""
    return RuleReadinessSnapshot(
        selection_status=result.status,
        selected_rule_count=len(result.selected_rule_ids),
        skipped_non_executable_count=result.skipped_non_executable_count,
        evaluation_performed=False,
    )


def validate_terminal_candidate(
    context: TerminalCandidateContext,
    deps: TerminalConfirmationDependencies,
) -> TerminalValidationResult:
    """Deterministic terminal validation (order frozen in TD D17)."""
    candidate_id = context.candidate_business_id
    if not candidate_id.strip():
        return TerminalValidationResult(
            status=TerminalValidationStatus.INVALID_TERMINAL_CONTEXT,
            candidate_business_id=None,
            canonical_name=None,
            rule_readiness=None,
        )

    repo = deps.business_repository
    if not repo.has_business(candidate_id):
        return TerminalValidationResult(
            status=TerminalValidationStatus.CANDIDATE_NOT_FOUND,
            candidate_business_id=candidate_id,
            canonical_name=None,
            rule_readiness=None,
        )

    business = repo.get_business(candidate_id)
    if business.business_id != candidate_id:
        return TerminalValidationResult(
            status=TerminalValidationStatus.CANDIDATE_ID_MISMATCH,
            candidate_business_id=candidate_id,
            canonical_name=None,
            rule_readiness=None,
        )

    canonical = business.canonical_name
    if not isinstance(canonical, str) or not canonical.strip():
        return TerminalValidationResult(
            status=TerminalValidationStatus.CANONICAL_NAME_UNAVAILABLE,
            candidate_business_id=candidate_id,
            canonical_name=None,
            rule_readiness=None,
        )
    canonical_name = canonical.strip()

    selection = deps.rule_selector(candidate_id, repo)
    readiness = rule_readiness_from_selection(selection)

    if readiness.selection_status == RuleSelectionStatus.NO_RULES:
        return TerminalValidationResult(
            status=TerminalValidationStatus.READY_FOR_CONFIRMATION,
            candidate_business_id=candidate_id,
            canonical_name=canonical_name,
            rule_readiness=readiness,
        )
    if (
        readiness.selection_status
        == RuleSelectionStatus.RULES_AVAILABLE_UNEVALUATED
    ):
        return TerminalValidationResult(
            status=TerminalValidationStatus.RULES_UNEVALUATED,
            candidate_business_id=candidate_id,
            canonical_name=canonical_name,
            rule_readiness=readiness,
        )
    raise ValueError(
        f"unsupported RuleSelectionStatus: {readiness.selection_status}"
    )


def normalize_confirmation_text(user_text: str) -> str:
    """Conservative confirmation normalization (exact-match prep only)."""
    if not isinstance(user_text, str):
        raise TypeError("user_text must be str")
    text = unicodedata.normalize("NFKC", user_text)
    text = text.strip()
    text = _MULTI_SPACE_RE.sub(" ", text)
    while True:
        updated = _EDGE_PUNCT_RE.sub("", text).strip()
        if updated == text:
            break
        text = updated
    return text


def interpret_confirmation(user_text: str) -> ConfirmationIntent:
    """Local deterministic high-precision confirmation parser."""
    normalized = normalize_confirmation_text(user_text)
    if normalized in _POSITIVE_CONFIRMATIONS:
        return ConfirmationIntent.CONFIRMED
    if normalized in _NEGATIVE_CONFIRMATIONS:
        return ConfirmationIntent.REJECTED
    return ConfirmationIntent.UNCERTAIN


def assign_confirmed_business_id(
    *,
    validation: TerminalValidationResult,
    intent: ConfirmationIntent,
    candidate_business_id: str,
) -> str | None:
    """Single confirmed-ID assignment gate with defense-in-depth checks."""
    if validation.status != TerminalValidationStatus.READY_FOR_CONFIRMATION:
        return None
    if intent != ConfirmationIntent.CONFIRMED:
        return None
    if (
        validation.candidate_business_id is None
        or validation.candidate_business_id != candidate_business_id
    ):
        return None
    return candidate_business_id


def build_terminal_failure(
    status: TerminalValidationStatus,
    *,
    canonical_name: str | None,
) -> TerminalConfirmationFailure | None:
    if status == TerminalValidationStatus.READY_FOR_CONFIRMATION:
        return None
    if status == TerminalValidationStatus.INVALID_TERMINAL_CONTEXT:
        return TerminalConfirmationFailure(
            kind=TerminalConfirmationFailureKind.INVALID_TERMINAL_CONTEXT,
            message=_MSG_INVALID_CONTEXT,
        )
    if status == TerminalValidationStatus.CANDIDATE_NOT_FOUND:
        return TerminalConfirmationFailure(
            kind=TerminalConfirmationFailureKind.CANDIDATE_NOT_FOUND,
            message=_MSG_CANDIDATE_NOT_FOUND,
        )
    if status == TerminalValidationStatus.CANDIDATE_ID_MISMATCH:
        return TerminalConfirmationFailure(
            kind=TerminalConfirmationFailureKind.CANDIDATE_ID_MISMATCH,
            message=_MSG_ID_MISMATCH,
        )
    if status == TerminalValidationStatus.CANONICAL_NAME_UNAVAILABLE:
        return TerminalConfirmationFailure(
            kind=TerminalConfirmationFailureKind.CANONICAL_NAME_UNAVAILABLE,
            message=_MSG_CANONICAL_UNAVAILABLE,
        )
    if status == TerminalValidationStatus.RULES_UNEVALUATED:
        if canonical_name and canonical_name.strip():
            message = _MSG_RULES_UNEVALUATED_TMPL.format(
                canonical_name=canonical_name.strip()
            )
        else:
            message = (
                "当前候选事项存在尚未完成确定性校验的业务规则，"
                "暂不能完成最终事项确认。"
            )
        return TerminalConfirmationFailure(
            kind=TerminalConfirmationFailureKind.RULES_UNEVALUATED,
            message=message,
        )
    raise ValueError(f"unsupported TerminalValidationStatus: {status}")


def compose_terminal_response_text(
    *,
    mode: TerminalConfirmationMode,
    validation: TerminalValidationResult,
    confirmation_status: ConfirmationStatus,
    confirmation_intent: ConfirmationIntent | None,
) -> str:
    """Deterministic local response templates (D16)."""
    del mode, confirmation_intent  # reserved for future template branching
    canonical = validation.canonical_name
    status = validation.status

    if status != TerminalValidationStatus.READY_FOR_CONFIRMATION:
        failure = build_terminal_failure(status, canonical_name=canonical)
        assert failure is not None
        return failure.message

    assert canonical is not None and canonical.strip()
    name = canonical.strip()

    if confirmation_status == ConfirmationStatus.AWAITING_CONFIRMATION:
        return _MSG_AWAITING_TMPL.format(canonical_name=name)
    if confirmation_status == ConfirmationStatus.CONFIRMED:
        return _MSG_CONFIRMED_TMPL.format(canonical_name=name)
    if confirmation_status == ConfirmationStatus.REJECTED:
        return _MSG_REJECTED_TMPL.format(canonical_name=name)
    if confirmation_status == ConfirmationStatus.UNCERTAIN:
        return _MSG_UNCERTAIN_TMPL.format(canonical_name=name)
    if confirmation_status == ConfirmationStatus.BLOCKED:
        failure = build_terminal_failure(status, canonical_name=name)
        assert failure is not None
        return failure.message
    raise ValueError(f"unsupported ConfirmationStatus: {confirmation_status}")


def serialize_terminal_context(
    context: TerminalCandidateContext,
) -> dict[str, Any]:
    return {
        "transition_status": context.transition_status.value,
        "current_node_id": context.current_node_id,
        "candidate_business_id": context.candidate_business_id,
        "visited_node_ids": list(context.visited_node_ids),
        "traversed_edge_ids": list(context.traversed_edge_ids),
    }


def serialize_terminal_validation(
    result: TerminalValidationResult,
) -> dict[str, Any]:
    return {
        "status": result.status.value,
        "candidate_business_id": result.candidate_business_id,
        "canonical_name": result.canonical_name,
    }


def serialize_rule_readiness(
    readiness: RuleReadinessSnapshot | None,
) -> dict[str, Any] | None:
    if readiness is None:
        return None
    return {
        "selection_status": readiness.selection_status.value,
        "selected_rule_count": readiness.selected_rule_count,
        "skipped_non_executable_count": readiness.skipped_non_executable_count,
        "evaluation_performed": readiness.evaluation_performed,
    }


def serialize_confirmation(
    *,
    status: ConfirmationStatus,
    intent: ConfirmationIntent | None,
) -> dict[str, Any]:
    return {
        "status": status.value,
        "intent": intent.value if intent is not None else None,
    }


def serialize_failure(
    failure: TerminalConfirmationFailure | None,
) -> dict[str, Any] | None:
    if failure is None:
        return None
    return failure.model_dump(mode="json")


def empty_f10_namespace(
    *,
    mode: TerminalConfirmationMode,
    context: TerminalCandidateContext,
) -> dict[str, Any]:
    """Fresh controlled f10 namespace skeleton for one runner invocation."""
    return {
        "mode": mode.value,
        "terminal_context": serialize_terminal_context(context),
        "terminal_validation": None,
        "rule_readiness": None,
        "confirmation": {
            "status": ConfirmationStatus.BLOCKED.value,
            "intent": None,
        },
        "confirmed_business_id": None,
        "failure": None,
        "response_text": None,
    }


def merge_f10_artifacts(
    artifacts: dict[str, Any],
    f10_update: Mapping[str, Any],
) -> dict[str, Any]:
    """Deep-copy artifacts, merge/replace f10 namespace keys, preserve others."""
    owned = copy.deepcopy(artifacts)
    current = owned.get(_F10_ARTIFACT_KEY)
    if not isinstance(current, dict):
        current = {}
    merged = copy.deepcopy(current)
    merged.update(dict(f10_update))
    owned[_F10_ARTIFACT_KEY] = merged
    return owned


def read_f10(artifacts: Mapping[str, Any]) -> dict[str, Any]:
    value = artifacts.get(_F10_ARTIFACT_KEY)
    if not isinstance(value, dict):
        return {}
    return value


def deserialize_terminal_context(
    payload: Mapping[str, Any],
) -> TerminalCandidateContext:
    return TerminalCandidateContext(
        transition_status=TransitionStatus(payload["transition_status"]),
        current_node_id=payload["current_node_id"],
        candidate_business_id=payload["candidate_business_id"],
        visited_node_ids=tuple(payload["visited_node_ids"]),
        traversed_edge_ids=tuple(payload["traversed_edge_ids"]),
    )


def deserialize_terminal_validation(
    payload: Mapping[str, Any],
    *,
    rule_readiness: RuleReadinessSnapshot | None = None,
) -> TerminalValidationResult:
    return TerminalValidationResult(
        status=TerminalValidationStatus(payload["status"]),
        candidate_business_id=payload.get("candidate_business_id"),
        canonical_name=payload.get("canonical_name"),
        rule_readiness=rule_readiness,
    )


def deserialize_rule_readiness(
    payload: Mapping[str, Any] | None,
) -> RuleReadinessSnapshot | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise ValueError("rule_readiness must be a mapping or None")
    return RuleReadinessSnapshot(
        selection_status=RuleSelectionStatus(payload["selection_status"]),
        selected_rule_count=int(payload["selected_rule_count"]),
        skipped_non_executable_count=int(
            payload["skipped_non_executable_count"]
        ),
        evaluation_performed=bool(payload["evaluation_performed"]),
    )
