"""Anthropic-compatible provider tests. No live MicuAPI calls."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from gov_service_agent.llm.anthropic_compatible import AnthropicCompatibleLlmProvider
from gov_service_agent.llm.provider import build_llm_provider
from gov_service_agent.llm.types import (
    DataClassification,
    LlmErrorCode,
    LlmMessage,
    LlmProviderError,
    LlmRequest,
    LlmRole,
    RemoteDataPolicyProfile,
)
from gov_service_agent.settings import Settings

_FAKE_URL = "https://llm.test"
_FAKE_KEY = "SUPER_SECRET_TEST_TOKEN"
_FAKE_MODEL = "claude-haiku-4-5-20251001"


def _request(*classes: DataClassification, content: str = "synthetic user") -> LlmRequest:
    return LlmRequest(
        messages=[
            LlmMessage(
                role=LlmRole.SYSTEM,
                content="system rules",
                classifications=frozenset({DataClassification.SYSTEM_CONTROL_DATA}),
            ),
            LlmMessage(
                role=LlmRole.USER,
                content=content,
                classifications=frozenset(classes or (DataClassification.SYNTHETIC_TEST_DATA,)),
            ),
        ],
        operation="unit_test",
    )


def test_missing_api_key_reports_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ANTHROPIC_COMPATIBLE")
    monkeypatch.setenv("LLM_MODEL_ID", _FAKE_MODEL)
    monkeypatch.setenv("LLM_BASE_URL", _FAKE_URL)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    provider = build_llm_provider(settings)
    assert provider.provider_name == "NOT_CONFIGURED"
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(_request())
    assert exc.value.code is LlmErrorCode.NOT_CONFIGURED


def test_factory_builds_provider_without_network() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, json={"error": "should-not-run"})

    settings = SimpleNamespace(
        llm_provider="ANTHROPIC_COMPATIBLE",
        llm_base_url=_FAKE_URL,
        llm_api_key=SecretStr(_FAKE_KEY),
        llm_model_id=_FAKE_MODEL,
        llm_timeout_seconds=5.0,
        llm_max_retries=0,
        llm_remote_data_policy_profile=RemoteDataPolicyProfile.DEFAULT,
    )
    provider = build_llm_provider(settings)
    assert isinstance(provider, AnthropicCompatibleLlmProvider)
    assert provider.model_id == _FAKE_MODEL
    assert calls["n"] == 0


def test_success_payload_has_no_group_field() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        captured["api_key_header"] = request.headers.get("x-api-key")
        return httpx.Response(
            200,
            json={
                "model": _FAKE_MODEL,
                "stop_reason": "end_turn",
                "content": [
                    {"type": "thinking", "thinking": "hidden"},
                    {"type": "text", "text": "公开答复"},
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = AnthropicCompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        max_retries=0,
        client=client,
    )
    response = provider.complete(_request())
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == _FAKE_MODEL
    assert body["messages"] == [{"role": "user", "content": "synthetic user"}]
    assert body["system"] == "system rules"
    assert "group" not in body
    assert captured["url"] == "https://llm.test/v1/messages"
    assert captured["api_key_header"] == _FAKE_KEY
    assert response.content == "公开答复"
    assert response.reasoning_present is True
    assert _FAKE_KEY not in response.content
    client.close()


def test_demo_approved_still_blocks_sensitive_categories() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("sensitive request must not reach HTTP")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = AnthropicCompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        remote_data_policy_profile=RemoteDataPolicyProfile.DEMO_APPROVED,
        client=client,
    )
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(_request(DataClassification.USER_PII, content="id-number"))
    assert exc.value.code is LlmErrorCode.POLICY_DENIED
    client.close()


def test_default_profile_blocks_user_free_text_before_http() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("unauthorized free text must not reach HTTP")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = AnthropicCompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        client=client,
    )
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(_request(DataClassification.USER_FREE_TEXT))
    assert exc.value.code is LlmErrorCode.POLICY_DENIED
    client.close()
