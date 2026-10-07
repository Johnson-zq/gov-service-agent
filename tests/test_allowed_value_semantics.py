"""F09 controlled allowed-value semantic projection tests. Offline only."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from gov_service_agent.business_data.models import BusinessSnapshot, load_snapshot
from gov_service_agent.business_data.repository import (
    ConsumptionMode,
    JsonBusinessRepository,
)
from gov_service_agent.business_data.semantics import (
    ControlledAllowedValueSemantic,
    SemanticCoverage,
    SemanticProjectionResult,
    project_allowed_value_semantics,
)
from gov_service_agent.business_graph import load_decision_graph
from gov_service_agent.business_graph.models import SourceConditionRef

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_SS_001_PATH = REPO_ROOT / "data" / "demo" / "demo_ss_001.json"
GRAPH_PATH = REPO_ROOT / "data" / "graphs" / "demo" / "social_security.json"

_A = "self_employed_without_employees"
_B = "part_time_without_employer_insurance"
_C = "other_flexible_employment"
_ALLOWED = (_A, _B, _C)
_MEANINGS = {
    _A: "无雇工的个体工商户",
    _B: "未在用人单位参加社会保险的非全日制从业人员",
    _C: "其他灵活就业人员",
}
_REF_IDS = (
    "cond-applicant-01",
    "cond-applicant-02",
    "cond-applicant-03",
)


def _snapshot() -> BusinessSnapshot:
    return load_snapshot(DEMO_SS_001_PATH)


def _repository(snapshot: BusinessSnapshot) -> JsonBusinessRepository:
    return JsonBusinessRepository({snapshot.business.business_id: snapshot})


def _demo_repository() -> JsonBusinessRepository:
    return _repository(_snapshot())


def _refs(*condition_ids: str) -> tuple[SourceConditionRef, ...]:
    return tuple(
        SourceConditionRef(business_id="DEMO_SS_001", condition_id=item)
        for item in condition_ids
    )


def _project(
    repository: JsonBusinessRepository,
    *,
    allowed: tuple[str, ...] = _ALLOWED,
    refs: tuple[SourceConditionRef, ...] | None = None,
    slot_name: str = "employment_type",
) -> SemanticProjectionResult:
    if refs is None:
        refs = _refs(*_REF_IDS)
    return project_allowed_value_semantics(
        repository,
        slot_name=slot_name,
        allowed_values=allowed,
        source_condition_refs=refs,
    )


def _with_updates(updates: dict[str, dict[str, object]]) -> JsonBusinessRepository:
    snapshot = _snapshot()
    conditions = []
    for condition in snapshot.conditions:
        patch = updates.get(condition.condition_id)
        if patch is None:
            conditions.append(condition)
        else:
            conditions.append(condition.model_copy(update=patch))
    return _repository(snapshot.model_copy(update={"conditions": conditions}))


def test_projection_full_employment_type_demo_slice() -> None:
    graph = load_decision_graph(GRAPH_PATH)
    node = next(item for item in graph.nodes if item.node_id == "employment_type")
    assert node.source_condition_refs is not None
    result = project_allowed_value_semantics(
        _demo_repository(),
        slot_name="employment_type",
        allowed_values=tuple(node.allowed_values or ()),
        source_condition_refs=node.source_condition_refs,
    )
    assert result.coverage is SemanticCoverage.FULL
    assert result.reason_code == "full"
    assert len(result.semantics) == 3
    assert tuple(item.value for item in result.semantics) == _ALLOWED
    assert tuple(item.meaning for item in result.semantics) == tuple(
        _MEANINGS[value] for value in _ALLOWED
    )


def test_projection_orders_by_allowed_values_not_repository_order() -> None:
    snapshot = _snapshot()
    by_id = {condition.condition_id: condition for condition in snapshot.conditions}
    reordered_ids = (
        "cond-applicant-03",
        "cond-applicant-01",
        "cond-applicant-02",
    )
    rest = [
        condition
        for condition in snapshot.conditions
        if condition.condition_id not in reordered_ids
    ]
    repository = _repository(
        snapshot.model_copy(
            update={
                "conditions": [by_id[item] for item in reordered_ids] + rest
            }
        )
    )
    public_values = [
        condition.normalized_values[0]
        for condition in repository.get_conditions(
            "DEMO_SS_001",
            consumption=ConsumptionMode.PUBLIC,
        )
        if condition.normalized_values
    ]
    assert public_values == [_C, _A, _B]
    result = _project(repository, refs=_refs(*reordered_ids))
    assert result.coverage is SemanticCoverage.FULL
    assert tuple(item.value for item in result.semantics) == _ALLOWED
    assert tuple(item.meaning for item in result.semantics) == (
        _MEANINGS[_A],
        _MEANINGS[_B],
        _MEANINGS[_C],
    )


def test_projection_none_skips_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = _demo_repository()
    calls = {"count": 0}
    real = repository.get_conditions

    def _spy(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(repository, "get_conditions", _spy)
    for refs in (None, ()):
        result = project_allowed_value_semantics(
            repository,
            slot_name="employment_type",
            allowed_values=_ALLOWED,
            source_condition_refs=refs,
        )
        assert result.coverage is SemanticCoverage.NONE
        assert result.semantics == ()
        assert result.reason_code == "none"
    assert calls["count"] == 0


def test_projection_partial_missing_value() -> None:
    result = _project(_demo_repository(), refs=_refs(*_REF_IDS[:2]))
    assert result.coverage is SemanticCoverage.PARTIAL
    assert result.semantics == ()
    assert result.reason_code == "partial_missing_values"


def test_projection_invalid_extra_value() -> None:
    snapshot = _snapshot()
    extra = snapshot.conditions[2].model_copy(
        update={
            "condition_id": "cond-applicant-extra",
            "normalized_values": ["not_in_allowed_values"],
            "source_text": "不属于当前选项的说明",
        }
    )
    repository = _repository(
        snapshot.model_copy(update={"conditions": [*snapshot.conditions, extra]})
    )
    result = _project(
        repository,
        refs=_refs(*_REF_IDS, "cond-applicant-extra"),
    )
    assert result.coverage is SemanticCoverage.INVALID
    assert result.reason_code == "invalid_extra_value"
    assert result.semantics == ()


def test_projection_invalid_duplicate_value() -> None:
    snapshot = _snapshot()
    duplicate = snapshot.conditions[0].model_copy(
        update={"condition_id": "cond-applicant-01-dup"}
    )
    repository = _repository(
        snapshot.model_copy(
            update={"conditions": [*snapshot.conditions, duplicate]}
        )
    )
    result = _project(
        repository,
        refs=_refs("cond-applicant-01", "cond-applicant-01-dup"),
    )
    assert result.coverage is SemanticCoverage.INVALID
    assert result.reason_code == "invalid_duplicate_value"
    assert result.semantics == ()


@pytest.mark.parametrize("source_text", ["", "   "])
def test_projection_invalid_blank_meaning(source_text: str) -> None:
    repository = _with_updates({"cond-applicant-01": {"source_text": source_text}})
    result = _project(repository, refs=_refs("cond-applicant-01"))
    assert result.coverage is SemanticCoverage.INVALID
    assert result.reason_code == "invalid_blank_meaning"
    assert result.semantics == ()


def test_projection_invalid_field_mismatch() -> None:
    repository = _with_updates(
        {"cond-applicant-01": {"field": "payment_actor"}}
    )
    result = _project(repository, refs=_refs("cond-applicant-01"))
    assert result.coverage is SemanticCoverage.INVALID
    assert result.reason_code == "invalid_field_mismatch"
    assert result.semantics == ()


@pytest.mark.parametrize(
    "normalized_values",
    [[], ["self_employed_without_employees", "other_flexible_employment"], ["   "], [""]],
)
def test_projection_invalid_normalized_value(
    normalized_values: list[str],
) -> None:
    repository = _with_updates(
        {"cond-applicant-01": {"normalized_values": normalized_values}}
    )
    result = _project(repository, refs=_refs("cond-applicant-01"))
    assert result.coverage is SemanticCoverage.INVALID
    assert result.reason_code == "invalid_normalized_value"
    assert result.semantics == ()


def test_projection_invalid_unapproved_ref_uses_public_filter() -> None:
    repository = _demo_repository()
    internal = repository.get_conditions(
        "DEMO_SS_001",
        consumption=ConsumptionMode.INTERNAL,
    )
    public = repository.get_conditions(
        "DEMO_SS_001",
        consumption=ConsumptionMode.PUBLIC,
    )
    assert any(condition.condition_id == "cond-tc-01" for condition in internal)
    assert all(condition.condition_id != "cond-tc-01" for condition in public)
    result = _project(repository, refs=_refs("cond-tc-01"))
    assert result.coverage is SemanticCoverage.INVALID
    assert result.reason_code == "invalid_unapproved_ref"
    assert result.semantics == ()


def test_repository_source_text_drives_meaning() -> None:
    repository = _with_updates(
        {"cond-applicant-01": {"source_text": "测试含义甲"}}
    )
    result = _project(repository)
    assert result.coverage is SemanticCoverage.FULL
    assert result.semantics[0].value == _A
    assert result.semantics[0].meaning == "测试含义甲"
    assert result.semantics[0].meaning != _MEANINGS[_A]


@pytest.mark.parametrize(
    "payload",
    [
        {"value": "", "meaning": "有含义"},
        {"value": "   ", "meaning": "有含义"},
        {"value": "machine", "meaning": ""},
        {"value": "machine", "meaning": "   "},
    ],
)
def test_semantic_item_rejects_blank(payload: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        ControlledAllowedValueSemantic(**payload)


def test_semantic_item_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        ControlledAllowedValueSemantic.model_validate(
            {"value": "machine", "meaning": "含义", "business_id": "DEMO_SS_001"}
        )


def test_projection_result_invariants() -> None:
    item = ControlledAllowedValueSemantic(value="machine", meaning="含义")
    full = SemanticProjectionResult(
        coverage=SemanticCoverage.FULL,
        semantics=(item,),
        reason_code="full",
    )
    assert full.semantics == (item,)
    for coverage in (
        SemanticCoverage.NONE,
        SemanticCoverage.PARTIAL,
        SemanticCoverage.INVALID,
    ):
        with pytest.raises(ValidationError):
            SemanticProjectionResult(
                coverage=coverage,
                semantics=(item,),
                reason_code="blocked",
            )
    with pytest.raises(ValidationError):
        SemanticProjectionResult(
            coverage=SemanticCoverage.FULL,
            semantics=(),
            reason_code="full",
        )
