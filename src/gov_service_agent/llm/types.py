"""Provider-neutral LLM request/response and error contracts (F07)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LlmRole(str, Enum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class DataClassification(str, Enum):
    PUBLIC_BUSINESS_METADATA = "PUBLIC_BUSINESS_METADATA"
    SYSTEM_CONTROL_DATA = "SYSTEM_CONTROL_DATA"
    SYNTHETIC_TEST_DATA = "SYNTHETIC_TEST_DATA"
    USER_FREE_TEXT = "USER_FREE_TEXT"
    USER_PII = "USER_PII"
    HIGH_SENSITIVE_IDENTITY = "HIGH_SENSITIVE_IDENTITY"
    TO_CONFIRM_OR_INTERNAL = "TO_CONFIRM_OR_INTERNAL"
    UNKNOWN = "UNKNOWN"


class LlmErrorCode(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNKNOWN_PROVIDER = "UNKNOWN_PROVIDER"
    POLICY_DENIED = "POLICY_DENIED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    SERVER_ERROR = "SERVER_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    EMPTY_CONTENT = "EMPTY_CONTENT"
    STRUCTURED_PARSE_FAILED = "STRUCTURED_PARSE_FAILED"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"


class ParsingMode(str, Enum):
    DIRECT_JSON = "DIRECT_JSON"
    STRICT_SINGLE_JSON_CODE_FENCE = "STRICT_SINGLE_JSON_CODE_FENCE"


class LlmProviderError(Exception):
    """Controlled LLM provider failure without sensitive payloads."""

    def __init__(
        self,
        code: LlmErrorCode,
        *,
        message: str,
        retryable: bool = False,
        http_status: int | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        self.http_status = http_status
        super().__init__(message)

    def __str__(self) -> str:
        status = f" http_status={self.http_status}" if self.http_status is not None else ""
        return (
            f"LlmProviderError(code={self.code.value}, "
            f"retryable={self.retryable}{status}): {self.message}"
        )

    def __repr__(self) -> str:
        return (
            f"LlmProviderError(code={self.code!r}, retryable={self.retryable!r}, "
            f"http_status={self.http_status!r}, message={self.message!r})"
        )


class StructuredParseError(Exception):
    """Controlled structured-output parse / schema failure."""

    def __init__(
        self,
        code: LlmErrorCode,
        *,
        message: str,
        detail: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)

    def __str__(self) -> str:
        detail = f" detail={self.detail}" if self.detail else ""
        return f"StructuredParseError(code={self.code.value}{detail}): {self.message}"

    def __repr__(self) -> str:
        return (
            f"StructuredParseError(code={self.code!r}, detail={self.detail!r}, "
            f"message={self.message!r})"
        )


class LlmMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: LlmRole
    content: str
    classifications: frozenset[DataClassification] = Field(default_factory=frozenset)


class LlmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    messages: list[LlmMessage]
    operation: str | None = None

    @field_validator("messages")
    @classmethod
    def _messages_non_empty(cls, value: list[LlmMessage]) -> list[LlmMessage]:
        if not value:
            raise ValueError("messages must be non-empty")
        return value

    @field_validator("operation", mode="before")
    @classmethod
    def _normalize_operation(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else None
        return value


class LlmResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str
    provider_name: str
    model_id: str | None = None
    reasoning_present: bool = False
    finish_reason: str | None = None
