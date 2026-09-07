"""Deterministic Demo LLM Provider (F07). No network; no API key."""

from __future__ import annotations

from gov_service_agent.llm.types import (
    LlmErrorCode,
    LlmProviderError,
    LlmRequest,
    LlmResponse,
)

_DEFAULT_SYNTHETIC_CONTENT = '{"status":"demo"}'


class DemoLlmProvider:
    """Deterministic local provider for tests and offline scaffolding."""

    def __init__(
        self,
        *,
        response_content: str = _DEFAULT_SYNTHETIC_CONTENT,
        failure: LlmErrorCode | None = None,
    ) -> None:
        self._response_content = response_content
        self._failure = failure

    @property
    def provider_name(self) -> str:
        return "DEMO"

    @property
    def model_id(self) -> str | None:
        return None

    def complete(self, request: LlmRequest) -> LlmResponse:
        if self._failure is not None:
            raise LlmProviderError(
                self._failure,
                message="Demo provider controlled failure",
                retryable=False,
            )
        return LlmResponse(
            content=self._response_content,
            provider_name=self.provider_name,
            model_id=None,
            reasoning_present=False,
            finish_reason=None,
        )
