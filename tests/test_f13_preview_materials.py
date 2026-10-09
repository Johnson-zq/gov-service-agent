"""F13-Preview wrapper tests. No Redis, PostgreSQL, embedding, LLM, or network."""

from __future__ import annotations

import ast
import copy
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from gov_service_agent.agent.materials_preview import (
    ConfirmedBusinessMaterialsPreviewProcessor,
)
from gov_service_agent.agent.state import (
    AgentPhase,
    AgentState,
    WorkflowStatus,
    validate_agent_state,
)
from gov_service_agent.business_data.models import (
    VerificationStatus,
    load_snapshot,
)
from gov_service_agent.business_data.repository import (
    BusinessNotFoundError,
    JsonBusinessRepository,
)
from gov_service_agent.session.models import (
    AgentTurnResult,
    SessionTurnPublicStatus,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEMO_PATH = _REPO_ROOT / "data" / "demo" / "demo_ss_001.json"
_BASE_RESPONSE = "事项已确认。"
_CANONICAL_NAME = "灵活就业人员社会保险费申报缴费"
_PUBLIC_MATERIAL = "身份证"
_HIDDEN_MATERIAL = "内部草稿材料"
_UNSAFE_PHRASES = (
    "全部材料",
    "仅需以下材料",
    "材料完整",
    "保证可以办理",
)


class SentinelError(RuntimeError):
    """Base-processor failure that must propagate unchanged."""


class FakeBase:
    def __init__(
        self,
        *,
        state: AgentState,
        response_text: str = _BASE_RESPONSE,
        error: BaseException | None = None,
    ) -> None:
        self._state = state
        self._response_text = response_text
        self._error = error
        self.calls = 0

    def process_turn(
        self,
        *,
        session_id: str,
        request_id: str,
        input_text: str,
        restored_state: AgentState | None,
    ) -> AgentTurnResult:
        del session_id, restored_state
        self.calls += 1
        if self._error is not None:
            raise self._error
        state = copy.deepcopy(self._state)
        state["request_id"] = request_id
        state["input_text"] = input_text
        return AgentTurnResult(
            state=validate_agent_state(state),
            response_text=self._response_text,
            requires_user_input=False,
            public_status=SessionTurnPublicStatus.COMPLETED,
        )


class CountingRepository:
    def __init__(self, inner: JsonBusinessRepository) -> None:
        self._inner = inner
        self.business_ids: list[str] = []
        self.material_ids: list[str] = []

    def get_business(self, business_id: str):  # type: ignore[no-untyped-def]
        self.business_ids.append(business_id)
        return self._inner.get_business(business_id)

    def get_materials(self, business_id: str):  # type: ignore[no-untyped-def]
        self.material_ids.append(business_id)
        return self._inner.get_materials(business_id)


class RaisingRepository:
    def __init__(self, error: BaseException) -> None:
        self._error = error
        self.calls = 0

    def get_business(self, business_id: str):  # type: ignore[no-untyped-def]
        del business_id
        self.calls += 1
        raise self._error

    def get_materials(self, business_id: str):  # type: ignore[no-untyped-def]
        del business_id
        self.calls += 1
        raise self._error


def _state(confirmed: str | None, **artifacts: object) -> AgentState:
    f10: dict[str, object] = {"candidate_business_id": "DEMO_SS_001"}
    if confirmed is not None:
        f10["confirmed_business_id"] = confirmed
    else:
        f10["confirmed_business_id"] = None
    payload = {
        "f09": {
            "validated_slots": {"employment_type": "self_employed_without_employees"},
            "business_transition": None,
        },
        "f10": f10,
    }
    payload.update(artifacts)
    return validate_agent_state(
        {
            "request_id": "req-template",
            "input_text": "template",
            "phase": AgentPhase.COMPLETED,
            "status": WorkflowStatus.COMPLETED,
            "artifacts": payload,
            "error": None,
            "orchestration_trace": [],
        }
    )


def _preview(
    base: FakeBase,
    repository: object,
) -> ConfirmedBusinessMaterialsPreviewProcessor:
    return ConfirmedBusinessMaterialsPreviewProcessor(
        base_processor=base,  # type: ignore[arg-type]
        business_repository=repository,  # type: ignore[arg-type]
    )


def _turn(
    processor: ConfirmedBusinessMaterialsPreviewProcessor,
    restored: AgentState | None,
) -> AgentTurnResult:
    return processor.process_turn(
        session_id="session-1",
        request_id="request-1",
        input_text="确认",
        restored_state=restored,
    )


def test_first_confirmation_appends_public_materials() -> None:
    """T-F13P-001."""
    repository = CountingRepository(JsonBusinessRepository.from_paths([_DEMO_PATH]))
    after = _state("DEMO_SS_001")
    expected_state = copy.deepcopy(after)
    expected_state["request_id"] = "request-1"
    expected_state["input_text"] = "确认"
    base = FakeBase(state=after)
    result = _turn(_preview(base, repository), None)

    assert base.calls == 1
    assert repository.business_ids == ["DEMO_SS_001"]
    assert repository.material_ids == ["DEMO_SS_001"]
    assert result.response_text.startswith(f"{_BASE_RESPONSE}\n\n")
    assert f"办理事项：{_CANONICAL_NAME}" in result.response_text
    assert "需要准备的材料：" in result.response_text
    assert f"1. {_PUBLIC_MATERIAL}" in result.response_text
    assert result.requires_user_input is False
    assert result.public_status is SessionTurnPublicStatus.COMPLETED
    assert result.state == expected_state
    assert "mat-id-card" not in result.response_text
    assert "SOURCE_EXPLICIT" not in result.response_text
    assert "DEMO_SS_001" not in result.response_text


def test_prepare_does_not_lookup_materials() -> None:
    """T-F13P-002."""
    repository = CountingRepository(JsonBusinessRepository.from_paths([_DEMO_PATH]))
    base = FakeBase(state=_state(None))
    result = _turn(_preview(base, repository), None)
    assert base.calls == 1
    assert repository.business_ids == []
    assert repository.material_ids == []
    assert result.response_text == _BASE_RESPONSE


def test_already_confirmed_does_not_repeat_materials() -> None:
    """T-F13P-003."""
    repository = CountingRepository(JsonBusinessRepository.from_paths([_DEMO_PATH]))
    confirmed = _state("DEMO_SS_001")
    base = FakeBase(state=confirmed)
    result = _turn(_preview(base, repository), confirmed)
    assert repository.business_ids == []
    assert repository.material_ids == []
    assert result.response_text == _BASE_RESPONSE


def test_low_confidence_does_not_preview() -> None:
    """T-F13P-004."""
    repository = CountingRepository(JsonBusinessRepository.from_paths([_DEMO_PATH]))
    base = FakeBase(state=_state(None, f09={"mapping_validation": "low_confidence"}))
    result = _turn(_preview(base, repository), None)
    assert repository.material_ids == []
    assert result.response_text == _BASE_RESPONSE


def test_explanation_request_does_not_preview() -> None:
    """T-F13P-005."""
    repository = CountingRepository(JsonBusinessRepository.from_paths([_DEMO_PATH]))
    base = FakeBase(
        state=_state(None, f09={"interpretation": "explanation_request"})
    )
    result = _turn(_preview(base, repository), None)
    assert repository.material_ids == []
    assert result.response_text == _BASE_RESPONSE


def test_empty_public_materials_appends_controlled_message() -> None:
    """T-F13P-006."""
    snapshot = load_snapshot(_DEMO_PATH)
    empty = snapshot.model_copy(update={"materials": []})
    repository = JsonBusinessRepository({snapshot.business.business_id: empty})
    result = _turn(_preview(FakeBase(state=_state("DEMO_SS_001")), repository), None)
    assert result.response_text.startswith(f"{_BASE_RESPONSE}\n\n")
    assert f"办理事项：{_CANONICAL_NAME}" in result.response_text
    assert "当前暂无可展示的办理材料信息。" in result.response_text
    assert "需要准备的材料：" not in result.response_text
    assert result.state["artifacts"]["f10"]["confirmed_business_id"] == "DEMO_SS_001"  # type: ignore[index]


def test_non_public_material_stays_out_of_response() -> None:
    """T-F13P-007. Display follows repository public results."""
    snapshot = load_snapshot(_DEMO_PATH)
    hidden = snapshot.materials[0].model_copy(
        update={
            "material_id": "mat-hidden",
            "source_text": _HIDDEN_MATERIAL,
            "requirement_level_status": VerificationStatus.TO_CONFIRM,
        }
    )
    mixed = snapshot.model_copy(
        update={"materials": [*snapshot.materials, hidden]}
    )
    repository = JsonBusinessRepository({snapshot.business.business_id: mixed})
    public_texts = [
        item.source_text
        for item in repository.get_materials(snapshot.business.business_id)
    ]
    assert _PUBLIC_MATERIAL in public_texts
    assert _HIDDEN_MATERIAL not in public_texts
    result = _turn(
        _preview(FakeBase(state=_state(snapshot.business.business_id)), repository),
        None,
    )
    for text in public_texts:
        assert text in result.response_text
    assert _HIDDEN_MATERIAL not in result.response_text


def test_repository_exception_returns_base_result() -> None:
    """T-F13P-008."""
    repository = RaisingRepository(RuntimeError("lookup failed"))
    after = _state("DEMO_SS_001")
    expected_state = copy.deepcopy(after)
    expected_state["request_id"] = "request-1"
    expected_state["input_text"] = "确认"
    result = _turn(_preview(FakeBase(state=after), repository), None)
    assert result.response_text == _BASE_RESPONSE
    assert result.state == expected_state
    assert result.state["artifacts"]["f10"]["confirmed_business_id"] == "DEMO_SS_001"  # type: ignore[index]


def test_unknown_business_returns_base_result() -> None:
    """T-F13P-009."""
    repository = RaisingRepository(BusinessNotFoundError("unknown business_id"))
    result = _turn(_preview(FakeBase(state=_state("UNLISTED_ID")), repository), None)
    assert result.response_text == _BASE_RESPONSE
    assert "UNLISTED_ID" not in result.response_text
    assert _CANONICAL_NAME not in result.response_text
    assert _PUBLIC_MATERIAL not in result.response_text


def test_base_processor_exception_propagates() -> None:
    """T-F13P-010."""
    repository = CountingRepository(JsonBusinessRepository.from_paths([_DEMO_PATH]))
    base = FakeBase(state=_state("DEMO_SS_001"), error=SentinelError("base failed"))
    with pytest.raises(SentinelError, match="base failed"):
        _turn(_preview(base, repository), None)
    assert base.calls == 1
    assert repository.business_ids == []
    assert repository.material_ids == []


def test_successful_preview_does_not_change_business_state() -> None:
    """T-F13P-011."""
    repository = JsonBusinessRepository.from_paths([_DEMO_PATH])
    after = _state("DEMO_SS_001")
    expected_state = copy.deepcopy(after)
    expected_state["request_id"] = "request-1"
    expected_state["input_text"] = "确认"
    result = _turn(_preview(FakeBase(state=after), repository), None)
    assert result.state["artifacts"]["f09"] == expected_state["artifacts"]["f09"]
    assert result.state["artifacts"]["f10"] == expected_state["artifacts"]["f10"]
    assert result.state == expected_state


def test_preview_has_no_llm_or_retrieval_dependency() -> None:
    """T-F13P-012 and T-F13P-013."""
    source = inspect.getsource(
        __import__(
            "gov_service_agent.agent.materials_preview",
            fromlist=["ConfirmedBusinessMaterialsPreviewProcessor"],
        )
    )
    imported: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    joined = " ".join(imported).lower()
    assert "llm" not in joined
    assert "retrieval" not in joined
    assert "embedding" not in joined
    repository = CountingRepository(JsonBusinessRepository.from_paths([_DEMO_PATH]))
    _turn(_preview(FakeBase(state=_state("DEMO_SS_001")), repository), None)
    assert repository.business_ids == ["DEMO_SS_001"]


def test_material_order_follows_repository_order() -> None:
    repository = SimpleNamespace(
        get_business=lambda business_id: SimpleNamespace(canonical_name="测试事项"),
        get_materials=lambda business_id: [
            SimpleNamespace(source_text="甲材料"),
            SimpleNamespace(source_text="乙材料"),
        ],
    )
    result = _turn(
        _preview(FakeBase(state=_state("OTHER_ID"), response_text=""), repository),
        None,
    )
    assert result.response_text == (
        "办理事项：测试事项\n需要准备的材料：\n1. 甲材料\n2. 乙材料"
    )
    for phrase in _UNSAFE_PHRASES:
        assert phrase not in result.response_text


def test_non_empty_base_response_is_exact_prefix() -> None:
    repository = SimpleNamespace(
        get_business=lambda business_id: SimpleNamespace(canonical_name="测试事项"),
        get_materials=lambda business_id: [],
    )
    original = "  保持原文空格  "
    result = _turn(
        _preview(
            FakeBase(state=_state("OTHER_ID"), response_text=original),
            repository,
        ),
        None,
    )
    assert result.response_text.startswith(original + "\n\n")
    assert "当前暂无可展示的办理材料信息。" in result.response_text


def test_confirmed_id_change_does_not_preview() -> None:
    repository = CountingRepository(JsonBusinessRepository.from_paths([_DEMO_PATH]))
    result = _turn(
        _preview(FakeBase(state=_state("OTHER_ID")), repository),
        _state("DEMO_SS_001"),
    )
    assert repository.material_ids == []
    assert result.response_text == _BASE_RESPONSE


def test_blank_canonical_name_fail_soft() -> None:
    repository = SimpleNamespace(
        get_business=lambda business_id: SimpleNamespace(canonical_name="  "),
        get_materials=lambda business_id: [],
    )
    result = _turn(_preview(FakeBase(state=_state("OTHER_ID")), repository), None)
    assert result.response_text == _BASE_RESPONSE
