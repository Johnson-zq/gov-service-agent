"""Opt-in real company LLM smoke (never auto-run)."""

from __future__ import annotations

import os

import pytest
from pydantic import BaseModel, ConfigDict, Field

from gov_service_agent.llm.provider import build_llm_provider
from gov_service_agent.llm.structured import parse_structured_output
from gov_service_agent.llm.types import (
    DataClassification,
    LlmMessage,
    LlmRequest,
    LlmRole,
    ParsingMode,
)
from gov_service_agent.settings import Settings, get_settings


class _SmokeSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0)


def _require_opt_in() -> None:
    if os.environ.get("RUN_LLM_REAL", "").strip() != "1":
        pytest.skip("RUN_LLM_REAL=1 required for real LLM smoke")


def _assert_real_config(settings: Settings) -> None:
    if settings.llm_provider != "OPENAI_COMPATIBLE":
        pytest.fail("RUN_LLM_REAL=1 requires LLM_PROVIDER=OPENAI_COMPATIBLE")
    if (
        settings.llm_base_url is None
        or settings.llm_api_key is None
        or settings.llm_model_id is None
    ):
        pytest.fail(
            "RUN_LLM_REAL=1 requires LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL_ID"
        )


def test_opt_in_missing_llm_config_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt-in without LLM config must FAIL (not SKIP). Cheap; no network."""
    monkeypatch.setenv("RUN_LLM_REAL", "1")
    for key in (
        "LLM_PROVIDER",
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL_ID",
        "LLM_TIMEOUT_SECONDS",
        "LLM_MAX_RETRIES",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    with pytest.raises(pytest.fail.Exception, match="RUN_LLM_REAL=1 requires"):
        _assert_real_config(settings)


@pytest.mark.llm_real
def test_real_openai_compatible_structured_smoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_opt_in()
    get_settings.cache_clear()
    # Use process env / ignored .env via Settings default (formal LLM_* only).
    settings = Settings()
    _assert_real_config(settings)

    provider = build_llm_provider(settings)
    assert provider.provider_name == "OPENAI_COMPATIBLE"

    request = LlmRequest(
        messages=[
            LlmMessage(
                role=LlmRole.SYSTEM,
                content=(
                    "你是结构化数据接口。你的输出将被程序直接解析。"
                    "只输出一个 JSON 对象。不要解释。不要输出 Markdown。"
                    "不要输出多个对象。不要输出任何前缀或后缀文字。"
                    "JSON 只允许包含 slot、value、confidence 三个字段。"
                ),
                classifications=frozenset(
                    {DataClassification.SYSTEM_CONTROL_DATA}
                ),
            ),
            LlmMessage(
                role=LlmRole.USER,
                content=(
                    "返回以下结构化结果：\n"
                    "slot=payment_mode\n"
                    "value=self_payment\n"
                    "confidence=0.9\n"
                    "只输出 JSON 对象。"
                ),
                classifications=frozenset(
                    {DataClassification.SYNTHETIC_TEST_DATA}
                ),
            ),
        ],
        operation="structured_smoke",
    )

    response = provider.complete(request)
    assert isinstance(response.content, str)
    assert response.content.strip() != ""
    # Do not read reasoning content; only presence flag is allowed.
    assert isinstance(response.reasoning_present, bool)

    parsed = parse_structured_output(response.content, _SmokeSchema)
    assert parsed.mode in {
        ParsingMode.DIRECT_JSON,
        ParsingMode.STRICT_SINGLE_JSON_CODE_FENCE,
    }
    assert parsed.value.slot == "payment_mode"
    assert parsed.value.value == "self_payment"
    assert 0.0 <= parsed.value.confidence <= 1.0
