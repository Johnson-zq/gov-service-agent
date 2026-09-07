"""LLM Provider Protocol, factory, and not-configured stub (F07)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from gov_service_agent.llm.demo import DemoLlmProvider
from gov_service_agent.llm.types import (
    LlmErrorCode,
    LlmProviderError,
    LlmRequest,
    LlmResponse,
)


@runtime_checkable
class LlmProvider(Protocol):
    """Provider-neutral synchronous LLM capability."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_id(self) -> str | None: ...

    def complete(self, request: LlmRequest) -> LlmResponse: ...


class _NotConfiguredProvider:
    """Private controlled-failure provider; not public API."""

    @property
    def provider_name(self) -> str:
        return "NOT_CONFIGURED"

    @property
    def model_id(self) -> str | None:
        return None

    def complete(self, request: LlmRequest) -> LlmResponse:
        raise LlmProviderError(
            LlmErrorCode.NOT_CONFIGURED,
            message="LLM provider is not configured",
            retryable=False,
        )


def build_llm_provider(settings: object) -> LlmProvider:
    """
    Construct an LLM provider from Settings.

    Does not perform network I/O. Missing Real config yields NOT_CONFIGURED
    on complete(), not Settings/startup failure.
    """
    provider = getattr(settings, "llm_provider", None)
    if provider is None:
        return _NotConfiguredProvider()

    if provider == "DEMO":
        return DemoLlmProvider()

    if provider == "OPENAI_COMPATIBLE":
        from gov_service_agent.llm.openai_compatible import OpenAICompatibleLlmProvider

        base_url = getattr(settings, "llm_base_url", None)
        model_id = getattr(settings, "llm_model_id", None)
        api_key = getattr(settings, "llm_api_key", None)
        secret: str | None = None
        if api_key is not None:
            getter = getattr(api_key, "get_secret_value", None)
            secret = getter() if callable(getter) else str(api_key)

        if (
            base_url is None
            or not str(base_url).strip()
            or model_id is None
            or not str(model_id).strip()
            or secret is None
            or not str(secret).strip()
        ):
            return _NotConfiguredProvider()

        timeout = float(getattr(settings, "llm_timeout_seconds", 60.0))
        max_retries = int(getattr(settings, "llm_max_retries", 1))
        return OpenAICompatibleLlmProvider(
            base_url=str(base_url).strip(),
            api_key=str(secret).strip(),
            model_id=str(model_id).strip(),
            timeout_seconds=timeout,
            max_retries=max_retries,
        )

    raise LlmProviderError(
        LlmErrorCode.UNKNOWN_PROVIDER,
        message="Unknown LLM provider configuration",
        retryable=False,
    )
