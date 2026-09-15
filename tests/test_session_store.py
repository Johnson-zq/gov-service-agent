"""F11 RedisSessionStore integration tests against local Redis 7.4.11."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.lock import Lock

from gov_service_agent.agent.state import AgentPhase, WorkflowStatus
from gov_service_agent.session.models import (
    AuditEvent,
    AuditEventType,
    AuditOutcome,
    CachedRequestResult,
    PersistedAgentState,
    SessionCheckpoint,
    SessionDomainError,
    SessionErrorCode,
    SessionMeta,
    SessionTurnPublicStatus,
    SessionTurnSuccess,
)
from gov_service_agent.session.store import RedisSessionConfig, RedisSessionStore, dumps_json


def _utc(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _cleanup_prefix(client: Redis, prefix: str) -> None:
    keys = list(client.scan_iter(match=f"{prefix}:*", count=200))
    if keys:
        client.delete(*keys)


@pytest.fixture
def redis_bundle():
    prefix = f"govagent:test:f11:{uuid.uuid4()}"
    assert not prefix.startswith("govagent:f11:")
    client = Redis(host="127.0.0.1", port=6379, decode_responses=True)
    config = RedisSessionConfig(
        key_prefix=prefix,
        session_ttl_seconds=120,
        session_expired_marker_ttl_seconds=300,
        audit_ttl_seconds=600,
        request_dedup_ttl_seconds=90,
        request_lock_ttl_seconds=30,
        session_lock_ttl_seconds=30,
    )
    store = RedisSessionStore(client, config)
    try:
        yield client, store, prefix, config
    finally:
        try:
            _cleanup_prefix(client, prefix)
        except Exception as exc:  # noqa: BLE001 - must surface teardown failure
            client.close()
            raise AssertionError(f"Redis test prefix cleanup failed: {exc}") from exc
        client.close()


def _persisted(artifacts: dict[str, Any] | None = None) -> PersistedAgentState:
    return PersistedAgentState(
        phase=AgentPhase.COMPLETED.value,
        status=WorkflowStatus.COMPLETED.value,
        artifacts=artifacts or {"note": "controlled"},
        error=None,
    )


def _commit_success(
    store: RedisSessionStore,
    *,
    session_id: str,
    request_id: str,
    expected_revision: int,
    revision: int,
    now: datetime,
    artifacts: dict[str, Any] | None = None,
    response_text: str = "ok",
) -> tuple[SessionMeta, SessionCheckpoint, AuditEvent, CachedRequestResult]:
    created_at = now if expected_revision == 0 else now - timedelta(minutes=1)
    meta = SessionMeta(
        session_id=session_id,
        created_at=created_at,
        last_activity_at=now,
        expires_at=now + timedelta(seconds=120),
        checkpoint_revision=revision,
    )
    checkpoint = SessionCheckpoint(
        session_id=session_id,
        revision=revision,
        saved_at=now,
        state=_persisted(artifacts),
    )
    audit = AuditEvent(
        event_id=str(uuid.uuid4()),
        session_id=session_id,
        request_id=request_id,
        occurred_at=now,
        event_type=AuditEventType.TURN_COMPLETED,
        outcome=AuditOutcome.SUCCESS,
        before_phase=None if expected_revision == 0 else AgentPhase.COMPLETED.value,
        before_status=None if expected_revision == 0 else WorkflowStatus.COMPLETED.value,
        after_phase=AgentPhase.COMPLETED.value,
        after_status=WorkflowStatus.COMPLETED.value,
        checkpoint_revision_before=None if expected_revision == 0 else expected_revision,
        checkpoint_revision_after=revision,
        failure_code=None,
        capability="SESSION_TURN",
    )
    success = SessionTurnSuccess(
        session_id=session_id,
        request_id=request_id,
        status=SessionTurnPublicStatus.COMPLETED,
        response_text=response_text,
        requires_user_input=False,
    )
    cached = CachedRequestResult(
        request_id=request_id,
        session_id=session_id,
        request_fingerprint="abc123",
        public_response=success,
        completed_at=now,
    )
    store.commit_successful_turn(
        session_id=session_id,
        request_id=request_id,
        expected_revision=expected_revision,
        meta=meta,
        checkpoint=checkpoint,
        audit_event=audit,
        cached_result=cached,
    )
    return meta, checkpoint, audit, cached


def test_session_keys_are_isolated_by_prefix_and_session(redis_bundle):
    client, store, prefix, config = redis_bundle
    other_prefix = f"govagent:test:f11:{uuid.uuid4()}"
    other = RedisSessionStore(
        client,
        RedisSessionConfig(
            key_prefix=other_prefix,
            session_ttl_seconds=config.session_ttl_seconds,
            session_expired_marker_ttl_seconds=config.session_expired_marker_ttl_seconds,
            audit_ttl_seconds=config.audit_ttl_seconds,
            request_dedup_ttl_seconds=config.request_dedup_ttl_seconds,
            request_lock_ttl_seconds=config.request_lock_ttl_seconds,
            session_lock_ttl_seconds=config.session_lock_ttl_seconds,
        ),
    )
    now = _utc()
    sid_a = str(uuid.uuid4())
    sid_b = str(uuid.uuid4())
    _commit_success(
        store,
        session_id=sid_a,
        request_id=str(uuid.uuid4()),
        expected_revision=0,
        revision=1,
        now=now,
        artifacts={"owner": "A"},
    )
    _commit_success(
        other,
        session_id=sid_b,
        request_id=str(uuid.uuid4()),
        expected_revision=0,
        revision=1,
        now=now,
        artifacts={"owner": "B"},
    )
    meta_a, cp_a = store.load_active_session(sid_a, now=now)
    assert cp_a.state.artifacts["owner"] == "A"
    with pytest.raises(SessionDomainError) as exc:
        store.load_active_session(sid_b, now=now)
    assert exc.value.code == SessionErrorCode.SESSION_NOT_FOUND
    meta_b, cp_b = other.load_active_session(sid_b, now=now)
    assert cp_b.state.artifacts["owner"] == "B"
    assert meta_a.session_id == sid_a
    assert "input_text" not in meta_a.model_dump()
    _cleanup_prefix(client, other_prefix)


def test_session_meta_and_checkpoint_physical_shape_excludes_turn_local_fields(
    redis_bundle,
):
    client, store, prefix, _config = redis_bundle
    now = _utc()
    session_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    marker = f"RAW_USER_INPUT_MUST_NOT_PERSIST_{uuid.uuid4()}"
    _commit_success(
        store,
        session_id=session_id,
        request_id=request_id,
        expected_revision=0,
        revision=1,
        now=now,
        artifacts={"f09": {"slot_context": {"required_slot": "employment_status"}}},
        response_text="系统回复",
    )
    meta_raw = client.get(f"{prefix}:session:{session_id}:meta")
    cp_raw = client.get(f"{prefix}:session:{session_id}:checkpoint")
    assert meta_raw is not None and cp_raw is not None
    meta = json.loads(meta_raw)
    cp = json.loads(cp_raw)
    assert meta["schema_version"] == 1
    assert set(meta) >= {
        "schema_version",
        "session_id",
        "created_at",
        "last_activity_at",
        "expires_at",
        "checkpoint_revision",
    }
    assert "input_text" not in meta
    assert cp["schema_version"] == 1
    assert cp["revision"] == 1
    assert set(cp["state"]) == {"phase", "status", "artifacts", "error"}
    assert "input_text" not in cp["state"]
    assert "request_id" not in cp["state"]
    assert "orchestration_trace" not in cp["state"]
    assert marker not in meta_raw
    assert marker not in cp_raw


def test_strict_json_serialization_rejects_non_finite_float():
    with pytest.raises(ValueError):
        dumps_json({"bad": float("nan")})


def test_corrupt_checkpoint_json_fails_closed(redis_bundle):
    client, store, prefix, _config = redis_bundle
    now = _utc()
    session_id = str(uuid.uuid4())
    _commit_success(
        store,
        session_id=session_id,
        request_id=str(uuid.uuid4()),
        expected_revision=0,
        revision=1,
        now=now,
    )
    client.set(f"{prefix}:session:{session_id}:checkpoint", "{not-json")
    with pytest.raises(SessionDomainError) as exc:
        store.load_active_session(session_id, now=now)
    assert exc.value.code == SessionErrorCode.CHECKPOINT_INVALID


def test_unsupported_checkpoint_version_is_not_migrated(redis_bundle):
    client, store, prefix, _config = redis_bundle
    now = _utc()
    session_id = str(uuid.uuid4())
    _commit_success(
        store,
        session_id=session_id,
        request_id=str(uuid.uuid4()),
        expected_revision=0,
        revision=1,
        now=now,
    )
    payload = json.loads(client.get(f"{prefix}:session:{session_id}:checkpoint"))
    payload["schema_version"] = 99
    client.set(
        f"{prefix}:session:{session_id}:checkpoint",
        dumps_json(payload),
    )
    with pytest.raises(SessionDomainError) as exc:
        store.load_active_session(session_id, now=now)
    assert exc.value.code == SessionErrorCode.CHECKPOINT_VERSION_UNSUPPORTED


def test_revision_increments_and_stale_revision_conflicts_via_watch(redis_bundle):
    _client, store, _prefix, _config = redis_bundle
    now = _utc()
    session_id = str(uuid.uuid4())
    _commit_success(
        store,
        session_id=session_id,
        request_id=str(uuid.uuid4()),
        expected_revision=0,
        revision=1,
        now=now,
        artifacts={"v": 1},
    )
    _commit_success(
        store,
        session_id=session_id,
        request_id=str(uuid.uuid4()),
        expected_revision=1,
        revision=2,
        now=now + timedelta(seconds=1),
        artifacts={"v": 2},
    )
    _commit_success(
        store,
        session_id=session_id,
        request_id=str(uuid.uuid4()),
        expected_revision=2,
        revision=3,
        now=now + timedelta(seconds=2),
        artifacts={"v": 3},
    )
    meta, cp = store.load_active_session(session_id, now=now + timedelta(seconds=3))
    assert meta.checkpoint_revision == 3
    assert cp.revision == 3
    assert cp.state.artifacts["v"] == 3

    with pytest.raises(SessionDomainError) as exc:
        _commit_success(
            store,
            session_id=session_id,
            request_id=str(uuid.uuid4()),
            expected_revision=1,
            revision=2,
            now=now + timedelta(seconds=4),
            artifacts={"v": "stale"},
        )
    assert exc.value.code == SessionErrorCode.SESSION_CONFLICT
    _, cp_final = store.load_active_session(session_id, now=now + timedelta(seconds=5))
    assert cp_final.state.artifacts["v"] == 3


def test_atomic_success_writes_meta_checkpoint_audit_and_request_cache(redis_bundle):
    client, store, prefix, config = redis_bundle
    now = _utc()
    session_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    _commit_success(
        store,
        session_id=session_id,
        request_id=request_id,
        expected_revision=0,
        revision=1,
        now=now,
    )
    assert client.exists(f"{prefix}:session:{session_id}:meta") == 1
    assert client.exists(f"{prefix}:session:{session_id}:checkpoint") == 1
    assert client.exists(f"{prefix}:session:{session_id}:audit") == 1
    assert client.exists(f"{prefix}:request:{request_id}:result") == 1
    assert client.llen(f"{prefix}:session:{session_id}:audit") == 1
    meta_ttl = client.ttl(f"{prefix}:session:{session_id}:meta")
    cp_ttl = client.ttl(f"{prefix}:session:{session_id}:checkpoint")
    audit_ttl = client.ttl(f"{prefix}:session:{session_id}:audit")
    result_ttl = client.ttl(f"{prefix}:request:{request_id}:result")
    assert 0 < cp_ttl <= config.session_ttl_seconds
    assert cp_ttl < meta_ttl <= (
        config.session_ttl_seconds + config.session_expired_marker_ttl_seconds
    )
    assert cp_ttl < audit_ttl <= config.audit_ttl_seconds
    assert 0 < result_ttl <= config.request_dedup_ttl_seconds


def test_audit_list_appends_and_excludes_raw_sensitive_fields(redis_bundle):
    client, store, prefix, _config = redis_bundle
    now = _utc()
    session_id = str(uuid.uuid4())
    secret = f"TEST_SECRET_MUST_NOT_PERSIST_{uuid.uuid4()}"
    raw = f"RAW_USER_INPUT_MUST_NOT_PERSIST_{uuid.uuid4()}"
    _commit_success(
        store,
        session_id=session_id,
        request_id=str(uuid.uuid4()),
        expected_revision=0,
        revision=1,
        now=now,
        response_text="第一轮系统回复",
    )
    _commit_success(
        store,
        session_id=session_id,
        request_id=str(uuid.uuid4()),
        expected_revision=1,
        revision=2,
        now=now + timedelta(seconds=1),
        response_text="第二轮系统回复",
    )
    events = client.lrange(f"{prefix}:session:{session_id}:audit", 0, -1)
    assert len(events) == 2
    joined = "\n".join(events)
    assert raw not in joined
    assert secret not in joined
    assert "input_text" not in joined
    assert "第一轮系统回复" not in joined
    assert "第二轮系统回复" not in joined
    assert f"{prefix}:session:" not in joined
    for item in events:
        payload = json.loads(item)
        assert payload["event_type"] == "TURN_COMPLETED"
        assert "traceback" not in payload


def test_request_cache_physical_structure_excludes_raw_input(redis_bundle):
    client, store, prefix, _config = redis_bundle
    now = _utc()
    session_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    raw = f"RAW_USER_INPUT_MUST_NOT_PERSIST_{uuid.uuid4()}"
    _commit_success(
        store,
        session_id=session_id,
        request_id=request_id,
        expected_revision=0,
        revision=1,
        now=now,
    )
    cached_raw = client.get(f"{prefix}:request:{request_id}:result")
    assert cached_raw is not None
    cached = json.loads(cached_raw)
    assert cached["request_id"] == request_id
    assert cached["session_id"] == session_id
    assert "request_fingerprint" in cached
    assert "public_response" in cached
    assert "completed_at" in cached
    assert raw not in cached_raw
    assert "input_text" not in cached
    assert "artifacts" not in cached["public_response"]


def test_unknown_expired_and_missing_checkpoint_semantics(redis_bundle):
    client, store, prefix, _config = redis_bundle
    now = _utc()
    missing = str(uuid.uuid4())
    with pytest.raises(SessionDomainError) as not_found:
        store.load_active_session(missing, now=now)
    assert not_found.value.code == SessionErrorCode.SESSION_NOT_FOUND

    session_id = str(uuid.uuid4())
    _commit_success(
        store,
        session_id=session_id,
        request_id=str(uuid.uuid4()),
        expected_revision=0,
        revision=1,
        now=now,
    )
    meta = json.loads(client.get(f"{prefix}:session:{session_id}:meta"))
    # Keep created_at <= last_activity_at <= expires_at; expiry is vs wall-clock now.
    expired_at = now - timedelta(minutes=5)
    meta["created_at"] = (expired_at - timedelta(minutes=1)).isoformat()
    meta["last_activity_at"] = (expired_at - timedelta(seconds=1)).isoformat()
    meta["expires_at"] = expired_at.isoformat()
    client.set(f"{prefix}:session:{session_id}:meta", dumps_json(meta))
    with pytest.raises(SessionDomainError) as expired:
        store.load_active_session(session_id, now=now)
    assert expired.value.code == SessionErrorCode.SESSION_EXPIRED

    session_id2 = str(uuid.uuid4())
    _commit_success(
        store,
        session_id=session_id2,
        request_id=str(uuid.uuid4()),
        expected_revision=0,
        revision=1,
        now=now,
    )
    client.delete(f"{prefix}:session:{session_id2}:checkpoint")
    with pytest.raises(SessionDomainError) as invalid:
        store.load_active_session(session_id2, now=now)
    assert invalid.value.code == SessionErrorCode.CHECKPOINT_INVALID


def test_request_and_session_locks_are_per_id_and_token_safe(redis_bundle):
    _client, store, _prefix, _config = redis_bundle
    rid = str(uuid.uuid4())
    sid_a = str(uuid.uuid4())
    sid_b = str(uuid.uuid4())
    req_lock = store.acquire_request_lock(rid)
    assert isinstance(req_lock, Lock)
    assert req_lock.acquire(blocking=False) is True
    assert store.acquire_request_lock(rid).acquire(blocking=False) is False
    req_lock.release()
    req_lock2 = store.acquire_request_lock(rid)
    assert req_lock2.acquire(blocking=False) is True
    req_lock2.release()

    lock_a = store.acquire_session_lock(sid_a)
    lock_b = store.acquire_session_lock(sid_b)
    assert lock_a.acquire(blocking=False) is True
    assert lock_b.acquire(blocking=False) is True
    assert store.acquire_session_lock(sid_a).acquire(blocking=False) is False
    lock_a.release()
    lock_b.release()


def test_redis_connection_failure_maps_to_persistence_unavailable(redis_bundle):
    _client, _store, prefix, config = redis_bundle
    broken = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2)
    store = RedisSessionStore(broken, config)
    with pytest.raises(SessionDomainError) as exc:
        store.meta_exists(str(uuid.uuid4()))
    assert exc.value.code == SessionErrorCode.PERSISTENCE_UNAVAILABLE
    assert "Connection" not in str(exc.value)
    broken.close()


def test_append_failure_audit_does_not_create_usable_checkpoint_for_new_prefix(
    redis_bundle,
):
    client, store, prefix, _config = redis_bundle
    session_id = str(uuid.uuid4())
    now = _utc()
    event = AuditEvent(
        event_id=str(uuid.uuid4()),
        session_id=session_id,
        request_id=str(uuid.uuid4()),
        occurred_at=now,
        event_type=AuditEventType.TURN_FAILED,
        outcome=AuditOutcome.FAILURE,
        failure_code=SessionErrorCode.AGENT_TURN_FAILED,
        capability="SESSION_TURN",
    )
    store.append_failure_audit(session_id=session_id, audit_event=event)
    assert client.exists(f"{prefix}:session:{session_id}:meta") == 0
    assert client.exists(f"{prefix}:session:{session_id}:checkpoint") == 0
    assert client.llen(f"{prefix}:session:{session_id}:audit") == 1


def test_corrupt_audit_string_blocks_commit_without_partial_write(redis_bundle):
    """RF-F11-RV-001: WRONGTYPE audit must fail before MULTI; no durable partial write."""
    client, store, prefix, _config = redis_bundle
    now = _utc()
    session_id = str(uuid.uuid4())
    first_request_id = str(uuid.uuid4())
    _commit_success(
        store,
        session_id=session_id,
        request_id=first_request_id,
        expected_revision=0,
        revision=1,
        now=now,
        artifacts={"rev": 1},
    )
    meta_key = f"{prefix}:session:{session_id}:meta"
    checkpoint_key = f"{prefix}:session:{session_id}:checkpoint"
    audit_key = f"{prefix}:session:{session_id}:audit"
    meta_before = client.get(meta_key)
    checkpoint_before = client.get(checkpoint_key)
    assert meta_before is not None and checkpoint_before is not None
    assert client.type(audit_key) == "list"

    corrupt_marker = f"CORRUPT_AUDIT_STRING_{uuid.uuid4()}"
    client.set(audit_key, corrupt_marker)
    assert client.type(audit_key) == "string"

    next_request_id = str(uuid.uuid4())
    with pytest.raises(SessionDomainError) as exc:
        _commit_success(
            store,
            session_id=session_id,
            request_id=next_request_id,
            expected_revision=1,
            revision=2,
            now=now + timedelta(seconds=1),
            artifacts={"rev": 2},
        )
    assert exc.value.code == SessionErrorCode.AUDIT_PERSISTENCE_FAILED

    assert client.get(meta_key) == meta_before
    assert client.get(checkpoint_key) == checkpoint_before
    assert json.loads(meta_before)["checkpoint_revision"] == 1
    assert client.type(audit_key) == "string"
    assert client.get(audit_key) == corrupt_marker
    assert client.get(f"{prefix}:request:{next_request_id}:result") is None
    assert client.exists(f"{prefix}:request:{first_request_id}:result") == 1


def test_append_failure_audit_rejects_corrupt_string_audit_key(redis_bundle):
    """RF-F11-RV-006 companion: failure audit also fail-closes on invalid TYPE."""
    client, store, prefix, _config = redis_bundle
    now = _utc()
    session_id = str(uuid.uuid4())
    audit_key = f"{prefix}:session:{session_id}:audit"
    corrupt = f"CORRUPT_FAIL_AUDIT_{uuid.uuid4()}"
    client.set(audit_key, corrupt)
    event = AuditEvent(
        event_id=str(uuid.uuid4()),
        session_id=session_id,
        request_id=str(uuid.uuid4()),
        occurred_at=now,
        event_type=AuditEventType.TURN_FAILED,
        outcome=AuditOutcome.FAILURE,
        failure_code=SessionErrorCode.AGENT_TURN_FAILED,
        capability="SESSION_TURN",
    )
    with pytest.raises(SessionDomainError) as exc:
        store.append_failure_audit(session_id=session_id, audit_event=event)
    assert exc.value.code == SessionErrorCode.AUDIT_PERSISTENCE_FAILED
    assert client.type(audit_key) == "string"
    assert client.get(audit_key) == corrupt
    assert client.exists(f"{prefix}:session:{session_id}:meta") == 0


def test_session_meta_timestamp_order_and_utc_normalize():
    """RF-F11-RV-005: SessionMeta enforces ordering and UTC normalize."""
    offset = timezone(timedelta(hours=8))
    now = datetime(2026, 9, 14, 12, 0, 0, tzinfo=offset)
    meta = SessionMeta(
        session_id=str(uuid.uuid4()),
        created_at=now,
        last_activity_at=now,
        expires_at=now + timedelta(hours=1),
        checkpoint_revision=1,
    )
    assert meta.created_at.tzinfo == timezone.utc
    assert meta.created_at.hour == 4  # UTC+8 noon → 04:00 UTC

    with pytest.raises(ValueError):
        SessionMeta(
            session_id=str(uuid.uuid4()),
            created_at=now + timedelta(minutes=5),
            last_activity_at=now,
            expires_at=now + timedelta(hours=1),
            checkpoint_revision=1,
        )
