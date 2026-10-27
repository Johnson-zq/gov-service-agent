"""Anthropic-compatible Messages API provider. Policy runs before any HTTP call."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from gov_service_agent.llm.policy import (
    collect_request_classifications,
    evaluate_request_remote_policy,
)
from gov_service_agent.llm.types import (
    DataClassification,
    LlmErrorCode,
    LlmProviderError,
    LlmRequest,
    LlmResponse,
    LlmRole,
    RemoteDataPolicyProfile,
)

logger = logging.getLogger("gov_service_agent")

_ROLE_MAP: dict[LlmRole, str] = {
    LlmRole.USER: "user",
    LlmRole.ASSISTANT: "assistant",
}

# Third-party relays do not receive these categories, even under DEMO_APPROVED.
_RELAY_BLOCKED = frozenset(
    {
        DataClassification.USER_PII,
        DataClassification.HIGH_SENSITIVE_IDENTITY,
        DataClassification.TO_CONFIRM_OR_INTERNAL,
    }
)

_DEFAULT_MAX_TOKENS = 1024


class AnthropicCompatibleLlmProvider:
    """Minimal Anthropic Messages client. No vendor group or billing fields."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_id: str,
        timeout_seconds: float = 60.0,
        max_retries: int = 1,
        remote_data_policy_profile: RemoteDataPolicyProfile = (
            RemoteDataPolicyProfile.DEFAULT
        ),
        client: httpx.Client | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        if not base_url or not str(base_url).strip():
            raise ValueError("base_url must be non-empty")
        if not api_key or not str(api_key).strip():
            raise ValueError("api_key must be non-empty")
        if not model_id or not str(model_id).strip():
            raise ValueError("model_id must be non-empty")
        if max_retries < 0 or max_retries > 3:
            raise ValueError("max_retries must be between 0 and 3")
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        if not isinstance(remote_data_policy_profile, RemoteDataPolicyProfile):
            raise ValueError(
                "remote_data_policy_profile must be RemoteDataPolicyProfile"
            )
        self._base_url = str(base_url).strip().rstrip("/")
        self._api_key = str(api_key).strip()
        self._model_id = str(model_id).strip()
        self._timeout_seconds = float(timeout_seconds)
        self._max_retries = int(max_retries)
        self._max_tokens = int(max_tokens)
        self._remote_data_policy_profile = remote_data_policy_profile
        self._external_client = client
        self._sleep_fn = sleep_fn if sleep_fn is not None else time.sleep

    @property
    def provider_name(self) -> str:
        return "ANTHROPIC_COMPATIBLE"

    @property
    def model_id(self) -> str | None:
        return self._model_id

    def complete(self, request: LlmRequest) -> LlmResponse:
        self._enforce_policy(request)
        url = _messages_url(self._base_url)
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = _build_payload(
            request,
            model_id=self._model_id,
            max_tokens=self._max_tokens,
        )
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

    def _enforce_policy(self, request: LlmRequest) -> None:
        decision = evaluate_request_remote_policy(
            request,
            profile=self._remote_data_policy_profile,
        )
        blocked = collect_request_classifications(request) & _RELAY_BLOCKED
        if decision.allowed and not blocked:
            return
        denied = set(decision.denied_categories)
        denied.update(blocked)
        logger.info(
            "message=llm_policy_denied provider=%s operation=%s "
            "decision=deny denied_categories=%s",
            self.provider_name,
            request.operation or "",
            ",".join(sorted(item.value for item in denied)),
        )
        raise LlmProviderError(
            LlmErrorCode.POLICY_DENIED,
            message="Remote data policy denied the request",
            retryable=False,
        )

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
                self._sleep_fn(min(0.25 * (2 ** (attempt - 1)), 2.0))
            try:
                http_response = client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException:
                last_error = LlmProviderError(
                    LlmErrorCode.TIMEOUT,
                    message="LLM request timed out",
                    retryable=True,
                )
                if attempt + 1 >= total_attempts:
                    raise last_error
                continue
            except httpx.TransportError:
                last_error = LlmProviderError(
                    LlmErrorCode.NETWORK_UNAVAILABLE,
                    message="LLM network unavailable",
                    retryable=True,
                )
                if attempt + 1 >= total_attempts:
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
            if status == 429 or status >= 500:
                code = (
                    LlmErrorCode.RATE_LIMITED
                    if status == 429
                    else LlmErrorCode.SERVER_ERROR
                )
                last_error = LlmProviderError(
                    code,
                    message="LLM request failed",
                    retryable=True,
                    http_status=status,
                )
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
            return _map_success_response(http_response, fallback_model=self._model_id)

        if last_error is not None:
            raise last_error
        raise LlmProviderError(
            LlmErrorCode.SERVER_ERROR,
            message="LLM request failed after retries",
            retryable=False,
        )


def _messages_url(base_url: str) -> str:
    if base_url.endswith("/v1/messages"):
        return base_url
    if base_url.endswith("/v1"):
        return f"{base_url}/messages"
    return f"{base_url}/v1/messages"


def _build_payload(
    request: LlmRequest,
    *,
    model_id: str,
    max_tokens: int,
) -> dict[str, Any]:
    system_parts: list[str] = []
    messages: list[dict[str, str]] = []
    for message in request.messages:
        if message.role is LlmRole.SYSTEM:
            system_parts.append(message.content)
            continue
        mapped = _ROLE_MAP.get(message.role)
        if mapped is None:
            raise LlmProviderError(
                LlmErrorCode.INVALID_REQUEST,
                message="LLM request role is not supported",
                retryable=False,
            )
        messages.append({"role": mapped, "content": message.content})
    if not messages:
        raise LlmProviderError(
            LlmErrorCode.INVALID_REQUEST,
            message="LLM request requires a user or assistant message",
            retryable=False,
        )
    payload: dict[str, Any] = {
        "model": model_id,
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": messages,
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    return payload


def _map_success_response(
    http_response: httpx.Response,
    *,
    fallback_model: str,
) -> LlmResponse:
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
    content_blocks = body.get("content")
    texts: list[str] = []
    reasoning_present = False
    if isinstance(content_blocks, str):
        texts.append(content_blocks)
    elif isinstance(content_blocks, list):
        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type in {"thinking", "redacted_thinking"}:
                reasoning_present = True
                continue
            text = block.get("text")
            if block_type == "text" and isinstance(text, str):
                texts.append(text)
    content = "".join(texts).strip()
    if not content:
        raise LlmProviderError(
            LlmErrorCode.EMPTY_CONTENT,
            message="LLM response content is empty",
            retryable=False,
            http_status=http_response.status_code,
        )
    response_model = body.get("model")
    model_id = (
        response_model
        if isinstance(response_model, str) and response_model.strip()
        else fallback_model
    )
    stop_reason = body.get("stop_reason")
    finish_reason = stop_reason if isinstance(stop_reason, str) else None
    return LlmResponse(
        content=content,
        provider_name="ANTHROPIC_COMPATIBLE",
        model_id=model_id,
        reasoning_present=reasoning_present,
        finish_reason=finish_reason,
    )
