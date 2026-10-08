"""F12 SessionTurnService integration with GovernmentAgentTurnProcessor."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import pytest

from gov_service_agent.agent.explanation import (
    ExplanationRequest,
    ExplanationResult,
    ExplanationStatus,
)
from gov_service_agent.agent.interaction import AnswerMapperOutput, AnswerMappingRequest
from gov_service_agent.agent.turn_processor import GovernmentAgentTurnProcessor
from gov_service_agent.agent.workflow import (
    SlotInteractionDependencies,
    TerminalConfirmationDependencies,
)
from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.business_graph.loader import load_decision_graph
from gov_service_agent.retrieval.types import (
    RetrievalCandidate,
    RetrievalResult,
    RetrievalStatus,
)
from gov_service_agent.session.models import (
    AgentTurnResult,
    AuditEvent,
    AuditEventType,
    CachedRequestResult,
    SessionCheckpoint,
    SessionDomainError,
    SessionErrorCode,
    SessionMeta,
    SessionTurnPublicStatus,
    SessionTurnRequest,
)
from gov_service_agent.session.service import SessionTurnService

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GRAPH_PATH = _REPO_ROOT / "data" / "graphs" / "demo" / "social_security.json"
_BUSINESS_PATH = _REPO_ROOT / "data" / "demo" / "demo_ss_001.json"
_INITIAL = "我辞职了，现在没单位，想自己交社保"
_SERVICE_QUESTION = "您主要想办理社保缴费、社保转移，还是查询或其他业务？"
_PAYMENT_QUESTION = "这次社保缴费主要是单位缴，还是您自己缴？"


class MemoryStore:
    """In-memory SessionStore. Does not open a Redis connection."""

    def __init__(self) -> None:
        self.cached: dict[str, CachedRequestResult] = {}
        self.sessions: dict[str, tuple[SessionMeta, SessionCheckpoint]] = {}
        self.audits: dict[str, list[AuditEvent]] = {}
        self.commit_calls = 0
        self.lock_acquires = 0

    class _Lock:
        def __init__(self, owner: "MemoryStore") -> None:
            self._owner = owner

        def acquire(self, blocking: bool = False) -> bool:
            self._owner.lock_acquires += 1
            return True

        def release(self) -> None:
            return None

    def get_cached_result(self, request_id: str) -> CachedRequestResult | None:
        cached = self.cached.get(request_id)
        if cached is None:
            return None
        return CachedRequestResult.model_validate(cached.model_dump(mode="json"))

    def acquire_request_lock(self, request_id: str) -> "_Lock":
        del request_id
        return self._Lock(self)

    def acquire_session_lock(self, session_id: str) -> "_Lock":
        del session_id
        return self._Lock(self)

    def meta_exists(self, session_id: str) -> bool:
        return session_id in self.sessions

    def load_active_session(
        self,
        session_id: str,
        *,
        now: datetime,
    ) -> tuple[SessionMeta, SessionCheckpoint]:
        del now
        meta, checkpoint = self.sessions[session_id]
        return (
            SessionMeta.model_validate(meta.model_dump(mode="json")),
            SessionCheckpoint.model_validate(checkpoint.model_dump(mode="json")),
        )

    def commit_successful_turn(
        self,
        *,
        session_id: str,
        request_id: str,
        expected_revision: int,
        meta: SessionMeta,
        checkpoint: SessionCheckpoint,
        audit_event: AuditEvent,
        cached_result: CachedRequestResult,
    ) -> None:
        del expected_revision
        self.sessions[session_id] = (meta, checkpoint)
        self.audits.setdefault(session_id, []).append(audit_event)
        self.cached[request_id] = cached_result
        self.commit_calls += 1

    def append_failure_audit(self, *, session_id: str, audit_event: AuditEvent) -> None:
        self.audits.setdefault(session_id, []).append(audit_event)


class FakeRetrieval:
    def __init__(self, result: RetrievalResult) -> None:
        self._result = result
        self.queries: list[str | None] = []

    def retrieve(self, query: str | None) -> RetrievalResult:
        self.queries.append(query)
        return self._result


class ScriptedMapper:
    def __init__(self, outputs: list[AnswerMapperOutput | Exception]) -> None:
        self._outputs = list(outputs)
        self.calls = 0

    def map_answer(self, request: AnswerMappingRequest) -> AnswerMapperOutput:
        del request
        self.calls += 1
        item = self._outputs.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class SilentExplanation:
    def explain(self, request: ExplanationRequest) -> ExplanationResult:
        raise AssertionError("explanation must not run in this session test")


def _slot(value: str) -> AnswerMapperOutput:
    from gov_service_agent.agent.interaction import MapperUtteranceKind

    return AnswerMapperOutput(
        kind=MapperUtteranceKind.SLOT_ANSWER,
        mapped_value=value,
        confidence=0.95,
    )


def _processor(
    retrieval: FakeRetrieval,
    mapper: ScriptedMapper,
) -> GovernmentAgentTurnProcessor:
    graph = load_decision_graph(_GRAPH_PATH)
    repository = JsonBusinessRepository.from_paths([_BUSINESS_PATH])
    return GovernmentAgentTurnProcessor(
        decision_graph=graph,
        business_repository=repository,
        retrieval_service=retrieval,  # type: ignore[arg-type]
        slot_dependencies=SlotInteractionDependencies(
            answer_mapper=mapper,
            explanation_service=SilentExplanation(),
            decision_graph=graph,
            business_repository=repository,
        ),
        terminal_dependencies=TerminalConfirmationDependencies(
            business_repository=repository,
        ),
    )


def _request(text: str, session_id: str | None = None, request_id: str | None = None) -> SessionTurnRequest:
    return SessionTurnRequest(
        request_id=request_id or str(uuid.uuid4()),
        session_id=session_id,
        input_text=text,
    )


def _service(
    store: MemoryStore,
    processor: GovernmentAgentTurnProcessor,
) -> SessionTurnService:
    return SessionTurnService(store=store, processor=processor)


def test_new_session_commits_first_pending_question() -> None:
    retrieval = FakeRetrieval(
        RetrievalResult(
            status=RetrievalStatus.CANDIDATES,
            query=_INITIAL,
            candidates=[
                RetrievalCandidate(
                    business_id="DEMO_SS_001",
                    display_name="demo",
                    score=0.9,
                    rank=1,
                    direction="social_security",
                )
            ],
        )
    )
    store = MemoryStore()
    processor = _processor(retrieval, ScriptedMapper([]))
    result = _service(store, processor).handle_turn(_request(_INITIAL))
    assert isinstance(result, AgentTurnResult) is False
    assert result.session_id
    assert result.request_id
    assert result.status is SessionTurnPublicStatus.AWAITING_USER_INPUT
    assert result.requires_user_input is True
    assert result.response_text == _SERVICE_QUESTION
    assert store.commit_calls == 1
    assert store.lock_acquires >= 1
    checkpoint = store.sessions[result.session_id][1]
    persisted = checkpoint.state.model_dump()
    assert set(persisted) == {"phase", "status", "artifacts", "error"}
    assert "input_text" not in persisted
    assert persisted["artifacts"]["f09"]["business_transition"]["required_slot"] == (
        "service_action"
    )
    assert persisted["error"] is None


def test_resume_advances_pending_slot_without_second_retrieval() -> None:
    retrieval = FakeRetrieval(
        RetrievalResult(
            status=RetrievalStatus.CANDIDATES,
            query=_INITIAL,
            candidates=[
                RetrievalCandidate(
                    business_id="DEMO_SS_001",
                    display_name="demo",
                    score=0.9,
                    rank=1,
                    direction="social_security",
                )
            ],
        )
    )
    mapper = ScriptedMapper([_slot("payment")])
    store = MemoryStore()
    service = _service(store, _processor(retrieval, mapper))
    first = service.handle_turn(_request(_INITIAL))
    second = service.handle_turn(
        _request("我想缴费", session_id=first.session_id)
    )
    assert second.session_id == first.session_id
    assert second.response_text == _PAYMENT_QUESTION
    assert retrieval.queries == [_INITIAL]
    assert mapper.calls == 1
    persisted = store.sessions[second.session_id][1].state
    slots = persisted.artifacts["f09"]["slot_context"]["current_slots"]
    assert slots == {"service_action": "payment"}
    assert persisted.artifacts["f09"]["business_transition"]["required_slot"] == (
        "payment_actor"
    )
    assert store.sessions[second.session_id][0].checkpoint_revision == 2


def test_idempotent_replay_does_not_double_advance() -> None:
    retrieval = FakeRetrieval(
        RetrievalResult(
            status=RetrievalStatus.CANDIDATES,
            query=_INITIAL,
            candidates=[
                RetrievalCandidate(
                    business_id="DEMO_SS_001",
                    display_name="demo",
                    score=0.9,
                    rank=1,
                    direction="social_security",
                )
            ],
        )
    )
    mapper = ScriptedMapper([_slot("payment"), _slot("self_payment")])
    store = MemoryStore()
    service = _service(store, _processor(retrieval, mapper))
    first = service.handle_turn(_request(_INITIAL))
    request_id = str(uuid.uuid4())
    accepted = service.handle_turn(
        _request("我想缴费", session_id=first.session_id, request_id=request_id)
    )
    assert accepted.response_text == _PAYMENT_QUESTION
    replay = service.handle_turn(
        _request("我想缴费", session_id=first.session_id, request_id=request_id)
    )
    assert replay.response_text == accepted.response_text
    assert replay.session_id == accepted.session_id
    assert mapper.calls == 1
    assert retrieval.queries == [_INITIAL]
    assert store.commit_calls == 2
    slot = store.sessions[first.session_id][1].state.artifacts["f09"][
        "business_transition"
    ]["required_slot"]
    assert slot == "payment_actor"
    assert store.sessions[first.session_id][0].checkpoint_revision == 2


def test_unavailable_retrieval_does_not_commit_success() -> None:
    retrieval = FakeRetrieval(
        RetrievalResult(status=RetrievalStatus.UNAVAILABLE, query=_INITIAL)
    )
    store = MemoryStore()
    service = _service(store, _processor(retrieval, ScriptedMapper([])))
    with pytest.raises(SessionDomainError) as caught:
        service.handle_turn(_request(_INITIAL))
    assert caught.value.code is SessionErrorCode.AGENT_TURN_FAILED
    assert store.commit_calls == 0
    assert store.sessions == {}
    assert store.audits == {}


def test_failed_follow_up_preserves_prior_checkpoint() -> None:
    retrieval = FakeRetrieval(
        RetrievalResult(
            status=RetrievalStatus.CANDIDATES,
            query=_INITIAL,
            candidates=[
                RetrievalCandidate(
                    business_id="DEMO_SS_001",
                    display_name="demo",
                    score=0.9,
                    rank=1,
                    direction="social_security",
                )
            ],
        )
    )
    mapper = ScriptedMapper([RuntimeError("controlled mapper failure")])
    store = MemoryStore()
    service = _service(store, _processor(retrieval, mapper))
    first = service.handle_turn(_request(_INITIAL))
    revision = store.sessions[first.session_id][0].checkpoint_revision
    saved = store.sessions[first.session_id][1].model_dump(mode="json")
    with pytest.raises(SessionDomainError) as caught:
        service.handle_turn(_request("我想缴费", session_id=first.session_id))
    assert caught.value.code is SessionErrorCode.AGENT_TURN_FAILED
    assert store.commit_calls == 1
    assert store.sessions[first.session_id][0].checkpoint_revision == revision
    assert store.sessions[first.session_id][1].model_dump(mode="json") == saved
    audits = store.audits[first.session_id]
    assert audits[-1].event_type is AuditEventType.TURN_FAILED
    assert store.sessions[first.session_id][1].state.artifacts["f09"][
        "business_transition"
    ]["required_slot"] == "service_action"
