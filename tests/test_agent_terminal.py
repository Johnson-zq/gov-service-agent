"""F10 Terminal Validation / User Confirmation tests (local, deterministic)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from gov_service_agent.agent import (
    ConfirmationIntent,
    ConfirmationStatus,
    RuleReadinessSnapshot,
    TerminalCandidateContext,
    TerminalConfirmationDependencies,
    TerminalValidationStatus,
    build_terminal_candidate_context,
    create_initial_state,
    interpret_confirmation,
    prepare_terminal_confirmation,
    resolve_terminal_confirmation,
    terminal_candidate_context_from_business_transition,
)
from gov_service_agent.agent.interaction import serialize_transition_result
from gov_service_agent.agent.terminal import (
    normalize_confirmation_text,
    rule_readiness_from_selection,
    validate_terminal_candidate,
)
from gov_service_agent.business_data.models import load_snapshot
from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.business_graph import load_decision_graph
from gov_service_agent.business_graph.transition import (
    TransitionResult,
    TransitionStatus,
    advance_until_blocked,
)
from gov_service_agent.business_rules.selection import (
    RuleSelectionResult,
    RuleSelectionStatus,
    select_executable_rules,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_SS_001_PATH = REPO_ROOT / "data" / "demo" / "demo_ss_001.json"
GRAPH_PATH = REPO_ROOT / "data" / "graphs" / "demo" / "social_security.json"

_F10_KEYS = {
    "mode",
    "terminal_context",
    "terminal_validation",
    "rule_readiness",
    "confirmation",
    "confirmed_business_id",
    "failure",
    "response_text",
}

_CANONICAL = "灵活就业人员社会保险费申报缴费"


def _demo_repo() -> JsonBusinessRepository:
    return JsonBusinessRepository.from_paths([DEMO_SS_001_PATH])


def _golden_transition() -> TransitionResult:
    graph = load_decision_graph(GRAPH_PATH)
    slots = {
        "service_action": "payment",
        "payment_actor": "self_payment",
        "employment_type": "other_flexible_employment",
    }
    return advance_until_blocked(graph, "social_security_entry", slots)


def _golden_context() -> TerminalCandidateContext:
    return build_terminal_candidate_context(_golden_transition())


def _deps(
    repo: Any | None = None,
    rule_selector: Any | None = None,
) -> TerminalConfirmationDependencies:
    if repo is None:
        repo = _demo_repo()
    if rule_selector is None:
        return TerminalConfirmationDependencies(business_repository=repo)
    return TerminalConfirmationDependencies(
        business_repository=repo,
        rule_selector=rule_selector,
    )


def _walk(value: Any) -> list[Any]:
    found: list[Any] = [value]
    if isinstance(value, dict):
        for item in value.values():
            found.extend(_walk(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk(item))
    return found


# ---------------------------------------------------------------------------
# TerminalCandidateContext / factories
# ---------------------------------------------------------------------------


def test_terminal_context_valid_and_frozen() -> None:
    ctx = _golden_context()
    assert ctx.transition_status == TransitionStatus.TERMINAL_CANDIDATE
    assert ctx.candidate_business_id == "DEMO_SS_001"
    assert isinstance(ctx.visited_node_ids, tuple)
    with pytest.raises(ValidationError):
        ctx.candidate_business_id = "OTHER"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        TerminalCandidateContext(
            transition_status=TransitionStatus.TERMINAL_CANDIDATE,
            current_node_id="n1",
            candidate_business_id="DEMO_SS_001",
            visited_node_ids=("n1",),
            traversed_edge_ids=(),
            extra_field="nope",  # type: ignore[call-arg]
        )


def test_blank_candidate_rejected() -> None:
    with pytest.raises(ValidationError):
        TerminalCandidateContext(
            transition_status=TransitionStatus.TERMINAL_CANDIDATE,
            current_node_id="n1",
            candidate_business_id="  ",
            visited_node_ids=("n1",),
            traversed_edge_ids=(),
        )


@pytest.mark.parametrize(
    "status",
    [
        TransitionStatus.NEED_SLOT,
        TransitionStatus.INVALID_SLOT,
        TransitionStatus.ADVANCED,
        TransitionStatus.UNSUPPORTED,
        TransitionStatus.FALLBACK,
    ],
)
def test_f04_factory_rejects_non_terminal(status: TransitionStatus) -> None:
    if status == TransitionStatus.NEED_SLOT:
        result = TransitionResult(
            status=status,
            current_node_id="n1",
            required_slot="employment_type",
            allowed_values=["a"],
            question_text="q?",
            visited_node_ids=["n1"],
            traversed_edge_ids=[],
        )
    elif status == TransitionStatus.INVALID_SLOT:
        result = TransitionResult(
            status=status,
            current_node_id="n1",
            required_slot="employment_type",
            invalid_value="bad",
            allowed_values=["a"],
            question_text="q?",
            visited_node_ids=["n1"],
            traversed_edge_ids=[],
        )
    elif status == TransitionStatus.UNSUPPORTED:
        result = TransitionResult(
            status=status,
            current_node_id="n1",
            unsupported_reason="unsupported",
            visited_node_ids=["n1"],
            traversed_edge_ids=[],
        )
    else:
        result = TransitionResult(
            status=status,
            current_node_id="n1",
            visited_node_ids=["n1"],
            traversed_edge_ids=[],
        )
    with pytest.raises(ValueError):
        build_terminal_candidate_context(result)


def test_f04_factory_accepts_terminal() -> None:
    result = _golden_transition()
    ctx = build_terminal_candidate_context(result)
    assert ctx.candidate_business_id == "DEMO_SS_001"
    assert ctx.current_node_id == result.current_node_id


def test_f09_adapter_from_serialized_transition() -> None:
    payload = serialize_transition_result(_golden_transition())
    ctx = terminal_candidate_context_from_business_transition(payload)
    assert ctx.candidate_business_id == "DEMO_SS_001"
    assert "question_text" not in ctx.model_dump()
    assert "allowed_values" not in ctx.model_dump()
    assert "invalid_value" not in ctx.model_dump()
    assert "unsupported_reason" not in ctx.model_dump()


@pytest.mark.parametrize(
    "payload",
    [
        {"candidate_business_id": "DEMO_SS_001"},
        {
            "status": TransitionStatus.NEED_SLOT.value,
            "current_node_id": "n1",
            "candidate_business_id": "DEMO_SS_001",
            "visited_node_ids": ["n1"],
            "traversed_edge_ids": [],
        },
        {
            "status": TransitionStatus.TERMINAL_CANDIDATE.value,
            "current_node_id": "n1",
            "candidate_business_id": "  ",
            "visited_node_ids": ["n1"],
            "traversed_edge_ids": [],
        },
        {
            "status": TransitionStatus.TERMINAL_CANDIDATE.value,
            "current_node_id": "n1",
            "visited_node_ids": ["n1"],
            "traversed_edge_ids": [],
        },
        {
            "status": TransitionStatus.TERMINAL_CANDIDATE.value,
            "current_node_id": "n1",
            "candidate_business_id": "DEMO_SS_001",
            "visited_node_ids": "n1",
            "traversed_edge_ids": [],
        },
    ],
)
def test_f09_adapter_strict_failures(payload: dict[str, Any]) -> None:
    with pytest.raises((ValueError, ValidationError)):
        terminal_candidate_context_from_business_transition(payload)


# ---------------------------------------------------------------------------
# Confirmation parser
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["确认", "确认办理", "是的", "就是这个", "没错"],
)
def test_positive_exact_set(text: str) -> None:
    assert interpret_confirmation(text) is ConfirmationIntent.CONFIRMED


@pytest.mark.parametrize(
    "text",
    [
        "不确认",
        "不办理",
        "不是",
        "不是这个",
        "不是这个事项",
        "不是我要办的",
        "我办的不是这个",
        "不对",
    ],
)
def test_negative_exact_set(text: str) -> None:
    assert interpret_confirmation(text) is ConfirmationIntent.REJECTED


@pytest.mark.parametrize(
    "text",
    [
        "好的",
        "好",
        "行",
        "可以",
        "嗯",
        "对",
        "好像是吧",
        "应该是",
        "可能吧",
        "不知道",
        "随便",
        _CANONICAL,
        "确认，但是我不太确定",
        "确认但不是这个",
        "  ",
        "。。。",
    ],
)
def test_uncertain_defaults(text: str) -> None:
    assert interpret_confirmation(text) is ConfirmationIntent.UNCERTAIN


def test_buqueren_not_confirmed_via_substring() -> None:
    assert interpret_confirmation("不确认") is ConfirmationIntent.REJECTED
    assert "确认" in "不确认"


def test_normalization_spaces_and_punctuation() -> None:
    assert interpret_confirmation("  确认。 ") is ConfirmationIntent.CONFIRMED
    assert interpret_confirmation("确认！") is ConfirmationIntent.CONFIRMED
    assert normalize_confirmation_text("不确认。") == "不确认"
    assert normalize_confirmation_text("  是的  ") == "是的"
    # NFKC: fullwidth solidus / compatibility forms collapse without rewriting meaning
    assert normalize_confirmation_text("确认") == "确认"


def test_internal_negation_preserved() -> None:
    assert normalize_confirmation_text("不确认") == "不确认"
    assert normalize_confirmation_text("不是这个") == "不是这个"


# ---------------------------------------------------------------------------
# Validation / rule readiness
# ---------------------------------------------------------------------------


def test_candidate_exists_ready_no_rules() -> None:
    ctx = _golden_context()
    result = validate_terminal_candidate(ctx, _deps())
    assert result.status is TerminalValidationStatus.READY_FOR_CONFIRMATION
    assert result.canonical_name == _CANONICAL
    assert result.rule_readiness is not None
    assert result.rule_readiness.selection_status is RuleSelectionStatus.NO_RULES
    assert result.rule_readiness.selected_rule_count == 0
    assert result.rule_readiness.skipped_non_executable_count == 7
    assert result.rule_readiness.evaluation_performed is False
    dumped = result.rule_readiness.model_dump()
    assert "eligibility_pass" not in dumped
    assert "qualified" not in dumped
    assert "rules_passed" not in dumped


def test_candidate_not_found_selector_not_called() -> None:
    calls = {"n": 0}

    class EmptyRepo:
        def has_business(self, business_id: str) -> bool:
            return False

        def get_business(self, business_id: str) -> Any:
            raise AssertionError("get_business must not run")

    def _selector(business_id: str, repository: Any) -> RuleSelectionResult:
        calls["n"] += 1
        raise AssertionError("selector must not run")

    ctx = TerminalCandidateContext(
        transition_status=TransitionStatus.TERMINAL_CANDIDATE,
        current_node_id="n1",
        candidate_business_id="MISSING_BIZ",
        visited_node_ids=("n1",),
        traversed_edge_ids=(),
    )
    result = validate_terminal_candidate(
        ctx,
        _deps(repo=EmptyRepo(), rule_selector=_selector),
    )
    assert result.status is TerminalValidationStatus.CANDIDATE_NOT_FOUND
    assert calls["n"] == 0


def test_id_mismatch_fail_closed() -> None:
    class MismatchRepo:
        def has_business(self, business_id: str) -> bool:
            return True

        def get_business(self, business_id: str) -> Any:
            return SimpleNamespace(
                business_id="OTHER_ID",
                canonical_name=_CANONICAL,
            )

    calls = {"n": 0}

    def _selector(business_id: str, repository: Any) -> RuleSelectionResult:
        calls["n"] += 1
        raise AssertionError("selector must not run after mismatch")

    ctx = TerminalCandidateContext(
        transition_status=TransitionStatus.TERMINAL_CANDIDATE,
        current_node_id="n1",
        candidate_business_id="DEMO_SS_001",
        visited_node_ids=("n1",),
        traversed_edge_ids=(),
    )
    result = validate_terminal_candidate(
        ctx,
        _deps(repo=MismatchRepo(), rule_selector=_selector),
    )
    assert result.status is TerminalValidationStatus.CANDIDATE_ID_MISMATCH
    assert calls["n"] == 0


def test_canonical_name_unavailable() -> None:
    class BlankNameRepo:
        def has_business(self, business_id: str) -> bool:
            return True

        def get_business(self, business_id: str) -> Any:
            return SimpleNamespace(business_id=business_id, canonical_name="  ")

    calls = {"n": 0}

    def _selector(business_id: str, repository: Any) -> RuleSelectionResult:
        calls["n"] += 1
        raise AssertionError("selector must not run")

    ctx = TerminalCandidateContext(
        transition_status=TransitionStatus.TERMINAL_CANDIDATE,
        current_node_id="n1",
        candidate_business_id="DEMO_SS_001",
        visited_node_ids=("n1",),
        traversed_edge_ids=(),
    )
    result = validate_terminal_candidate(
        ctx,
        _deps(repo=BlankNameRepo(), rule_selector=_selector),
    )
    assert result.status is TerminalValidationStatus.CANONICAL_NAME_UNAVAILABLE
    assert calls["n"] == 0


def test_unevaluated_mapping() -> None:
    def _selector(business_id: str, repository: Any) -> RuleSelectionResult:
        return RuleSelectionResult(
            business_id=business_id,
            status=RuleSelectionStatus.RULES_AVAILABLE_UNEVALUATED,
            selected_rule_ids=["cond-1"],
            skipped_non_executable_count=0,
        )

    result = validate_terminal_candidate(
        _golden_context(),
        _deps(rule_selector=_selector),
    )
    assert result.status is TerminalValidationStatus.RULES_UNEVALUATED
    assert result.rule_readiness is not None
    assert result.rule_readiness.selected_rule_count == 1
    assert result.rule_readiness.evaluation_performed is False


def test_rule_readiness_invariant_no_rules_with_selected() -> None:
    with pytest.raises(ValidationError):
        RuleReadinessSnapshot(
            selection_status=RuleSelectionStatus.NO_RULES,
            selected_rule_count=1,
            skipped_non_executable_count=0,
            evaluation_performed=False,
        )
    with pytest.raises(ValidationError):
        RuleReadinessSnapshot(
            selection_status=RuleSelectionStatus.RULES_AVAILABLE_UNEVALUATED,
            selected_rule_count=0,
            skipped_non_executable_count=0,
            evaluation_performed=False,
        )


def test_rule_readiness_from_real_selection() -> None:
    selection = select_executable_rules("DEMO_SS_001", _demo_repo())
    snap = rule_readiness_from_selection(selection)
    assert snap.selection_status is RuleSelectionStatus.NO_RULES
    assert snap.selected_rule_count == 0
    assert snap.skipped_non_executable_count == 7


# ---------------------------------------------------------------------------
# PREPARE / RESOLVE runners
# ---------------------------------------------------------------------------


def test_prepare_stale_confirm_input_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(user_text: str) -> ConfirmationIntent:
        raise AssertionError(f"parser must not run: {user_text!r}")

    monkeypatch.setattr(
        "gov_service_agent.agent.nodes.interpret_confirmation",
        _boom,
    )
    initial = create_initial_state("req-prep", "确认")
    final = prepare_terminal_confirmation(
        initial,
        _golden_context(),
        _deps(),
    )
    f10 = final["artifacts"]["f10"]
    assert f10["confirmation"]["status"] == (
        ConfirmationStatus.AWAITING_CONFIRMATION.value
    )
    assert f10["confirmation"]["intent"] is None
    assert f10["confirmed_business_id"] is None
    assert _CANONICAL in f10["response_text"]
    assert "DEMO_SS_001" not in f10["response_text"]
    assert "符合办理条件" not in f10["response_text"]
    assert "资格通过" not in f10["response_text"]
    assert "材料" not in f10["response_text"]
    assert "法律依据" not in f10["response_text"]
    assert "interpret_confirmation" not in final["orchestration_trace"]
    assert "finalize_confirmation" not in final["orchestration_trace"]


def test_prepare_stale_slot_answer() -> None:
    final = prepare_terminal_confirmation(
        create_initial_state("req-slot", "平时接零活，没有固定单位"),
        _golden_context(),
        _deps(),
    )
    f10 = final["artifacts"]["f10"]
    assert f10["confirmation"]["status"] == (
        ConfirmationStatus.AWAITING_CONFIRMATION.value
    )
    assert f10["confirmed_business_id"] is None


def test_resolve_confirm() -> None:
    final = resolve_terminal_confirmation(
        create_initial_state("req-ok", "确认"),
        _golden_context(),
        _deps(),
    )
    f10 = final["artifacts"]["f10"]
    assert f10["confirmation"]["intent"] == ConfirmationIntent.CONFIRMED.value
    assert f10["confirmation"]["status"] == ConfirmationStatus.CONFIRMED.value
    assert f10["confirmed_business_id"] == "DEMO_SS_001"
    assert "finalize_confirmation" in final["orchestration_trace"]


def test_resolve_reject() -> None:
    final = resolve_terminal_confirmation(
        create_initial_state("req-rej", "不是这个"),
        _golden_context(),
        _deps(),
    )
    f10 = final["artifacts"]["f10"]
    assert f10["confirmation"]["intent"] == ConfirmationIntent.REJECTED.value
    assert f10["confirmation"]["status"] == ConfirmationStatus.REJECTED.value
    assert f10["confirmed_business_id"] is None
    assert f10["failure"] is None
    assert "finalize_confirmation" not in final["orchestration_trace"]


def test_resolve_uncertain() -> None:
    final = resolve_terminal_confirmation(
        create_initial_state("req-unc", "好像是吧"),
        _golden_context(),
        _deps(),
    )
    f10 = final["artifacts"]["f10"]
    assert f10["confirmation"]["intent"] == ConfirmationIntent.UNCERTAIN.value
    assert f10["confirmation"]["status"] == ConfirmationStatus.UNCERTAIN.value
    assert f10["confirmed_business_id"] is None
    assert "finalize_confirmation" not in final["orchestration_trace"]


def test_unevaluated_confirm_bypass_parser_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _selector(business_id: str, repository: Any) -> RuleSelectionResult:
        return RuleSelectionResult(
            business_id=business_id,
            status=RuleSelectionStatus.RULES_AVAILABLE_UNEVALUATED,
            selected_rule_ids=["cond-1"],
            skipped_non_executable_count=0,
        )

    def _boom(user_text: str) -> ConfirmationIntent:
        raise AssertionError("parser must not run when blocked")

    monkeypatch.setattr(
        "gov_service_agent.agent.nodes.interpret_confirmation",
        _boom,
    )
    final = resolve_terminal_confirmation(
        create_initial_state("req-ue", "确认"),
        _golden_context(),
        _deps(rule_selector=_selector),
    )
    f10 = final["artifacts"]["f10"]
    assert f10["terminal_validation"]["status"] == (
        TerminalValidationStatus.RULES_UNEVALUATED.value
    )
    assert f10["confirmation"]["status"] == ConfirmationStatus.BLOCKED.value
    assert f10["confirmation"]["intent"] is None
    assert f10["confirmed_business_id"] is None
    assert "interpret_confirmation" not in final["orchestration_trace"]
    assert "finalize_confirmation" not in final["orchestration_trace"]


def test_resolve_revalidation_not_found_after_prepare(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _golden_context()
    prepare_terminal_confirmation(
        create_initial_state("req-p", "确认"),
        ctx,
        _deps(),
    )

    class GoneRepo:
        def has_business(self, business_id: str) -> bool:
            return False

        def get_business(self, business_id: str) -> Any:
            raise AssertionError("unreachable")

    def _boom(user_text: str) -> ConfirmationIntent:
        raise AssertionError("parser must not run")

    monkeypatch.setattr(
        "gov_service_agent.agent.nodes.interpret_confirmation",
        _boom,
    )
    final = resolve_terminal_confirmation(
        create_initial_state("req-r", "确认"),
        ctx,
        _deps(repo=GoneRepo()),
    )
    f10 = final["artifacts"]["f10"]
    assert f10["terminal_validation"]["status"] == (
        TerminalValidationStatus.CANDIDATE_NOT_FOUND.value
    )
    assert f10["confirmation"]["status"] == ConfirmationStatus.BLOCKED.value
    assert f10["confirmed_business_id"] is None


@pytest.mark.parametrize(
    ("input_text", "mode"),
    [
        ("确认", "prepare"),
        ("不是这个", "resolve"),
        ("好像是吧", "resolve"),
    ],
)
def test_non_confirm_paths_confirmed_none(input_text: str, mode: str) -> None:
    ctx = _golden_context()
    state = create_initial_state("req-none", input_text)
    if mode == "prepare":
        final = prepare_terminal_confirmation(state, ctx, _deps())
    else:
        final = resolve_terminal_confirmation(state, ctx, _deps())
    assert final["artifacts"]["f10"]["confirmed_business_id"] is None


def test_exact_candidate_propagation() -> None:
    ctx = _golden_context()
    final = resolve_terminal_confirmation(
        create_initial_state("req-exact", "确认"),
        ctx,
        _deps(),
    )
    assert final["artifacts"]["f10"]["confirmed_business_id"] == (
        ctx.candidate_business_id
    )


# ---------------------------------------------------------------------------
# Artifact / immutability / JSON
# ---------------------------------------------------------------------------


def test_artifact_exact_layout_and_json_safe() -> None:
    sentinel = "UNIQUE_F10_RAW_SENTINEL_XYZ_9911"
    final = resolve_terminal_confirmation(
        create_initial_state("req-art", sentinel),
        _golden_context(),
        _deps(),
    )
    f10 = final["artifacts"]["f10"]
    assert set(f10.keys()) == _F10_KEYS
    assert sentinel not in json.dumps(f10, ensure_ascii=False)
    for item in _walk(f10):
        assert not isinstance(item, (Exception, type))
        assert not callable(item) or item is None
    payload = json.dumps(final, allow_nan=False, default=str)
    assert isinstance(payload, str)


def test_fresh_f10_and_preserve_other_namespaces() -> None:
    initial = create_initial_state(
        "req-ns",
        "确认",
        artifacts={
            "f09": {"marker": "keep-me"},
            "other": {"x": 1},
            "f10": {
                "mode": "resolve",
                "terminal_context": None,
                "terminal_validation": None,
                "rule_readiness": None,
                "confirmation": {
                    "status": ConfirmationStatus.CONFIRMED.value,
                    "intent": ConfirmationIntent.CONFIRMED.value,
                },
                "confirmed_business_id": "OLD_ID",
                "failure": {"kind": "X", "message": "old"},
                "response_text": "old-response",
            },
        },
    )
    before = copy.deepcopy(initial)
    final = prepare_terminal_confirmation(
        initial,
        _golden_context(),
        _deps(),
    )
    assert initial == before
    assert final["artifacts"]["f09"] == {"marker": "keep-me"}
    assert final["artifacts"]["other"] == {"x": 1}
    f10 = final["artifacts"]["f10"]
    assert f10["confirmed_business_id"] is None
    assert f10["response_text"] != "old-response"
    assert f10["mode"] == "prepare"


def test_caller_and_context_immutability() -> None:
    ctx = _golden_context()
    ctx_before = ctx.model_dump()
    initial = create_initial_state(
        "req-imm",
        "确认",
        artifacts={"nested": {"items": [1, 2]}},
    )
    before = copy.deepcopy(initial)
    resolve_terminal_confirmation(initial, ctx, _deps())
    assert initial == before
    assert ctx.model_dump() == ctx_before


# ---------------------------------------------------------------------------
# Golden
# ---------------------------------------------------------------------------


def test_golden_demo_ss_001_prepare_and_resolve() -> None:
    transition = _golden_transition()
    assert transition.status == TransitionStatus.TERMINAL_CANDIDATE
    assert transition.candidate_business_id == "DEMO_SS_001"
    ctx = build_terminal_candidate_context(transition)
    repo = _demo_repo()
    business = repo.get_business("DEMO_SS_001")
    selection = select_executable_rules("DEMO_SS_001", repo)
    assert selection.status == RuleSelectionStatus.NO_RULES
    assert selection.selected_rule_ids == []
    assert selection.skipped_non_executable_count == 7

    deps = TerminalConfirmationDependencies(business_repository=repo)
    prepared = prepare_terminal_confirmation(
        create_initial_state("golden-p", "确认"),
        ctx,
        deps,
    )
    f10p = prepared["artifacts"]["f10"]
    assert f10p["confirmation"]["status"] == (
        ConfirmationStatus.AWAITING_CONFIRMATION.value
    )
    assert f10p["confirmed_business_id"] is None
    assert business.canonical_name in f10p["response_text"]
    assert f10p["rule_readiness"]["selection_status"] == (
        RuleSelectionStatus.NO_RULES.value
    )
    assert f10p["rule_readiness"]["selected_rule_count"] == 0
    assert f10p["rule_readiness"]["skipped_non_executable_count"] == 7

    confirmed = resolve_terminal_confirmation(
        create_initial_state("golden-c", "确认"),
        ctx,
        deps,
    )
    assert confirmed["artifacts"]["f10"]["confirmed_business_id"] == "DEMO_SS_001"
    assert confirmed["artifacts"]["f10"]["confirmation"]["status"] == (
        ConfirmationStatus.CONFIRMED.value
    )

    rejected = resolve_terminal_confirmation(
        create_initial_state("golden-r", "不是这个"),
        ctx,
        deps,
    )
    assert rejected["artifacts"]["f10"]["confirmed_business_id"] is None
    assert rejected["artifacts"]["f10"]["confirmation"]["status"] == (
        ConfirmationStatus.REJECTED.value
    )

    uncertain = resolve_terminal_confirmation(
        create_initial_state("golden-u", "好像是吧"),
        ctx,
        deps,
    )
    assert uncertain["artifacts"]["f10"]["confirmed_business_id"] is None
    assert uncertain["artifacts"]["f10"]["confirmation"]["status"] == (
        ConfirmationStatus.UNCERTAIN.value
    )


def test_public_api_imports() -> None:
    from gov_service_agent.agent import (
        BusinessRepositoryReader,
        TerminalConfirmationFailureKind,
        TerminalValidationResult,
        build_terminal_confirmation_workflow,
    )

    assert TerminalCandidateContext is not None
    assert TerminalValidationStatus is not None
    assert RuleReadinessSnapshot is not None
    assert ConfirmationIntent is not None
    assert ConfirmationStatus is not None
    assert TerminalConfirmationDependencies is not None
    assert BusinessRepositoryReader is not None
    assert TerminalValidationResult is not None
    assert TerminalConfirmationFailureKind is not None
    assert build_terminal_confirmation_workflow is not None
    assert callable(prepare_terminal_confirmation)
    assert callable(resolve_terminal_confirmation)
    snapshot = load_snapshot(DEMO_SS_001_PATH)
    assert snapshot.business.canonical_name == _CANONICAL
