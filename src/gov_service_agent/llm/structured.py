"""Strict structured-output parser (F07). No network; Fail Closed."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from gov_service_agent.llm.types import (
    LlmErrorCode,
    ParsingMode,
    StructuredParseError,
)

T = TypeVar("T", bound=BaseModel)

_FENCE_OPEN_JSON = "```json"
_FENCE_OPEN_BARE = "```"
_FENCE_CLOSE = "```"


@dataclass(frozen=True, slots=True)
class StructuredParseResult:
    value: BaseModel
    mode: ParsingMode


def _reject(
    code: LlmErrorCode,
    message: str,
    *,
    detail: str | None = None,
) -> None:
    raise StructuredParseError(code, message=message, detail=detail)


def _loads_object(text: str, *, detail_on_decode: str) -> dict:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        _reject(
            LlmErrorCode.STRUCTURED_PARSE_FAILED,
            "JSON decode failed",
            detail=detail_on_decode,
        )
    if not isinstance(payload, dict):
        _reject(
            LlmErrorCode.STRUCTURED_PARSE_FAILED,
            "JSON payload must be an object",
            detail="NON_OBJECT_JSON",
        )
    return payload


def _try_direct_json(text: str) -> dict | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        _reject(
            LlmErrorCode.STRUCTURED_PARSE_FAILED,
            "JSON payload must be an object",
            detail="NON_OBJECT_JSON",
        )
    return payload


def _parse_strict_fence(text: str) -> dict:
    lines = text.splitlines()
    if len(lines) < 2:
        _reject(
            LlmErrorCode.STRUCTURED_PARSE_FAILED,
            "Invalid or ambiguous JSON envelope",
            detail="AMBIGUOUS_ENVELOPE",
        )
    first = lines[0]
    last = lines[-1]
    if first not in {_FENCE_OPEN_JSON, _FENCE_OPEN_BARE}:
        _reject(
            LlmErrorCode.STRUCTURED_PARSE_FAILED,
            "Invalid or ambiguous JSON envelope",
            detail="AMBIGUOUS_ENVELOPE",
        )
    if last != _FENCE_CLOSE:
        _reject(
            LlmErrorCode.STRUCTURED_PARSE_FAILED,
            "Invalid or ambiguous JSON envelope",
            detail="AMBIGUOUS_ENVELOPE",
        )
    # Bare opening ``` cannot also be the sole closing line when len==2
    # with empty payload — allow empty middle; reject nested fences.
    middle = lines[1:-1]
    for line in middle:
        if "```" in line:
            _reject(
                LlmErrorCode.STRUCTURED_PARSE_FAILED,
                "Invalid or ambiguous JSON envelope",
                detail="AMBIGUOUS_ENVELOPE",
            )
    payload_text = "\n".join(middle).strip()
    if payload_text == "":
        _reject(
            LlmErrorCode.STRUCTURED_PARSE_FAILED,
            "JSON fence payload empty",
            detail="MALFORMED_JSON",
        )
    return _loads_object(payload_text, detail_on_decode="MALFORMED_JSON")


def _reject_unknown_keys(payload: dict, model_type: type[BaseModel]) -> None:
    allowed = set(model_type.model_fields.keys())
    unknown = set(payload.keys()) - allowed
    if unknown:
        _reject(
            LlmErrorCode.SCHEMA_VALIDATION_FAILED,
            "Unknown fields in structured payload",
            detail="UNKNOWN_FIELDS",
        )


def parse_structured_output(
    content: str,
    model_type: type[T],
) -> StructuredParseResult:
    """
    Parse provider content into a typed Pydantic model.

    Supports DIRECT_JSON then STRICT_SINGLE_JSON_CODE_FENCE only.
    Does not repair JSON or extract objects from prose.
    """
    if not isinstance(content, str):
        _reject(
            LlmErrorCode.STRUCTURED_PARSE_FAILED,
            "Content must be a string",
            detail="INVALID_CONTENT_TYPE",
        )
    text = content.strip()
    if text == "":
        _reject(
            LlmErrorCode.EMPTY_CONTENT,
            "Structured content is empty",
            detail="EMPTY_CONTENT",
        )

    mode: ParsingMode
    payload = _try_direct_json(text)
    if payload is not None:
        mode = ParsingMode.DIRECT_JSON
    else:
        payload = _parse_strict_fence(text)
        mode = ParsingMode.STRICT_SINGLE_JSON_CODE_FENCE

    _reject_unknown_keys(payload, model_type)
    try:
        value = model_type.model_validate(payload)
    except ValidationError:
        _reject(
            LlmErrorCode.SCHEMA_VALIDATION_FAILED,
            "Structured payload failed schema validation",
        )
    return StructuredParseResult(value=value, mode=mode)
