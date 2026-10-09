"""F13-Preview session integration. In-memory store only; no real Redis."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gov_service_agent.agent.materials_preview import (
    ConfirmedBusinessMaterialsPreviewProcessor,
)
from gov_service_agent.agent.state import (
    AgentPhase,
    AgentState,
    WorkflowStatus,
    validate_agent_state,
)
from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.session.models import (
    AgentTurnResult,
    AuditEvent,
    CachedRequestResult,
    PersistedAgentState,
    SessionCheckpoint,
    SessionMeta,
    SessionTurnPublicStatus,
    SessionTurnRequest,
)
from gov_service_agent.session.service import SessionTurnService

_DEMO = Path(__file__).resolve().parents[1] / "data" / "demo" / "demo_ss_001.json"
_BASE_RESPONSE = "事项已确认。"


class MemoryStore:
    """In-memory SessionStore. Does not open a Redis connection."""

    def __init__(self) -> None:
        self.cached: dict[str, CachedRequestResult] = {}
        self.sessions: dict[str, tuple[SessionMeta, SessionCheckpoint]] = {}
        self.audits: dict[str, list[AuditEvent]] = {}
        self.commit_calls = 0

    class _Lock:
        def acquire(self, blocking: bool = False) -> bool:
            del blocking
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
        return self._Lock()

    def acquire_session_lock(self, session_id: str) -> "_Lock":
        del session_id
        return self._Lock()

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


class FakeBase:
    def __init__(self, *, confirmed_business_id: str) -> None:
        self.confirmed_business_id = confirmed_business_id
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
        state = validate_agent_state(
            {
                "request_id": request_id,
                "input_text": input_text,
                "phase": AgentPhase.COMPLETED,
                "status": WorkflowStatus.COMPLETED,
                "artifacts": {
                    "f10": {
                        "candidate_business_id": self.confirmed_business_id,
                        "confirmed_business_id": self.confirmed_business_id,
                    }
                },
                "error": None,
                "orchestration_trace": [],
            }
        )
        return AgentTurnResult(
            state=state,
            response_text=_BASE_RESPONSE,
            requires_user_input=False,
            public_status=SessionTurnPublicStatus.COMPLETED,
        )


class BrokenRepository:
    def __init__(self) -> None:
        self.calls = 0

    def get_business(self, business_id: str):  # type: ignore[no-untyped-def]
        del business_id
        self.calls += 1
        raise RuntimeError("preview lookup failed")

    def get_materials(self, business_id: str):  # type: ignore[no-untyped-def]
        del business_id
        self.calls += 1
        raise RuntimeError("preview lookup failed")


def _seed_unconfirmed(store: MemoryStore, session_id: str) -> None:
    now = datetime(2026, 10, 9, 4, 0, tzinfo=timezone.utc)
    meta = SessionMeta(
        session_id=session_id,
        created_at=now,
        last_activity_at=now,
        expires_at=now + timedelta(hours=1),
        checkpoint_revision=1,
    )
    checkpoint = SessionCheckpoint(
        session_id=session_id,
        revision=1,
        saved_at=now,
        state=PersistedAgentState(
            phase="completed",
            status="completed",
            artifacts={"f10": {"confirmed_business_id": None}},
        ),
    )
    store.sessions[session_id] = (meta, checkpoint)


def _service(
    store: MemoryStore,
    processor: ConfirmedBusinessMaterialsPreviewProcessor,
) -> SessionTurnService:
    return SessionTurnService(store=store, processor=processor)


def _request(session_id: str, request_id: str) -> SessionTurnRequest:
    return SessionTurnRequest(
        request_id=request_id,
        session_id=session_id,
        input_text="确认",
    )


def test_first_confirmation_response_includes_materials_without_new_artifact() -> None:
    store = MemoryStore()
    session_id = str(uuid.uuid4())
    _seed_unconfirmed(store, session_id)
    base = FakeBase(confirmed_business_id="DEMO_SS_001")
    repository = JsonBusinessRepository.from_paths([_DEMO])
    processor = ConfirmedBusinessMaterialsPreviewProcessor(
        base_processor=base,  # type: ignore[arg-type]
        business_repository=repository,
    )
    success = _service(store, processor).handle_turn(
        _request(session_id, str(uuid.uuid4()))
    )
    assert success.response_text.startswith(f"{_BASE_RESPONSE}\n\n")
    assert "办理事项：灵活就业人员社会保险费申报缴费" in success.response_text
    assert "1. 身份证" in success.response_text
    checkpoint = store.sessions[session_id][1]
    artifacts = checkpoint.state.artifacts
    assert artifacts["f10"]["confirmed_business_id"] == "DEMO_SS_001"
    assert "f13_preview" not in artifacts
    assert store.commit_calls == 1


def test_idempotent_replay_does_not_run_processor_again() -> None:
    """T-F13P-015."""
    store = MemoryStore()
    session_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    _seed_unconfirmed(store, session_id)
    base = FakeBase(confirmed_business_id="DEMO_SS_001")
    processor = ConfirmedBusinessMaterialsPreviewProcessor(
        base_processor=base,  # type: ignore[arg-type]
        business_repository=JsonBusinessRepository.from_paths([_DEMO]),
    )
    service = _service(store, processor)
    first = service.handle_turn(_request(session_id, request_id))
    second = service.handle_turn(_request(session_id, request_id))
    assert second.response_text == first.response_text
    assert "身份证" in second.response_text
    assert base.calls == 1
    assert store.commit_calls == 1


def test_preview_lookup_failure_still_commits_base_success() -> None:
    store = MemoryStore()
    session_id = str(uuid.uuid4())
    _seed_unconfirmed(store, session_id)
    base = FakeBase(confirmed_business_id="DEMO_SS_001")
    processor = ConfirmedBusinessMaterialsPreviewProcessor(
        base_processor=base,  # type: ignore[arg-type]
        business_repository=BrokenRepository(),  # type: ignore[arg-type]
    )
    success = _service(store, processor).handle_turn(
        _request(session_id, str(uuid.uuid4()))
    )
    assert success.response_text == _BASE_RESPONSE
    artifacts = store.sessions[session_id][1].state.artifacts
    assert artifacts["f10"]["confirmed_business_id"] == "DEMO_SS_001"
    assert store.commit_calls == 1
    assert copy.deepcopy(artifacts)["f10"]["confirmed_business_id"] == "DEMO_SS_001"
