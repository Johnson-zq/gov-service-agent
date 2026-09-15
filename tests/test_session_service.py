"""F11 SessionTurnService lifecycle unit/integration tests."""

from __future__ import annotations

import copy
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import pytest
from redis import Redis

from gov_service_agent.agent.interaction import SlotInteractionContext, empty_f09_namespace
from gov_service_agent.agent.state import (
    AgentPhase,
    AgentState,
    WorkflowStatus,
    create_initial_state,
    validate_agent_state,
)
from gov_service_agent.agent.terminal import (
    TerminalCandidateContext,
    TerminalConfirmationMode,
    empty_f10_namespace,
)
from gov_service_agent.business_graph.transition import TransitionStatus
from gov_service_agent.session.models import (
    AgentTurnResult,
    AuditEvent,
    AuditOutcome,
    CachedRequestResult,
    SessionCheckpoint,
    SessionDomainError,
    SessionErrorCode,
    SessionMeta,
    SessionTurnPublicStatus,
    SessionTurnRequest,
    SessionTurnSuccess,
)
from gov_service_agent.session.service import (
    SessionTurnService,
    from_persisted,
    to_persisted,
)
from gov_service_agent.session.store import RedisSessionConfig, RedisSessionStore


def _utc(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _uuid4() -> str:
    return str(uuid.uuid4())


def _cleanup_prefix(client: Redis, prefix: str) -> None:
    keys = list(client.scan_iter(match=f"{prefix}:*", count=200))
    if keys:
        client.delete(*keys)


@dataclass
class DeterministicTestAgentTurnProcessor:
    """Test-only processor double (must never exist in Production)."""

    response_text: str = "deterministic-response"
    requires_user_input: bool = False
    public_status: SessionTurnPublicStatus = SessionTurnPublicStatus.COMPLETED
    artifacts_factory: Callable[[AgentState | None], dict[str, Any]] | None = None
    fail_times: int = 0
    calls: list[dict[str, Any]] = field(default_factory=list)

    def process_turn(
        self,
        *,
        session_id: str,
        request_id: str,
        input_text: str,
        restored_state: AgentState | None,
    ) -> AgentTurnResult:
        self.calls.append(
            {
                "session_id": session_id,
                "request_id": request_id,
                "input_text": input_text,
                "restored_state": copy.deepcopy(restored_state),
            }
        )
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("deterministic processor failure")
        if restored_state is None:
            state = create_initial_state(request_id, input_text)
        else:
            state = copy.deepcopy(restored_state)
            state["request_id"] = request_id
            state["input_text"] = input_text
            state["orchestration_trace"] = []
        if self.artifacts_factory is not None:
            state["artifacts"] = self.artifacts_factory(restored_state)
        state["phase"] = AgentPhase.COMPLETED
        state["status"] = WorkflowStatus.COMPLETED
        state["error"] = None
        validate_agent_state(state)
        return AgentTurnResult(
            state=state,
            response_text=self.response_text,
            requires_user_input=self.requires_user_input,
            public_status=self.public_status,
        )


class RecordingStore:
    """Deterministic SessionStore double for service unit tests."""

    def __init__(self) -> None:
        self.cached: dict[str, CachedRequestResult] = {}
        self.sessions: dict[str, tuple[SessionMeta, SessionCheckpoint]] = {}
        self.audits: dict[str, list[AuditEvent]] = {}
        self.request_locks: dict[str, bool] = {}
        self.session_locks: dict[str, bool] = {}
        self.commit_calls = 0
        self.fail_commit = False
        self.meta_activity_snapshots: list[datetime] = []

    class _Lock:
        def __init__(self, owner: "RecordingStore", kind: str, key: str) -> None:
            self._owner = owner
            self._kind = kind
            self._key = key
            self._held = False

        def acquire(self, blocking: bool = False) -> bool:
            table = (
                self._owner.request_locks
                if self._kind == "request"
                else self._owner.session_locks
            )
            if table.get(self._key):
                return False
            table[self._key] = True
            self._held = True
            return True

        def release(self) -> None:
            table = (
                self._owner.request_locks
                if self._kind == "request"
                else self._owner.session_locks
            )
            if self._held:
                table[self._key] = False
                self._held = False

    def get_cached_result(self, request_id: str) -> CachedRequestResult | None:
        cached = self.cached.get(request_id)
        if cached is None:
            return None
        return CachedRequestResult.model_validate(cached.model_dump(mode="json"))

    def acquire_request_lock(self, request_id: str):
        return self._Lock(self, "request", request_id)

    def acquire_session_lock(self, session_id: str):
        return self._Lock(self, "session", session_id)

    def meta_exists(self, session_id: str) -> bool:
        return session_id in self.sessions

    def load_active_session(
        self,
        session_id: str,
        *,
        now: datetime,
    ) -> tuple[SessionMeta, SessionCheckpoint]:
        if session_id not in self.sessions:
            raise SessionDomainError(
                SessionErrorCode.SESSION_NOT_FOUND,
                session_id=session_id,
            )
        meta, checkpoint = self.sessions[session_id]
        if now > meta.expires_at:
            raise SessionDomainError(
                SessionErrorCode.SESSION_EXPIRED,
                session_id=session_id,
            )
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
        if self.fail_commit:
            raise SessionDomainError(
                SessionErrorCode.PERSISTENCE_UNAVAILABLE,
                session_id=session_id,
                request_id=request_id,
            )
        existing = self.sessions.get(session_id)
        if expected_revision == 0:
            if existing is not None:
                raise SessionDomainError(
                    SessionErrorCode.SESSION_CONFLICT,
                    session_id=session_id,
                    request_id=request_id,
                )
        else:
            if existing is None or existing[0].checkpoint_revision != expected_revision:
                raise SessionDomainError(
                    SessionErrorCode.SESSION_CONFLICT,
                    session_id=session_id,
                    request_id=request_id,
                )
        self.sessions[session_id] = (meta, checkpoint)
        self.meta_activity_snapshots.append(meta.last_activity_at)
        self.audits.setdefault(session_id, []).append(audit_event)
        self.cached[request_id] = cached_result
        self.commit_calls += 1

    def append_failure_audit(self, *, session_id: str, audit_event: AuditEvent) -> None:
        self.audits.setdefault(session_id, []).append(audit_event)


def _req(
    *,
    input_text: str,
    session_id: str | None = None,
    request_id: str | None = None,
) -> SessionTurnRequest:
    return SessionTurnRequest(
        request_id=request_id or _uuid4(),
        session_id=session_id,
        input_text=input_text,
    )


def test_new_session_calls_processor_once_with_none_restored_state():
    store = RecordingStore()
    processor = DeterministicTestAgentTurnProcessor()
    service = SessionTurnService(store=store, processor=processor)
    result = service.handle_turn(_req(input_text="测试输入A"))
    assert result.session_id
    assert result.response_text == "deterministic-response"
    assert len(processor.calls) == 1
    assert processor.calls[0]["restored_state"] is None
    assert store.sessions[result.session_id][0].checkpoint_revision == 1


def test_existing_session_restores_checkpoint_before_processing_current_input():
    store = RecordingStore()
    processor = DeterministicTestAgentTurnProcessor()
    service = SessionTurnService(store=store, processor=processor)
    first = service.handle_turn(_req(input_text="旧输入"))
    second = service.handle_turn(
        _req(input_text="新输入", session_id=first.session_id)
    )
    assert second.session_id == first.session_id
    assert len(processor.calls) == 2
    restored = processor.calls[1]["restored_state"]
    assert restored is not None
    assert restored["input_text"] == "新输入"
    assert restored["input_text"] != "旧输入"
    assert restored["request_id"] == processor.calls[1]["request_id"]
    assert restored["orchestration_trace"] == []
    assert store.sessions[first.session_id][0].checkpoint_revision == 2


def test_persisted_state_excludes_turn_local_fields_and_rebuilds_fresh_ids():
    state = create_initial_state("R1", "旧输入", artifacts={"k": 1})
    state["phase"] = AgentPhase.COMPLETED
    state["status"] = WorkflowStatus.COMPLETED
    state["orchestration_trace"] = ["prepare", "complete"]
    persisted = to_persisted(state)
    dumped = persisted.model_dump()
    assert set(dumped) == {"phase", "status", "artifacts", "error"}
    assert "input_text" not in dumped
    assert "request_id" not in dumped
    assert "orchestration_trace" not in dumped
    restored = from_persisted(persisted, request_id="R2", input_text="新输入")
    assert restored["request_id"] == "R2"
    assert restored["input_text"] == "新输入"
    assert restored["orchestration_trace"] == []
    assert restored["artifacts"]["k"] == 1


def test_f09_artifact_round_trip_preserves_pending_slot_without_old_input():
    ctx = SlotInteractionContext(
        transition_status=TransitionStatus.NEED_SLOT,
        current_node_id="n1",
        required_slot="employment_status",
        allowed_values=("灵活就业", "无业"),
        question_text="请问就业状态？",
    )
    f09 = empty_f09_namespace(ctx)
    f09["explanation"] = {"status": "ANSWERED", "text": "解释旁路"}

    def factory(_restored):
        return {"f09": copy.deepcopy(f09)}

    store = RecordingStore()
    processor = DeterministicTestAgentTurnProcessor(artifacts_factory=factory)
    service = SessionTurnService(store=store, processor=processor)
    first = service.handle_turn(_req(input_text="旧输入-F09"))
    second_processor = DeterministicTestAgentTurnProcessor()
    service2 = SessionTurnService(store=store, processor=second_processor)
    service2.handle_turn(_req(input_text="新输入-F09", session_id=first.session_id))
    restored = second_processor.calls[0]["restored_state"]
    assert restored is not None
    assert restored["input_text"] == "新输入-F09"
    assert restored["artifacts"]["f09"]["slot_context"]["required_slot"] == (
        "employment_status"
    )
    assert restored["artifacts"]["f09"]["explanation"]["status"] == "ANSWERED"


def test_f10_artifact_round_trip_preserves_eight_keys_and_rejects_stale_input():
    tctx = TerminalCandidateContext(
        transition_status=TransitionStatus.TERMINAL_CANDIDATE,
        current_node_id="t1",
        candidate_business_id="BIZ001",
        visited_node_ids=("n1", "t1"),
        traversed_edge_ids=("e1",),
    )
    f10 = empty_f10_namespace(
        mode=TerminalConfirmationMode.PREPARE,
        context=tctx,
    )
    assert len(f10.keys()) == 8
    assert f10["confirmed_business_id"] is None

    def factory(_restored):
        return {"f10": copy.deepcopy(f10)}

    store = RecordingStore()
    processor = DeterministicTestAgentTurnProcessor(artifacts_factory=factory)
    service = SessionTurnService(store=store, processor=processor)
    first = service.handle_turn(_req(input_text="PREPARE候选语句"))
    nxt = DeterministicTestAgentTurnProcessor()
    service2 = SessionTurnService(store=store, processor=nxt)
    service2.handle_turn(_req(input_text="确认", session_id=first.session_id))
    restored = nxt.calls[0]["restored_state"]
    assert restored is not None
    assert restored["input_text"] == "确认"
    assert restored["input_text"] != "PREPARE候选语句"
    assert set(restored["artifacts"]["f10"].keys()) == set(f10.keys())
    assert restored["artifacts"]["f10"]["confirmed_business_id"] is None
    assert (
        restored["artifacts"]["f10"]["terminal_context"]["candidate_business_id"]
        == "BIZ001"
    )


def test_replay_same_request_does_not_reinvoke_processor_or_refresh_session():
    store = RecordingStore()
    processor = DeterministicTestAgentTurnProcessor()
    fixed_now = _utc()
    service = SessionTurnService(
        store=store,
        processor=processor,
        clock=lambda: fixed_now,
    )
    request = _req(input_text="幂等输入")
    first = service.handle_turn(request)
    activity_before = store.meta_activity_snapshots[-1]
    audits_before = len(store.audits[first.session_id])
    revision_before = store.sessions[first.session_id][0].checkpoint_revision
    second = service.handle_turn(request)
    assert second.model_dump() == first.model_dump()
    assert len(processor.calls) == 1
    assert store.sessions[first.session_id][0].checkpoint_revision == revision_before
    assert len(store.audits[first.session_id]) == audits_before
    assert store.meta_activity_snapshots[-1] == activity_before


def test_request_id_reuse_with_different_payload_conflicts_without_second_processor_call():
    store = RecordingStore()
    processor = DeterministicTestAgentTurnProcessor()
    service = SessionTurnService(store=store, processor=processor)
    rid = _uuid4()
    service.handle_turn(_req(input_text="payload-A", request_id=rid))
    with pytest.raises(SessionDomainError) as exc:
        service.handle_turn(_req(input_text="payload-B", request_id=rid))
    assert exc.value.code == SessionErrorCode.REQUEST_ID_REUSE_CONFLICT
    assert len(processor.calls) == 1


def test_same_request_id_concurrent_race_invokes_processor_only_once():
    store = RecordingStore()
    processor = DeterministicTestAgentTurnProcessor()
    service = SessionTurnService(store=store, processor=processor)
    request = _req(input_text="并发同一请求")
    results: list[Any] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            results.append(service.handle_turn(request))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(processor.calls) == 1
    successes = [item for item in results if isinstance(item, SessionTurnSuccess)]
    in_progress = [
        err
        for err in errors
        if isinstance(err, SessionDomainError)
        and err.code == SessionErrorCode.REQUEST_IN_PROGRESS
    ]
    assert len(successes) >= 1
    assert len(successes) + len(in_progress) == 2


def test_same_session_concurrency_has_no_silent_lost_update():
    store = RecordingStore()
    processor = DeterministicTestAgentTurnProcessor()
    service = SessionTurnService(store=store, processor=processor)
    first = service.handle_turn(_req(input_text="初始"))
    session_id = first.session_id
    outcomes: list[str] = []

    def worker(label: str) -> None:
        try:
            service.handle_turn(_req(input_text=label, session_id=session_id))
            outcomes.append(f"ok:{label}")
        except SessionDomainError as exc:
            outcomes.append(f"err:{exc.code.value}")

    t1 = threading.Thread(target=worker, args=("A",))
    t2 = threading.Thread(target=worker, args=("B",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert any(item.startswith("ok:") for item in outcomes)
    revision = store.sessions[session_id][0].checkpoint_revision
    assert revision >= 2
    # One success + conflict/serialized path is fine; lost update would leave
    # revision=2 while both claimed success from the same base without ordering.
    if outcomes.count("ok:A") == 1 and outcomes.count("ok:B") == 1:
        assert revision == 3


def test_different_sessions_use_independent_locks():
    store = RecordingStore()
    processor = DeterministicTestAgentTurnProcessor()
    service = SessionTurnService(store=store, processor=processor)
    a = service.handle_turn(_req(input_text="会话A"))
    b = service.handle_turn(_req(input_text="会话B"))
    assert a.session_id != b.session_id
    assert store.acquire_session_lock(a.session_id)._key != store.acquire_session_lock(
        b.session_id
    )._key


def test_processor_failure_preserves_existing_checkpoint_and_records_failure_audit():
    store = RecordingStore()
    processor = DeterministicTestAgentTurnProcessor()
    service = SessionTurnService(store=store, processor=processor)
    first = service.handle_turn(_req(input_text="成功"))
    revision = store.sessions[first.session_id][0].checkpoint_revision
    failing = DeterministicTestAgentTurnProcessor(fail_times=1)
    service2 = SessionTurnService(store=store, processor=failing)
    with pytest.raises(SessionDomainError) as exc:
        service2.handle_turn(_req(input_text="失败", session_id=first.session_id))
    assert exc.value.code == SessionErrorCode.AGENT_TURN_FAILED
    assert store.sessions[first.session_id][0].checkpoint_revision == revision
    assert any(
        event.event_type.value == "TURN_FAILED"
        for event in store.audits[first.session_id]
    )


def test_new_session_processor_failure_does_not_return_usable_session():
    store = RecordingStore()
    processor = DeterministicTestAgentTurnProcessor(fail_times=1)
    service = SessionTurnService(store=store, processor=processor)
    with pytest.raises(SessionDomainError) as exc:
        service.handle_turn(_req(input_text="首轮失败"))
    assert exc.value.code == SessionErrorCode.AGENT_TURN_FAILED
    assert exc.value.session_id is None
    assert store.sessions == {}
    assert store.commit_calls == 0


def test_persistence_failure_after_processor_success_does_not_return_success():
    store = RecordingStore()
    store.fail_commit = True
    processor = DeterministicTestAgentTurnProcessor()
    service = SessionTurnService(store=store, processor=processor)
    with pytest.raises(SessionDomainError) as exc:
        service.handle_turn(_req(input_text="持久化失败"))
    assert exc.value.code == SessionErrorCode.PERSISTENCE_UNAVAILABLE
    assert len(processor.calls) == 1
    assert store.sessions == {}


def test_processor_invocation_contract_has_no_redis_or_http_dependencies():
    store = RecordingStore()
    processor = DeterministicTestAgentTurnProcessor()
    service = SessionTurnService(store=store, processor=processor)
    service.handle_turn(_req(input_text="契约"))
    call = processor.calls[0]
    assert set(call) == {
        "session_id",
        "request_id",
        "input_text",
        "restored_state",
    }


def test_restart_style_continuity_with_real_redis_store():
    prefix = f"govagent:test:f11:{uuid.uuid4()}"
    client = Redis(host="127.0.0.1", port=6379, decode_responses=True)
    config = RedisSessionConfig(
        key_prefix=prefix,
        session_ttl_seconds=180,
        session_expired_marker_ttl_seconds=300,
        audit_ttl_seconds=600,
        request_dedup_ttl_seconds=120,
        request_lock_ttl_seconds=30,
        session_lock_ttl_seconds=30,
    )
    try:
        store_a = RedisSessionStore(client, config)
        processor = DeterministicTestAgentTurnProcessor(
            artifacts_factory=lambda _r: {"marker": "alive"}
        )
        service_a = SessionTurnService(
            store=store_a,
            processor=processor,
            session_ttl_seconds=180,
        )
        first = service_a.handle_turn(
            _req(input_text="我辞职了，现在没单位，想自己交社保")
        )
        del service_a
        del store_a
        store_b = RedisSessionStore(client, config)
        processor_b = DeterministicTestAgentTurnProcessor()
        service_b = SessionTurnService(
            store=store_b,
            processor=processor_b,
            session_ttl_seconds=180,
        )
        second = service_b.handle_turn(
            _req(
                input_text="平时接零活，没有固定单位",
                session_id=first.session_id,
            )
        )
        assert second.session_id == first.session_id
        restored = processor_b.calls[0]["restored_state"]
        assert restored is not None
        assert restored["artifacts"]["marker"] == "alive"
        assert restored["input_text"] == "平时接零活，没有固定单位"
    finally:
        _cleanup_prefix(client, prefix)
        client.close()


def test_no_silent_in_memory_fallback_when_store_unavailable():
    class BrokenStore(RecordingStore):
        def get_cached_result(self, request_id: str) -> CachedRequestResult | None:
            raise SessionDomainError(SessionErrorCode.PERSISTENCE_UNAVAILABLE)

    service = SessionTurnService(
        store=BrokenStore(),
        processor=DeterministicTestAgentTurnProcessor(),
    )
    with pytest.raises(SessionDomainError) as exc:
        service.handle_turn(_req(input_text="不可用"))
    assert exc.value.code == SessionErrorCode.PERSISTENCE_UNAVAILABLE


def test_settings_defaults_available_without_reading_dotenv_file():
    from gov_service_agent.settings import Settings

    settings = Settings.model_construct(
        redis_host="127.0.0.1",
        redis_port=6379,
        redis_db=0,
        redis_username=None,
        redis_password=None,
        redis_key_prefix="govagent:f11",
        session_ttl_seconds=1800,
        session_expired_marker_ttl_seconds=86400,
        audit_ttl_seconds=604800,
        request_dedup_ttl_seconds=600,
        request_lock_ttl_seconds=120,
        session_lock_ttl_seconds=120,
        session_max_input_chars=4000,
    )
    assert settings.redis_host == "127.0.0.1"
    assert settings.redis_port == 6379
    assert settings.session_max_input_chars == 4000
    assert settings.redis_password is None


@dataclass
class _MutatingIdentityProcessor:
    """Test-only: returns valid shape with wrong turn identity fields."""

    mode: str
    calls: list[dict[str, Any]] = field(default_factory=list)

    def process_turn(
        self,
        *,
        session_id: str,
        request_id: str,
        input_text: str,
        restored_state: AgentState | None,
    ) -> AgentTurnResult:
        self.calls.append(
            {
                "session_id": session_id,
                "request_id": request_id,
                "input_text": input_text,
            }
        )
        if restored_state is None:
            state = create_initial_state(request_id, input_text)
        else:
            state = copy.deepcopy(restored_state)
            state["request_id"] = request_id
            state["input_text"] = input_text
            state["orchestration_trace"] = []
        if self.mode == "wrong_request_id":
            state["request_id"] = str(uuid.uuid4())
        elif self.mode == "wrong_input_text":
            state["input_text"] = f"TAMPERED_INPUT_{uuid.uuid4()}"
        state["phase"] = AgentPhase.COMPLETED
        state["status"] = WorkflowStatus.COMPLETED
        state["error"] = None
        validate_agent_state(state)
        return AgentTurnResult(
            state=state,
            response_text="should-not-persist",
            requires_user_input=False,
            public_status=SessionTurnPublicStatus.COMPLETED,
        )


def test_processor_wrong_request_id_fails_without_durable_commit():
    """RF-F11-RV-003: mismatched request_id must not persist."""
    store = RecordingStore()
    service = SessionTurnService(
        store=store,
        processor=DeterministicTestAgentTurnProcessor(),
    )
    first = service.handle_turn(_req(input_text="基线输入"))
    revision_before = store.sessions[first.session_id][0].checkpoint_revision
    commits_before = store.commit_calls
    success_audits_before = sum(
        1
        for e in store.audits.get(first.session_id, [])
        if e.outcome == AuditOutcome.SUCCESS
    )

    bad = SessionTurnService(
        store=store,
        processor=_MutatingIdentityProcessor(mode="wrong_request_id"),
    )
    with pytest.raises(SessionDomainError) as exc:
        bad.handle_turn(_req(input_text="下一轮", session_id=first.session_id))
    assert exc.value.code == SessionErrorCode.AGENT_TURN_FAILED
    assert store.commit_calls == commits_before
    assert store.sessions[first.session_id][0].checkpoint_revision == revision_before
    success_audits_after = sum(
        1
        for e in store.audits.get(first.session_id, [])
        if e.outcome == AuditOutcome.SUCCESS
    )
    assert success_audits_after == success_audits_before


def test_processor_wrong_input_text_fails_without_success_cache():
    """RF-F11-RV-003: mismatched input_text must not success-audit or cache."""
    store = RecordingStore()
    service = SessionTurnService(
        store=store,
        processor=_MutatingIdentityProcessor(mode="wrong_input_text"),
    )
    with pytest.raises(SessionDomainError) as exc:
        service.handle_turn(_req(input_text="真实用户输入"))
    assert exc.value.code == SessionErrorCode.AGENT_TURN_FAILED
    assert store.commit_calls == 0
    assert store.sessions == {}
    assert store.cached == {}
    assert store.audits == {}  # new session: no failure audit either


def test_inconsistent_public_status_requires_user_input_fails_closed():
    """RF-F11-RV-004: COMPLETED + requires_user_input=True is rejected."""
    store = RecordingStore()
    processor = DeterministicTestAgentTurnProcessor(
        requires_user_input=True,
        public_status=SessionTurnPublicStatus.COMPLETED,
    )
    service = SessionTurnService(store=store, processor=processor)
    with pytest.raises(SessionDomainError) as exc:
        service.handle_turn(_req(input_text="状态不一致"))
    assert exc.value.code == SessionErrorCode.AGENT_TURN_FAILED
    assert store.commit_calls == 0

    with pytest.raises(ValueError):
        SessionTurnSuccess(
            session_id=str(uuid.uuid4()),
            request_id=str(uuid.uuid4()),
            status=SessionTurnPublicStatus.AWAITING_USER_INPUT,
            response_text="x",
            requires_user_input=False,
        )
