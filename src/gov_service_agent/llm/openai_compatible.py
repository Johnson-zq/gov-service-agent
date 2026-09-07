"""OpenAI-compatible HTTP LLM Provider (F07). Policy before dispatch."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from gov_service_agent.llm.policy import evaluate_request_remote_policy
from gov_service_agent.llm.types import (
    LlmErrorCode,
    LlmProviderError,
    LlmRequest,
    LlmResponse,
    LlmRole,
)

logger = logging.getLogger("gov_service_agent")

_ROLE_MAP: dict[LlmRole, str] = {
    LlmRole.SYSTEM: "system",
    LlmRole.USER: "user",
    LlmRole.ASSISTANT: "assistant",
}

_REASONING_KEYS = frozenset({"reasoning", "reasoning_content", "thinking"})


class OpenAICompatibleLlmProvider:
    """Real company OpenAI-compatible chat completion provider (httpx)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_id: str,
        timeout_seconds: float = 60.0,
        max_retries: int = 1,
        client: httpx.Client | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        if not base_url or not str(base_url).strip():
            raise ValueError("base_url must be non-empty")
        if not api_key or not str(api_key).strip():
            raise ValueError("api_key must be non-empty")
        if not model_id or not str(model_id).strip():
            raise ValueError("model_id must be non-empty")
        if max_retries < 0 or max_retries > 3:
            raise ValueError("max_retries must be between 0 and 3")
        self._base_url = str(base_url).strip().rstrip("/")
        self._api_key = str(api_key).strip()
        self._model_id = str(model_id).strip()
        self._timeout_seconds = float(timeout_seconds)
        self._max_retries = int(max_retries)
        self._external_client = client
        self._sleep_fn = sleep_fn if sleep_fn is not None else time.sleep

    @property
    def provider_name(self) -> str:
        return "OPENAI_COMPATIBLE"

    @property
    def model_id(self) -> str | None:
        return self._model_id

    def complete(self, request: LlmRequest) -> LlmResponse:
        decision = evaluate_request_remote_policy(request)
        if not decision.allowed:
            denied = ",".join(sorted(c.value for c in decision.denied_categories))
            logger.info(
                "message=llm_policy_denied provider=%s operation=%s "
                "decision=deny denied_categories=%s",
                self.provider_name,
                request.operation or "",
                denied,
            )
            raise LlmProviderError(
                LlmErrorCode.POLICY_DENIED,
                message="Remote data policy denied the request",
                retryable=False,
            )

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model_id,
            "messages": [
                {
                    "role": _ROLE_MAP[message.role],
                    "content": message.content,
                }
                for message in request.messages
            ],
            "temperature": 0,
        }

        started = time.perf_counter()
        if self._external_client is not None:
            response = self._complete_with_client(
                self._external_client,
                url=url,
                headers=headers,
                payload=payload,
                operation=request.operation,
            )
        else:
            timeout = httpx.Timeout(self._timeout_seconds)
            with httpx.Client(timeout=timeout) as client:
                response = self._complete_with_client(
                    client,
                    url=url,
                    headers=headers,
                    payload=payload,
                    operation=request.operation,
                )
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "message=llm_complete_ok provider=%s operation=%s status=ok "
            "latency_ms=%s reasoning_present=%s response_length=%s",
            self.provider_name,
            request.operation or "",
            latency_ms,
            response.reasoning_present,
            len(response.content),
        )
        return response

    def _complete_with_client(
        self,
        client: httpx.Client,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        operation: str | None,
    ) -> LlmResponse:
        total_attempts = 1 + self._max_retries
        last_error: LlmProviderError | None = None

        for attempt in range(total_attempts):
            if attempt > 0:
                retry_index = attempt - 1
                delay = min(0.25 * (2**retry_index), 2.0)
                self._sleep_fn(delay)

            try:
                http_response = client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException:
                last_error = LlmProviderError(
                    LlmErrorCode.TIMEOUT,
                    message="LLM request timed out",
                    retryable=True,
                )
                self._log_attempt(operation, attempt, last_error)
                if attempt + 1 >= total_attempts or not last_error.retryable:
                    raise last_error
                continue
            except httpx.TransportError:
                last_error = LlmProviderError(
                    LlmErrorCode.NETWORK_UNAVAILABLE,
                    message="LLM network unavailable",
                    retryable=True,
                )
                self._log_attempt(operation, attempt, last_error)
                if attempt + 1 >= total_attempts or not last_error.retryable:
                    raise last_error
                continue

            status = http_response.status_code
            if status in {401, 403}:
                raise LlmProviderError(
                    LlmErrorCode.AUTHENTICATION_FAILED,
                    message="LLM authentication failed",
                    retryable=False,
                    http_status=status,
                )
            if status == 429:
                last_error = LlmProviderError(
                    LlmErrorCode.RATE_LIMITED,
                    message="LLM rate limited",
                    retryable=True,
                    http_status=status,
                )
                self._log_attempt(operation, attempt, last_error)
                if attempt + 1 >= total_attempts:
                    raise last_error
                continue
            if status >= 500:
                last_error = LlmProviderError(
                    LlmErrorCode.SERVER_ERROR,
                    message="LLM server error",
                    retryable=True,
                    http_status=status,
                )
                self._log_attempt(operation, attempt, last_error)
                if attempt + 1 >= total_attempts:
                    raise last_error
                continue
            if status >= 400:
                raise LlmProviderError(
                    LlmErrorCode.INVALID_REQUEST,
                    message="LLM request rejected",
                    retryable=False,
                    http_status=status,
                )

            return self._map_success_response(http_response)

        if last_error is not None:
            raise last_error
        raise LlmProviderError(
            LlmErrorCode.SERVER_ERROR,
            message="LLM request failed after retries",
            retryable=False,
        )

    def _map_success_response(self, http_response: httpx.Response) -> LlmResponse:
        try:
            body = http_response.json()
        except ValueError:
            raise LlmProviderError(
                LlmErrorCode.INVALID_RESPONSE,
                message="LLM response is not JSON",
                retryable=False,
                http_status=http_response.status_code,
            ) from None

        if not isinstance(body, dict):
            raise LlmProviderError(
                LlmErrorCode.INVALID_RESPONSE,
                message="LLM response JSON must be an object",
                retryable=False,
                http_status=http_response.status_code,
            )

        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LlmProviderError(
                LlmErrorCode.INVALID_RESPONSE,
                message="LLM response missing choices",
                retryable=False,
                http_status=http_response.status_code,
            )
        first = choices[0]
        if not isinstance(first, dict):
            raise LlmProviderError(
                LlmErrorCode.INVALID_RESPONSE,
                message="LLM response choice invalid",
                retryable=False,
                http_status=http_response.status_code,
            )
        message = first.get("message")
        if not isinstance(message, dict):
            raise LlmProviderError(
                LlmErrorCode.INVALID_RESPONSE,
                message="LLM response missing message",
                retryable=False,
                http_status=http_response.status_code,
            )
        content = message.get("content")
        if not isinstance(content, str):
            raise LlmProviderError(
                LlmErrorCode.INVALID_RESPONSE,
                message="LLM response content invalid",
                retryable=False,
                http_status=http_response.status_code,
            )
        if content.strip() == "":
            raise LlmProviderError(
                LlmErrorCode.EMPTY_CONTENT,
                message="LLM response content is empty",
                retryable=False,
                http_status=http_response.status_code,
            )

        reasoning_present = any(key in message for key in _REASONING_KEYS)
        finish_reason = first.get("finish_reason")
        if finish_reason is not None and not isinstance(finish_reason, str):
            finish_reason = None

        response_model = body.get("model")
        model_id = (
            response_model
            if isinstance(response_model, str) and response_model.strip()
            else self._model_id
        )

        return LlmResponse(
            content=content,
            provider_name=self.provider_name,
            model_id=model_id,
            reasoning_present=reasoning_present,
            finish_reason=finish_reason,
        )

    def _log_attempt(
        self,
        operation: str | None,
        attempt: int,
        error: LlmProviderError,
    ) -> None:
        logger.info(
            "message=llm_attempt_failed provider=%s operation=%s attempt=%s "
            "error_code=%s http_status=%s",
            self.provider_name,
            operation or "",
            attempt,
            error.code.value,
            error.http_status if error.http_status is not None else "",
        )
