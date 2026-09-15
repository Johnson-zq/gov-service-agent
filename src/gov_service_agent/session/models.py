"""F11 Session API / persistence contracts and controlled domain errors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from gov_service_agent.agent.state import AgentState

SESSION_META_SCHEMA_VERSION = 1
CHECKPOINT_SCHEMA_VERSION = 1
AUDIT_SCHEMA_VERSION = 1
REQUEST_RESULT_SCHEMA_VERSION = 1


class SessionTurnPublicStatus(StrEnum):
    COMPLETED = "COMPLETED"
    AWAITING_USER_INPUT = "AWAITING_USER_INPUT"


class SessionTurnFailedStatus(StrEnum):
    FAILED = "FAILED"


class SessionErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    SESSION_CONFLICT = "SESSION_CONFLICT"
    REQUEST_ID_REUSE_CONFLICT = "REQUEST_ID_REUSE_CONFLICT"
    REQUEST_IN_PROGRESS = "REQUEST_IN_PROGRESS"
    CHECKPOINT_INVALID = "CHECKPOINT_INVALID"
    CHECKPOINT_VERSION_UNSUPPORTED = "CHECKPOINT_VERSION_UNSUPPORTED"
    PERSISTENCE_UNAVAILABLE = "PERSISTENCE_UNAVAILABLE"
    AUDIT_PERSISTENCE_FAILED = "AUDIT_PERSISTENCE_FAILED"
    AGENT_TURN_FAILED = "AGENT_TURN_FAILED"
    UNEXPECTED_INTERNAL_ERROR = "UNEXPECTED_INTERNAL_ERROR"


class AuditEventType(StrEnum):
    TURN_COMPLETED = "TURN_COMPLETED"
    TURN_FAILED = "TURN_FAILED"


class AuditOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


_SAFE_ERROR_MESSAGES: dict[SessionErrorCode, str] = {
    SessionErrorCode.INVALID_REQUEST: "请求参数无效。",
    SessionErrorCode.SESSION_NOT_FOUND: "会话不存在。",
    SessionErrorCode.SESSION_EXPIRED: "会话已过期。",
    SessionErrorCode.SESSION_CONFLICT: "会话状态冲突，请稍后重试。",
    SessionErrorCode.REQUEST_ID_REUSE_CONFLICT: "请求标识与已有内容冲突。",
    SessionErrorCode.REQUEST_IN_PROGRESS: "相同请求正在处理中。",
    SessionErrorCode.CHECKPOINT_INVALID: "会话检查点无效。",
    SessionErrorCode.CHECKPOINT_VERSION_UNSUPPORTED: "会话检查点版本不受支持。",
    SessionErrorCode.PERSISTENCE_UNAVAILABLE: "会话持久化暂时不可用。",
    SessionErrorCode.AUDIT_PERSISTENCE_FAILED: "审计记录持久化失败。",
    SessionErrorCode.AGENT_TURN_FAILED: "本轮处理失败。",
    SessionErrorCode.UNEXPECTED_INTERNAL_ERROR: "服务内部错误。",
}


def safe_error_message(code: SessionErrorCode) -> str:
    return _SAFE_ERROR_MESSAGES[code]


class SessionDomainError(Exception):
    """Controlled F11 domain failure with a public-safe error code."""

    def __init__(
        self,
        code: SessionErrorCode,
        *,
        session_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.code = code
        self.session_id = session_id
        self.request_id = request_id
        self.message = safe_error_message(code)
        super().__init__(self.message)


def _require_uuid4(value: UUID | str, *, field_name: str) -> str:
    if isinstance(value, UUID):
        uuid_value = value
    else:
        try:
            uuid_value = UUID(str(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"{field_name} must be a UUID4 string") from exc
    if uuid_value.version != 4:
        raise ValueError(f"{field_name} must be a UUID4 string")
    return str(uuid_value)


class SessionTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    session_id: str | None = None
    input_text: str = Field(min_length=1, max_length=4000)

    @field_validator("request_id", mode="before")
    @classmethod
    def _validate_request_id(cls, value: Any) -> str:
        return _require_uuid4(value, field_name="request_id")

    @field_validator("session_id", mode="before")
    @classmethod
    def _validate_session_id(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == "":
            return None
        return _require_uuid4(value, field_name="session_id")

    @field_validator("input_text", mode="before")
    @classmethod
    def _reject_whitespace_only(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip() == "":
            raise ValueError("input_text must not be empty or whitespace-only")
        return value


class SessionTurnSuccess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    request_id: str
    status: SessionTurnPublicStatus
    response_text: str
    requires_user_input: bool

    @model_validator(mode="after")
    def _status_requires_user_input_matrix(self) -> SessionTurnSuccess:
        if (
            self.status == SessionTurnPublicStatus.COMPLETED
            and self.requires_user_input
        ):
            raise ValueError(
                "COMPLETED requires requires_user_input=False"
            )
        if (
            self.status == SessionTurnPublicStatus.AWAITING_USER_INPUT
            and not self.requires_user_input
        ):
            raise ValueError(
                "AWAITING_USER_INPUT requires requires_user_input=True"
            )
        return self


class SessionErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: SessionErrorCode
    message: str


class SessionTurnError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str | None = None
    session_id: str | None = None
    status: SessionTurnFailedStatus = SessionTurnFailedStatus.FAILED
    error: SessionErrorBody


class PersistedAgentState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: str
    status: str
    artifacts: dict[str, Any]
    error: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _require_stable_error_none(self) -> PersistedAgentState:
        if self.error is not None:
            raise ValueError("stable PersistedAgentState.error must be None")
        return self


class SessionMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SESSION_META_SCHEMA_VERSION
    session_id: str
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    checkpoint_revision: int = Field(ge=1)

    @field_validator("created_at", "last_activity_at", "expires_at")
    @classmethod
    def _require_aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware UTC")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _timestamp_order(self) -> SessionMeta:
        if not (self.created_at <= self.last_activity_at <= self.expires_at):
            raise ValueError(
                "created_at <= last_activity_at <= expires_at required"
            )
        return self


class SessionCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = CHECKPOINT_SCHEMA_VERSION
    session_id: str
    revision: int = Field(ge=1)
    saved_at: datetime
    state: PersistedAgentState

    @field_validator("saved_at")
    @classmethod
    def _require_aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("saved_at must be timezone-aware UTC")
        return value.astimezone(timezone.utc)


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = AUDIT_SCHEMA_VERSION
    event_id: str
    session_id: str
    request_id: str
    occurred_at: datetime
    event_type: AuditEventType
    outcome: AuditOutcome
    before_phase: str | None = None
    before_status: str | None = None
    after_phase: str | None = None
    after_status: str | None = None
    checkpoint_revision_before: int | None = None
    checkpoint_revision_after: int | None = None
    failure_code: SessionErrorCode | None = None
    capability: str | None = "SESSION_TURN"

    @field_validator("occurred_at")
    @classmethod
    def _require_aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware UTC")
        return value.astimezone(timezone.utc)


class CachedRequestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = REQUEST_RESULT_SCHEMA_VERSION
    request_id: str
    session_id: str
    request_fingerprint: str
    public_response: SessionTurnSuccess
    completed_at: datetime

    @field_validator("completed_at")
    @classmethod
    def _require_aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("completed_at must be timezone-aware UTC")
        return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class AgentTurnResult:
    """Processor-owned one-turn result (F11 ↔ F12 production contract)."""

    state: AgentState
    response_text: str
    requires_user_input: bool
    public_status: SessionTurnPublicStatus
