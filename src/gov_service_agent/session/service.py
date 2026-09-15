"""F11 SessionTurnService and AgentTurnProcessor production Protocol."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from redis.exceptions import LockError

from gov_service_agent.agent.state import (
    AgentPhase,
    AgentState,
    AgentStateValidationError,
    WorkflowStatus,
    validate_agent_state,
)
from gov_service_agent.session.models import (
    AgentTurnResult,
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
    SessionTurnRequest,
    SessionTurnSuccess,
    safe_error_message,
)
from gov_service_agent.session.store import SessionStore, hold_lock, utc_now

logger = logging.getLogger("gov_service_agent")

Clock = Callable[[], datetime]
IdGenerator = Callable[[], str]


class AgentTurnProcessor(Protocol):
    """F11 ↔ F12 production integration contract (no concrete implementation here)."""

    def process_turn(
        self,
        *,
        session_id: str,
        request_id: str,
        input_text: str,
        restored_state: AgentState | None,
    ) -> AgentTurnResult: ...


def compute_request_fingerprint(
    *,
    session_id: str | None,
    input_text: str,
) -> str:
    canonical = json.dumps(
        {"session_id": session_id, "input_text": input_text},
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def to_persisted(state: AgentState) -> PersistedAgentState:
    validated = validate_agent_state(state)
    if validated["error"] is not None:
        raise SessionDomainError(SessionErrorCode.AGENT_TURN_FAILED)
    if validated["status"] == WorkflowStatus.FAILED:
        raise SessionDomainError(SessionErrorCode.AGENT_TURN_FAILED)
    if validated["phase"] == AgentPhase.FAILED:
        raise SessionDomainError(SessionErrorCode.AGENT_TURN_FAILED)
    return PersistedAgentState(
        phase=validated["phase"].value,
        status=validated["status"].value,
        artifacts=copy.deepcopy(validated["artifacts"]),
        error=None,
    )


def from_persisted(
    persisted: PersistedAgentState,
    *,
    request_id: str,
    input_text: str,
) -> AgentState:
    owned = PersistedAgentState.model_validate(
        copy.deepcopy(persisted.model_dump(mode="json"))
    )
    try:
        phase = AgentPhase(owned.phase)
        status = WorkflowStatus(owned.status)
    except ValueError as exc:
        raise SessionDomainError(SessionErrorCode.CHECKPOINT_INVALID) from exc
    state: AgentState = {
        "request_id": request_id,
        "input_text": input_text,
        "phase": phase,
        "status": status,
        "artifacts": copy.deepcopy(owned.artifacts),
        "error": None,
        "orchestration_trace": [],
    }
    try:
        return validate_agent_state(state)
    except AgentStateValidationError as exc:
        raise SessionDomainError(SessionErrorCode.CHECKPOINT_INVALID) from exc


def _default_id_generator() -> str:
    return str(uuid.uuid4())


class SessionTurnService:
    """Orchestrates one HTTP session turn without business-matter decisions."""

    def __init__(
        self,
        *,
        store: SessionStore,
        processor: AgentTurnProcessor,
        clock: Clock | None = None,
        id_generator: IdGenerator | None = None,
        max_input_chars: int = 4000,
        session_ttl_seconds: int = 1800,
        max_new_session_id_attempts: int = 3,
    ) -> None:
        if store is None:
            raise TypeError("store is required")
        if processor is None:
            raise TypeError("processor is required")
        if max_input_chars < 1:
            raise ValueError("max_input_chars must be >= 1")
        if session_ttl_seconds < 1:
            raise ValueError("session_ttl_seconds must be >= 1")
        self._store = store
        self._processor = processor
        self._clock: Clock = clock or utc_now
        self._id_generator: IdGenerator = id_generator or _default_id_generator
        self._max_input_chars = max_input_chars
        self._session_ttl_seconds = session_ttl_seconds
        self._max_new_session_id_attempts = max_new_session_id_attempts

    def handle_turn(self, request: SessionTurnRequest) -> SessionTurnSuccess:
        self._validate_input_length(request)
        fingerprint = compute_request_fingerprint(
            session_id=request.session_id,
            input_text=request.input_text,
        )
        cached = self._lookup_replay(request, fingerprint)
        if cached is not None:
            return cached

        request_lock = self._store.acquire_request_lock(request.request_id)
        acquired = False
        try:
            acquired = bool(request_lock.acquire(blocking=False))
            if not acquired:
                cached = self._lookup_replay(request, fingerprint)
                if cached is not None:
                    return cached
                raise SessionDomainError(
                    SessionErrorCode.REQUEST_IN_PROGRESS,
                    request_id=request.request_id,
                    session_id=request.session_id,
                )
            cached = self._lookup_replay(request, fingerprint)
            if cached is not None:
                return cached
            if request.session_id is None:
                return self._handle_new_session(request, fingerprint)
            return self._handle_existing_session(request, fingerprint)
        finally:
            if acquired:
                try:
                    request_lock.release()
                except LockError:
                    logger.warning(
                        "message=session_request_lock_release_failed request_id=%s",
                        request.request_id,
                    )

    def _validate_input_length(self, request: SessionTurnRequest) -> None:
        if len(request.input_text) > self._max_input_chars:
            raise SessionDomainError(
                SessionErrorCode.INVALID_REQUEST,
                request_id=request.request_id,
                session_id=request.session_id,
            )

    def _lookup_replay(
        self,
        request: SessionTurnRequest,
        fingerprint: str,
    ) -> SessionTurnSuccess | None:
        cached = self._store.get_cached_result(request.request_id)
        if cached is None:
            return None
        if cached.request_fingerprint != fingerprint:
            raise SessionDomainError(
                SessionErrorCode.REQUEST_ID_REUSE_CONFLICT,
                request_id=request.request_id,
                session_id=cached.session_id,
            )
        return SessionTurnSuccess.model_validate(
            cached.public_response.model_dump(mode="json")
        )

    def _handle_new_session(
        self,
        request: SessionTurnRequest,
        fingerprint: str,
    ) -> SessionTurnSuccess:
        last_error: SessionDomainError | None = None
        for _ in range(self._max_new_session_id_attempts):
            session_id = self._id_generator()
            session_lock = self._store.acquire_session_lock(session_id)
            try:
                with hold_lock(
                    session_lock,
                    code_on_busy=SessionErrorCode.SESSION_CONFLICT,
                    request_id=request.request_id,
                    session_id=session_id,
                ):
                    if self._store.meta_exists(session_id):
                        last_error = SessionDomainError(
                            SessionErrorCode.SESSION_CONFLICT,
                            request_id=request.request_id,
                            session_id=session_id,
                        )
                        continue
                    return self._run_and_commit(
                        request=request,
                        session_id=session_id,
                        fingerprint=fingerprint,
                        expected_revision=0,
                        restored_state=None,
                        before_phase=None,
                        before_status=None,
                        created_at=None,
                    )
            except SessionDomainError as exc:
                if exc.code == SessionErrorCode.SESSION_CONFLICT:
                    last_error = exc
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise SessionDomainError(
            SessionErrorCode.SESSION_CONFLICT,
            request_id=request.request_id,
        )

    def _handle_existing_session(
        self,
        request: SessionTurnRequest,
        fingerprint: str,
    ) -> SessionTurnSuccess:
        assert request.session_id is not None
        session_id = request.session_id
        session_lock = self._store.acquire_session_lock(session_id)
        with hold_lock(
            session_lock,
            code_on_busy=SessionErrorCode.SESSION_CONFLICT,
            request_id=request.request_id,
            session_id=session_id,
        ):
            now = self._clock()
            meta, checkpoint = self._store.load_active_session(
                session_id,
                now=now,
            )
            restored = from_persisted(
                checkpoint.state,
                request_id=request.request_id,
                input_text=request.input_text,
            )
            return self._run_and_commit(
                request=request,
                session_id=session_id,
                fingerprint=fingerprint,
                expected_revision=meta.checkpoint_revision,
                restored_state=restored,
                before_phase=checkpoint.state.phase,
                before_status=checkpoint.state.status,
                created_at=meta.created_at,
            )

    def _run_and_commit(
        self,
        *,
        request: SessionTurnRequest,
        session_id: str,
        fingerprint: str,
        expected_revision: int,
        restored_state: AgentState | None,
        before_phase: str | None,
        before_status: str | None,
        created_at: datetime | None,
    ) -> SessionTurnSuccess:
        try:
            result = self._processor.process_turn(
                session_id=session_id,
                request_id=request.request_id,
                input_text=request.input_text,
                restored_state=restored_state,
            )
        except SessionDomainError:
            raise
        except Exception:
            logger.warning(
                "message=agent_turn_failed session_id=%s request_id=%s",
                session_id,
                request.request_id,
            )
            self._record_agent_failure(
                session_id=session_id,
                request_id=request.request_id,
                expected_revision=expected_revision,
                before_phase=before_phase,
                before_status=before_status,
                is_new_session=expected_revision == 0,
            )
            raise SessionDomainError(
                SessionErrorCode.AGENT_TURN_FAILED,
                session_id=None if expected_revision == 0 else session_id,
                request_id=request.request_id,
            )

        try:
            if not isinstance(result, AgentTurnResult):
                raise SessionDomainError(SessionErrorCode.AGENT_TURN_FAILED)
            if not isinstance(result.response_text, str):
                raise SessionDomainError(SessionErrorCode.AGENT_TURN_FAILED)
            if not isinstance(result.requires_user_input, bool):
                raise SessionDomainError(SessionErrorCode.AGENT_TURN_FAILED)
            if not isinstance(result.public_status, SessionTurnPublicStatus):
                raise SessionDomainError(SessionErrorCode.AGENT_TURN_FAILED)
            validate_agent_state(result.state)
            if result.state.get("request_id") != request.request_id:
                raise SessionDomainError(SessionErrorCode.AGENT_TURN_FAILED)
            if result.state.get("input_text") != request.input_text:
                raise SessionDomainError(SessionErrorCode.AGENT_TURN_FAILED)
            if (
                result.public_status == SessionTurnPublicStatus.COMPLETED
                and result.requires_user_input
            ):
                raise SessionDomainError(SessionErrorCode.AGENT_TURN_FAILED)
            if (
                result.public_status
                == SessionTurnPublicStatus.AWAITING_USER_INPUT
                and not result.requires_user_input
            ):
                raise SessionDomainError(SessionErrorCode.AGENT_TURN_FAILED)
            persisted = to_persisted(result.state)
        except SessionDomainError as exc:
            if exc.code == SessionErrorCode.AGENT_TURN_FAILED:
                self._record_agent_failure(
                    session_id=session_id,
                    request_id=request.request_id,
                    expected_revision=expected_revision,
                    before_phase=before_phase,
                    before_status=before_status,
                    is_new_session=expected_revision == 0,
                )
                raise SessionDomainError(
                    SessionErrorCode.AGENT_TURN_FAILED,
                    session_id=None if expected_revision == 0 else session_id,
                    request_id=request.request_id,
                ) from exc
            raise
        except AgentStateValidationError as exc:
            self._record_agent_failure(
                session_id=session_id,
                request_id=request.request_id,
                expected_revision=expected_revision,
                before_phase=before_phase,
                before_status=before_status,
                is_new_session=expected_revision == 0,
            )
            raise SessionDomainError(
                SessionErrorCode.AGENT_TURN_FAILED,
                session_id=None if expected_revision == 0 else session_id,
                request_id=request.request_id,
            ) from exc

        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        new_revision = 1 if expected_revision == 0 else expected_revision + 1
        expires_at = now + timedelta(seconds=self._session_ttl_seconds)
        if expected_revision == 0:
            meta = SessionMeta(
                session_id=session_id,
                created_at=now,
                last_activity_at=now,
                expires_at=expires_at,
                checkpoint_revision=new_revision,
            )
        else:
            if created_at is None:
                raise SessionDomainError(
                    SessionErrorCode.UNEXPECTED_INTERNAL_ERROR,
                    session_id=session_id,
                    request_id=request.request_id,
                )
            meta = SessionMeta(
                session_id=session_id,
                created_at=created_at,
                last_activity_at=now,
                expires_at=expires_at,
                checkpoint_revision=new_revision,
            )

        checkpoint = SessionCheckpoint(
            session_id=session_id,
            revision=new_revision,
            saved_at=now,
            state=persisted,
        )
        success = SessionTurnSuccess(
            session_id=session_id,
            request_id=request.request_id,
            status=result.public_status,
            response_text=result.response_text,
            requires_user_input=result.requires_user_input,
        )
        audit_event = AuditEvent(
            event_id=self._id_generator(),
            session_id=session_id,
            request_id=request.request_id,
            occurred_at=now,
            event_type=AuditEventType.TURN_COMPLETED,
            outcome=AuditOutcome.SUCCESS,
            before_phase=before_phase,
            before_status=before_status,
            after_phase=persisted.phase,
            after_status=persisted.status,
            checkpoint_revision_before=(
                None if expected_revision == 0 else expected_revision
            ),
            checkpoint_revision_after=new_revision,
            failure_code=None,
            capability="SESSION_TURN",
        )
        cached_result = CachedRequestResult(
            request_id=request.request_id,
            session_id=session_id,
            request_fingerprint=fingerprint,
            public_response=SessionTurnSuccess.model_validate(
                success.model_dump(mode="json")
            ),
            completed_at=now,
        )
        self._store.commit_successful_turn(
            session_id=session_id,
            request_id=request.request_id,
            expected_revision=expected_revision,
            meta=meta,
            checkpoint=checkpoint,
            audit_event=audit_event,
            cached_result=cached_result,
        )
        return SessionTurnSuccess.model_validate(success.model_dump(mode="json"))

    def _record_agent_failure(
        self,
        *,
        session_id: str,
        request_id: str,
        expected_revision: int,
        before_phase: str | None,
        before_status: str | None,
        is_new_session: bool,
    ) -> None:
        if is_new_session:
            return
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        event = AuditEvent(
            event_id=self._id_generator(),
            session_id=session_id,
            request_id=request_id,
            occurred_at=now,
            event_type=AuditEventType.TURN_FAILED,
            outcome=AuditOutcome.FAILURE,
            before_phase=before_phase,
            before_status=before_status,
            after_phase=before_phase,
            after_status=before_status,
            checkpoint_revision_before=expected_revision,
            checkpoint_revision_after=expected_revision,
            failure_code=SessionErrorCode.AGENT_TURN_FAILED,
            capability="SESSION_TURN",
        )
        try:
            self._store.append_failure_audit(
                session_id=session_id,
                audit_event=event,
            )
        except SessionDomainError:
            logger.warning(
                "message=session_failure_audit_skipped code=%s session_id=%s request_id=%s",
                SessionErrorCode.AUDIT_PERSISTENCE_FAILED.value,
                session_id,
                request_id,
            )


def build_public_error(
    code: SessionErrorCode,
    *,
    request_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, object]:
    from gov_service_agent.session.models import (
        SessionErrorBody,
        SessionTurnError,
        SessionTurnFailedStatus,
    )

    error = SessionTurnError(
        request_id=request_id,
        session_id=session_id,
        status=SessionTurnFailedStatus.FAILED,
        error=SessionErrorBody(code=code, message=safe_error_message(code)),
    )
    return error.model_dump(mode="json")
