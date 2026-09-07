"""F07 Demo Provider and factory unit tests."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from gov_service_agent.llm.demo import DemoLlmProvider
from gov_service_agent.llm.provider import build_llm_provider
from gov_service_agent.llm.types import (
    DataClassification,
    LlmErrorCode,
    LlmMessage,
    LlmProviderError,
    LlmRequest,
    LlmRole,
)
from gov_service_agent.settings import Settings, get_settings


def _synthetic_request() -> LlmRequest:
    return LlmRequest(
        messages=[
            LlmMessage(
                role=LlmRole.USER,
                content="synthetic",
                classifications=frozenset({DataClassification.SYNTHETIC_TEST_DATA}),
            )
        ]
    )


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_demo_default_response_is_neutral() -> None:
    provider = DemoLlmProvider()
    response = provider.complete(_synthetic_request())
    assert provider.provider_name == "DEMO"
    assert response.content == '{"status":"demo"}'
    assert "payment_mode" not in response.content
    assert "self_payment" not in response.content
    assert "DEMO_SS_001" not in response.content


def test_demo_injected_content_deterministic() -> None:
    provider = DemoLlmProvider(response_content='{"ok":true}')
    first = provider.complete(_synthetic_request())
    second = provider.complete(_synthetic_request())
    assert first.content == second.content == '{"ok":true}'


def test_demo_controlled_failure() -> None:
    provider = DemoLlmProvider(failure=LlmErrorCode.TIMEOUT)
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(_synthetic_request())
    assert exc.value.code == LlmErrorCode.TIMEOUT


def test_demo_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args, **_kwargs):  # pragma: no cover - must not run
        raise AssertionError("Demo must not use httpx")

    monkeypatch.setattr(httpx.Client, "post", _boom)
    DemoLlmProvider().complete(_synthetic_request())


def test_factory_none_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    settings = Settings(_env_file=None)
    provider = build_llm_provider(settings)
    assert provider.provider_name == "NOT_CONFIGURED"
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(_synthetic_request())
    assert exc.value.code == LlmErrorCode.NOT_CONFIGURED


def test_factory_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "DEMO")
    settings = Settings(_env_file=None)
    provider = build_llm_provider(settings)
    assert isinstance(provider, DemoLlmProvider)


def test_factory_openai_compatible_missing_config_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "OPENAI_COMPATIBLE")
    for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL_ID"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=None)
    provider = build_llm_provider(settings)
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(_synthetic_request())
    assert exc.value.code == LlmErrorCode.NOT_CONFIGURED


def test_factory_openai_compatible_full_config() -> None:
    from gov_service_agent.llm.openai_compatible import OpenAICompatibleLlmProvider
    from pydantic import SecretStr

    settings = SimpleNamespace(
        llm_provider="OPENAI_COMPATIBLE",
        llm_base_url="http://llm.test/v1",
        llm_api_key=SecretStr("test-secret"),
        llm_model_id="test-model",
        llm_timeout_seconds=60.0,
        llm_max_retries=1,
    )
    provider = build_llm_provider(settings)
    assert isinstance(provider, OpenAICompatibleLlmProvider)


def test_factory_unknown_provider_defensive() -> None:
    settings = SimpleNamespace(llm_provider="WEIRD")
    with pytest.raises(LlmProviderError) as exc:
        build_llm_provider(settings)
    assert exc.value.code == LlmErrorCode.UNKNOWN_PROVIDER
