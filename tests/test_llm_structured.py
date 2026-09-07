"""F07 strict structured parser unit tests."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict

from gov_service_agent.llm.structured import parse_structured_output
from gov_service_agent.llm.types import LlmErrorCode, ParsingMode, StructuredParseError


class _DemoSchema(BaseModel):
    name: str
    score: float


class _DemoSchemaAllowExtra(BaseModel):
    """Intentionally permissive — parser must still reject unknown keys."""

    model_config = ConfigDict(extra="allow")

    name: str
    score: float


def test_direct_json_pass() -> None:
    result = parse_structured_output(
        '{"name":"demo","score":0.9}',
        _DemoSchema,
    )
    assert result.mode == ParsingMode.DIRECT_JSON
    assert result.value.name == "demo"
    assert result.value.score == 0.9


def test_json_fence_pass() -> None:
    content = '```json\n{"name":"demo","score":0.9}\n```'
    result = parse_structured_output(content, _DemoSchema)
    assert result.mode == ParsingMode.STRICT_SINGLE_JSON_CODE_FENCE
    assert result.value.name == "demo"


def test_empty_language_fence_pass() -> None:
    content = '```\n{"name":"demo","score":0.9}\n```'
    result = parse_structured_output(content, _DemoSchema)
    assert result.mode == ParsingMode.STRICT_SINGLE_JSON_CODE_FENCE


@pytest.mark.parametrize(
    "content",
    [
        'prefix\n```json\n{"name":"demo","score":0.9}\n```',
        '```json\n{"name":"demo","score":0.9}\n```\nsuffix',
        '```json\n{"name":"a","score":0.1}\n```\n```json\n{"name":"b","score":0.2}\n```',
        '```json\n{"name":"demo","score":0.9\n```\n```\n}\n```',
        '```json\n{"name":"demo","score":0.9}',
        '{"name":"demo","score":0.9}\n```',
    ],
)
def test_fence_strictness_reject(content: str) -> None:
    with pytest.raises(StructuredParseError):
        parse_structured_output(content, _DemoSchema)


def test_prose_plus_raw_json_reject() -> None:
    with pytest.raises(StructuredParseError):
        parse_structured_output(
            '结果如下：\n{"name":"demo","score":0.9}',
            _DemoSchema,
        )


def test_raw_json_plus_prose_reject() -> None:
    with pytest.raises(StructuredParseError):
        parse_structured_output(
            '{"name":"demo","score":0.9}\n完成',
            _DemoSchema,
        )


def test_multiple_json_reject() -> None:
    with pytest.raises(StructuredParseError):
        parse_structured_output(
            '{"name":"a","score":0.1}\n{"name":"b","score":0.2}',
            _DemoSchema,
        )


@pytest.mark.parametrize(
    "content",
    [
        "{'name':'demo','score':0.9}",
        '{"name":"demo",}',
    ],
)
def test_malformed_json_reject(content: str) -> None:
    with pytest.raises(StructuredParseError) as exc:
        parse_structured_output(content, _DemoSchema)
    assert content not in str(exc.value)


@pytest.mark.parametrize(
    "content",
    ['[]', '["x"]', '"abc"', "123", "true", "null"],
)
def test_non_object_json_reject(content: str) -> None:
    with pytest.raises(StructuredParseError) as exc:
        parse_structured_output(content, _DemoSchema)
    assert exc.value.detail == "NON_OBJECT_JSON"


@pytest.mark.parametrize("content", ["", "   ", "\n\t"])
def test_empty_content_reject(content: str) -> None:
    with pytest.raises(StructuredParseError) as exc:
        parse_structured_output(content, _DemoSchema)
    assert exc.value.code == LlmErrorCode.EMPTY_CONTENT


def test_unknown_extra_field_rejected_even_if_model_allows() -> None:
    with pytest.raises(StructuredParseError) as exc:
        parse_structured_output(
            '{"name":"demo","score":0.9,"next_node":"x"}',
            _DemoSchemaAllowExtra,
        )
    assert exc.value.code == LlmErrorCode.SCHEMA_VALIDATION_FAILED


def test_schema_validation_missing_required() -> None:
    with pytest.raises(StructuredParseError) as exc:
        parse_structured_output('{"name":"demo"}', _DemoSchema)
    assert exc.value.code == LlmErrorCode.SCHEMA_VALIDATION_FAILED
    assert '{"name":"demo"}' not in str(exc.value)


def test_schema_validation_wrong_type() -> None:
    with pytest.raises(StructuredParseError) as exc:
        parse_structured_output(
            '{"name":"demo","score":"bad"}',
            _DemoSchema,
        )
    assert exc.value.code == LlmErrorCode.SCHEMA_VALIDATION_FAILED
