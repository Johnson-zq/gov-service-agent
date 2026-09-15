"""F11 Session API router tests (test app composition; no main.py activation)."""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis import Redis

from gov_service_agent.agent.state import (
    AgentPhase,
    AgentState,
    WorkflowStatus,
    create_initial_state,
    validate_agent_state,
)
from gov_service_agent.session.api import create_session_router
from gov_service_agent.session.models import (
    AgentTurnResult,
    SessionDomainError,
    SessionErrorCode,
    SessionTurnPublicStatus,
    SessionTurnSuccess,
)
from gov_service_agent.session.service import SessionTurnService
from gov_service_agent.session.store import RedisSessionConfig, RedisSessionStore


def _uuid4() -> str:
    return str(uuid.uuid4())


def _cleanup_prefix(client: Redis, prefix: str) -> None:
    keys = list(client.scan_iter(match=f"{prefix}:*", count=200))
    if keys:
        client.delete(*keys)


@dataclass
class DeterministicTestAgentTurnProcessor:
    response_text: str = "api-deterministic-response"
    requires_user_input: bool = True
    public_status: SessionTurnPublicStatus = (
        SessionTurnPublicStatus.AWAITING_USER_INPUT
    )
    fail: bool = False
    unexpected: bool = False
    calls: list[dict[str, Any]] = field(default_factory=list)
    artifacts_factory: Callable[[AgentState | None], dict[str, Any]] | None = None

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
        if self.unexpected:
            raise RuntimeError("TEST_SECRET_MUST_NOT_LEAK_unexpected")
        if self.fail:
            raise RuntimeError("controlled agent failure")
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


@pytest.fixture
def api_env():
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
    store = RedisSessionStore(client, config)
    processor = DeterministicTestAgentTurnProcessor()
    service = SessionTurnService(
        store=store,
        processor=processor,
        session_ttl_seconds=180,
        max_input_chars=4000,
    )
    app = FastAPI()
    app.include_router(create_session_router(service))
    http = TestClient(app)
    try:
        yield {
            "http": http,
            "client": client,
            "prefix": prefix,
            "store": store,
            "processor": processor,
            "service": service,
            "config": config,
        }
    finally:
        try:
            _cleanup_prefix(client, prefix)
        except Exception as exc:  # noqa: BLE001
            client.close()
            raise AssertionError(f"Redis test prefix cleanup failed: {exc}") from exc
        client.close()


def _post(http: TestClient, payload: dict[str, Any]):
    return http.post("/api/v1/session/turn", json=payload)


def test_api_new_and_existing_session_round_trip(api_env):
    http = api_env["http"]
    processor = api_env["processor"]
    r1 = _post(
        http,
        {
            "request_id": _uuid4(),
            "input_text": "我辞职了，现在没单位，想自己交社保",
        },
    )
    assert r1.status_code == 200
    body1 = r1.json()
    assert set(body1) == {
        "session_id",
        "request_id",
        "status",
        "response_text",
        "requires_user_input",
    }
    assert body1["status"] == "AWAITING_USER_INPUT"
    assert "artifacts" not in body1
    assert "traceback" not in r1.text

    r2 = _post(
        http,
        {
            "request_id": _uuid4(),
            "session_id": body1["session_id"],
            "input_text": "平时接零活，没有固定单位",
        },
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["session_id"] == body1["session_id"]
    assert len(processor.calls) == 2
    assert processor.calls[1]["input_text"] == "平时接零活，没有固定单位"
    assert processor.calls[1]["restored_state"] is not None


def test_api_request_session_and_input_validation(api_env):
    http = api_env["http"]
    assert _post(http, {"input_text": "缺 request"}).status_code == 422
    assert (
        _post(
            http,
            {"request_id": "not-a-uuid", "input_text": "x"},
        ).status_code
        == 422
    )
    # UUID1 is not UUID4
    assert (
        _post(
            http,
            {
                "request_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
                "input_text": "x",
            },
        ).status_code
        == 422
    )
    assert (
        _post(
            http,
            {
                "request_id": _uuid4(),
                "session_id": "bad-session",
                "input_text": "x",
            },
        ).status_code
        == 422
    )
    assert (
        _post(http, {"request_id": _uuid4(), "input_text": ""}).status_code == 422
    )
    assert (
        _post(http, {"request_id": _uuid4(), "input_text": "   "}).status_code == 422
    )
    oversized = _post(
        http,
        {"request_id": _uuid4(), "input_text": "字" * 4001},
    )
    assert oversized.status_code == 422


def _assert_controlled_422(response, *, sentinel: str | None = None) -> dict:
    assert response.status_code == 422
    body = response.json()
    assert "detail" not in body
    assert set(body.keys()) >= {"request_id", "session_id", "status", "error"}
    assert body["status"] == "FAILED"
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["error"]["message"] == "请求参数无效。"
    text = json.dumps(body, ensure_ascii=False)
    if sentinel is not None:
        assert sentinel not in text
    return body


def test_api_422_does_not_echo_raw_sentinel_input(api_env):
    """RF-F11-RV-002: controlled 422 must not echo raw USER input."""
    http = api_env["http"]
    sentinel = f"RAW_422_INPUT_MUST_NOT_LEAK_{uuid.uuid4()}"
    # empty/whitespace invalidates while still sending sensitive marker as sibling field
    # via oversized + sentinel path: use blank input_text with sentinel embedded...
    # Actually blank fails without including sentinel. Use invalid type mix:
    # send input_text as the sentinel but also invalid request_id so validation fails.
    response = _post(
        http,
        {"request_id": "not-a-uuid", "input_text": sentinel},
    )
    body = _assert_controlled_422(response, sentinel=sentinel)
    assert body["request_id"] is None


def test_api_422_oversized_input_is_not_echoed(api_env):
    """RF-F11-RV-002: oversized input_text must not appear in 422 body."""
    http = api_env["http"]
    marker = f"OVERSIZE_MARKER_{uuid.uuid4()}"
    oversized_text = marker + ("字" * 4001)
    rid = _uuid4()
    response = _post(
        http,
        {"request_id": rid, "input_text": oversized_text},
    )
    body = _assert_controlled_422(response, sentinel=marker)
    assert body["request_id"] == rid
    assert oversized_text not in json.dumps(body, ensure_ascii=False)


def test_api_422_invalid_uuid_uses_session_turn_error_shape(api_env):
    """RF-F11-RV-002/007: invalid UUID returns F11 SessionTurnError, not FastAPI detail."""
    http = api_env["http"]
    response = _post(
        http,
        {
            "request_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
            "session_id": "not-uuid",
            "input_text": "x",
        },
    )
    body = _assert_controlled_422(response)
    assert body["request_id"] is None
    assert body["session_id"] is None


def test_api_unknown_session_is_404_and_does_not_create_session(api_env):
    http = api_env["http"]
    client = api_env["client"]
    prefix = api_env["prefix"]
    unknown = _uuid4()
    response = _post(
        http,
        {
            "request_id": _uuid4(),
            "session_id": unknown,
            "input_text": "查询未知会话",
        },
    )
    assert response.status_code == 404
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["error"]["code"] == "SESSION_NOT_FOUND"
    assert client.exists(f"{prefix}:session:{unknown}:meta") == 0


def test_api_expired_session_is_410(api_env):
    http = api_env["http"]
    client = api_env["client"]
    prefix = api_env["prefix"]
    created = _post(
        http,
        {"request_id": _uuid4(), "input_text": "创建后过期"},
    )
    session_id = created.json()["session_id"]
    meta = json.loads(client.get(f"{prefix}:session:{session_id}:meta"))
    past = datetime.now(timezone.utc) - timedelta(minutes=10)
    meta["created_at"] = (past - timedelta(minutes=1)).isoformat()
    meta["last_activity_at"] = (past - timedelta(seconds=1)).isoformat()
    meta["expires_at"] = past.isoformat()
    client.set(f"{prefix}:session:{session_id}:meta", json.dumps(meta, ensure_ascii=False))
    response = _post(
        http,
        {
            "request_id": _uuid4(),
            "session_id": session_id,
            "input_text": "继续",
        },
    )
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "SESSION_EXPIRED"


def test_api_request_reuse_conflict_is_409(api_env):
    http = api_env["http"]
    rid = _uuid4()
    first = _post(http, {"request_id": rid, "input_text": "payload-A"})
    assert first.status_code == 200
    second = _post(http, {"request_id": rid, "input_text": "payload-B"})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "REQUEST_ID_REUSE_CONFLICT"


def test_api_checkpoint_invalid_and_unsupported_version_mappings(api_env):
    http = api_env["http"]
    client = api_env["client"]
    prefix = api_env["prefix"]
    created = _post(http, {"request_id": _uuid4(), "input_text": "准备坏检查点"})
    session_id = created.json()["session_id"]

    client.delete(f"{prefix}:session:{session_id}:checkpoint")
    missing = _post(
        http,
        {
            "request_id": _uuid4(),
            "session_id": session_id,
            "input_text": "缺 checkpoint",
        },
    )
    assert missing.status_code == 500
    assert missing.json()["error"]["code"] == "CHECKPOINT_INVALID"
    assert "Traceback" not in missing.text

    # recreate valid then corrupt version
    created2 = _post(http, {"request_id": _uuid4(), "input_text": "再创建"})
    sid2 = created2.json()["session_id"]
    payload = json.loads(client.get(f"{prefix}:session:{sid2}:checkpoint"))
    payload["schema_version"] = 9
    client.set(
        f"{prefix}:session:{sid2}:checkpoint",
        json.dumps(payload, ensure_ascii=False),
    )
    unsupported = _post(
        http,
        {
            "request_id": _uuid4(),
            "session_id": sid2,
            "input_text": "版本不支持",
        },
    )
    assert unsupported.status_code == 500
    assert unsupported.json()["error"]["code"] == "CHECKPOINT_VERSION_UNSUPPORTED"


def test_api_persistence_unavailable_and_agent_and_unexpected_mappings():
    class RaisingStore:
        def get_cached_result(self, request_id: str):
            raise SessionDomainError(SessionErrorCode.PERSISTENCE_UNAVAILABLE)

        def acquire_request_lock(self, request_id: str):
            raise AssertionError("should not acquire after cache failure")

    app = FastAPI()
    service = SessionTurnService(
        store=RaisingStore(),  # type: ignore[arg-type]
        processor=DeterministicTestAgentTurnProcessor(),
    )
    app.include_router(create_session_router(service))
    http = TestClient(app, raise_server_exceptions=False)
    unavailable = _post(
        http,
        {"request_id": _uuid4(), "input_text": "持久化不可用"},
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "PERSISTENCE_UNAVAILABLE"
    assert "Redis" not in unavailable.text

    from tests.test_session_service import (
        DeterministicTestAgentTurnProcessor as SvcProcessor,
        RecordingStore,
    )

    store = RecordingStore()
    failing = SvcProcessor(fail_times=1)
    svc = SessionTurnService(store=store, processor=failing)
    app2 = FastAPI()
    app2.include_router(create_session_router(svc))
    http2 = TestClient(app2, raise_server_exceptions=False)
    agent_fail = _post(
        http2,
        {"request_id": _uuid4(), "input_text": "agent fail"},
    )
    assert agent_fail.status_code == 500
    assert agent_fail.json()["error"]["code"] == "AGENT_TURN_FAILED"
    assert "RuntimeError" not in agent_fail.text

    unexpected_processor = DeterministicTestAgentTurnProcessor(unexpected=True)
    svc3 = SessionTurnService(store=RecordingStore(), processor=unexpected_processor)
    app3 = FastAPI()
    app3.include_router(create_session_router(svc3))
    http3 = TestClient(app3, raise_server_exceptions=False)
    unexpected = _post(
        http3,
        {"request_id": _uuid4(), "input_text": "unexpected"},
    )
    assert unexpected.status_code == 500
    body = unexpected.json()
    assert body["error"]["code"] in {
        "AGENT_TURN_FAILED",
        "UNEXPECTED_INTERNAL_ERROR",
    }
    assert "TEST_SECRET_MUST_NOT_LEAK_unexpected" not in unexpected.text
    assert "Traceback" not in unexpected.text


def test_api_public_response_has_no_internal_leakage(api_env):
    http = api_env["http"]
    response = _post(
        http,
        {
            "request_id": _uuid4(),
            "input_text": "泄漏检查",
        },
    )
    text = response.text
    assert response.status_code == 200
    for banned in (
        "artifacts",
        "orchestration_trace",
        "govagent:test:f11",
        ":checkpoint",
        ":lock:",
        "Traceback",
        "AgentState",
    ):
        assert banned not in text


def test_api_request_in_progress_mapping_with_held_lock(api_env):
    http = api_env["http"]
    store = api_env["store"]
    rid = _uuid4()
    lock = store.acquire_request_lock(rid)
    assert lock.acquire(blocking=False) is True
    try:
        response = _post(
            http,
            {"request_id": rid, "input_text": "锁占用中"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "REQUEST_IN_PROGRESS"
    finally:
        lock.release()


def test_api_replay_returns_same_public_response_without_second_processor_call(api_env):
    http = api_env["http"]
    processor = api_env["processor"]
    rid = _uuid4()
    payload = {"request_id": rid, "input_text": "幂等 API"}
    first = _post(http, payload)
    second = _post(http, payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert len(processor.calls) == 1
