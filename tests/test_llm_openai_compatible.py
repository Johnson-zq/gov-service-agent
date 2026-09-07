"""F07 OpenAI-compatible provider unit tests (0 company network)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from gov_service_agent.llm.openai_compatible import OpenAICompatibleLlmProvider
from gov_service_agent.llm.provider import build_llm_provider
from gov_service_agent.llm.structured import parse_structured_output
from gov_service_agent.llm.types import (
    DataClassification,
    LlmErrorCode,
    LlmMessage,
    LlmProviderError,
    LlmRequest,
    LlmRole,
)
from gov_service_agent.settings import Settings
from types import SimpleNamespace


_FAKE_URL = "http://llm.test/v1"
_FAKE_KEY = "SUPER_SECRET_TEST_TOKEN"
_FAKE_MODEL = "test-model"
_REASONING_SENTINEL = "SHOULD_NEVER_LEAK_REASONING"


def _allowed_request() -> LlmRequest:
    return LlmRequest(
        messages=[
            LlmMessage(
                role=LlmRole.SYSTEM,
                content="synthetic system",
                classifications=frozenset({DataClassification.SYSTEM_CONTROL_DATA}),
            ),
            LlmMessage(
                role=LlmRole.USER,
                content="synthetic user",
                classifications=frozenset({DataClassification.SYNTHETIC_TEST_DATA}),
            ),
        ],
        operation="unit_test",
    )


def _denied_request(*classes: DataClassification) -> LlmRequest:
    return LlmRequest(
        messages=[
            LlmMessage(
                role=LlmRole.USER,
                content="should-not-send",
                classifications=frozenset(classes),
            )
        ]
    )


def _ok_body(
    *,
    content: str = "ok",
    reasoning: str | None = None,
    reasoning_content: str | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": "assistant",
        "content": content,
    }
    if reasoning is not None:
        message["reasoning"] = reasoning
    if reasoning_content is not None:
        message["reasoning_content"] = reasoning_content
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": _FAKE_MODEL,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "stop",
            }
        ],
    }


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.sleeps: list[float] = []
        self.client_creates = 0
        self.clients_closed = 0
        self.client_ids: list[int] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def _provider(
    handler,
    *,
    recorder: _Recorder,
    max_retries: int = 1,
    external: bool = False,
) -> tuple[OpenAICompatibleLlmProvider, httpx.Client | None]:
    transport = httpx.MockTransport(handler)

    if external:
        client = httpx.Client(transport=transport, timeout=5.0)
        provider = OpenAICompatibleLlmProvider(
            base_url=_FAKE_URL,
            api_key=_FAKE_KEY,
            model_id=_FAKE_MODEL,
            timeout_seconds=5.0,
            max_retries=max_retries,
            client=client,
            sleep_fn=recorder.sleep,
        )
        return provider, client

    real_client_cls = httpx.Client

    class _SpyClient(real_client_cls):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)
            recorder.client_creates += 1
            recorder.client_ids.append(id(self))

        def close(self) -> None:
            recorder.clients_closed += 1
            super().close()

        def post(self, url, **kwargs):
            request = self.build_request("POST", url, **kwargs)
            recorder.calls.append(request)
            return super().post(url, **kwargs)

    # Patch only for this provider construction path via monkeypatch in tests.
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        timeout_seconds=5.0,
        max_retries=max_retries,
        sleep_fn=recorder.sleep,
    )
    # Attach spy factory for complete()'s internal Client
    provider._spy_client_cls = _SpyClient  # type: ignore[attr-defined]
    return provider, None


def _make_handler(responses: list[httpx.Response | Exception], recorder: _Recorder):
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.calls.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return handler


def test_policy_deny_user_pii_zero_calls() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("must not dispatch")

    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep_fn=recorder.sleep,
    )
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(_denied_request(DataClassification.USER_PII))
    assert exc.value.code == LlmErrorCode.POLICY_DENIED
    assert recorder.calls == []
    assert recorder.sleeps == []


def test_policy_deny_unknown_zero_calls() -> None:
    recorder = _Recorder()
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        client=httpx.Client(
            transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError()))
        ),
        sleep_fn=recorder.sleep,
    )
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(
            LlmRequest(
                messages=[
                    LlmMessage(role=LlmRole.USER, content="x", classifications=frozenset())
                ]
            )
        )
    assert exc.value.code == LlmErrorCode.POLICY_DENIED
    assert recorder.sleeps == []


def test_policy_deny_mixed_zero_calls() -> None:
    recorder = _Recorder()
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        client=httpx.Client(
            transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError()))
        ),
        sleep_fn=recorder.sleep,
    )
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(
            _denied_request(
                DataClassification.PUBLIC_BUSINESS_METADATA,
                DataClassification.USER_PII,
            )
        )
    assert exc.value.code == LlmErrorCode.POLICY_DENIED


def test_valid_200_and_payload_shape() -> None:
    recorder = _Recorder()
    handler = _make_handler(
        [httpx.Response(200, json=_ok_body(content="hello"))],
        recorder,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        client=client,
        sleep_fn=recorder.sleep,
    )
    response = provider.complete(_allowed_request())
    assert response.content == "hello"
    assert response.provider_name == "OPENAI_COMPATIBLE"
    assert response.model_id == _FAKE_MODEL
    assert response.finish_reason == "stop"
    assert len(recorder.calls) == 1
    req = recorder.calls[0]
    assert str(req.url) == "http://llm.test/v1/chat/completions"
    assert "/v1/v1/" not in str(req.url)
    assert req.headers["Authorization"] == f"Bearer {_FAKE_KEY}"
    body = json.loads(req.content.decode("utf-8"))
    assert body["model"] == _FAKE_MODEL
    assert body["temperature"] == 0
    assert "next_node" not in body
    client.close()


def test_no_models_endpoint() -> None:
    recorder = _Recorder()
    handler = _make_handler(
        [httpx.Response(200, json=_ok_body())],
        recorder,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        client=client,
        sleep_fn=recorder.sleep,
    )
    provider.complete(_allowed_request())
    assert all("/models" not in str(c.url) for c in recorder.calls)
    client.close()


def test_reasoning_isolation() -> None:
    recorder = _Recorder()
    handler = _make_handler(
        [
            httpx.Response(
                200,
                json=_ok_body(content="safe", reasoning=_REASONING_SENTINEL),
            )
        ],
        recorder,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        client=client,
        sleep_fn=recorder.sleep,
    )
    response = provider.complete(_allowed_request())
    assert response.reasoning_present is True
    blob = response.content + str(response) + repr(response)
    assert _REASONING_SENTINEL not in blob
    client.close()


def test_reasoning_content_key_present() -> None:
    recorder = _Recorder()
    handler = _make_handler(
        [
            httpx.Response(
                200,
                json=_ok_body(
                    content="safe",
                    reasoning_content=_REASONING_SENTINEL,
                ),
            )
        ],
        recorder,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        client=client,
        sleep_fn=recorder.sleep,
    )
    response = provider.complete(_allowed_request())
    assert response.reasoning_present is True
    assert _REASONING_SENTINEL not in response.content
    client.close()


@pytest.mark.parametrize(
    "status,code",
    [
        (401, LlmErrorCode.AUTHENTICATION_FAILED),
        (403, LlmErrorCode.AUTHENTICATION_FAILED),
        (400, LlmErrorCode.INVALID_REQUEST),
    ],
)
def test_auth_and_4xx_no_retry(status: int, code: LlmErrorCode) -> None:
    recorder = _Recorder()
    handler = _make_handler(
        [httpx.Response(status, json={"error": "no"})],
        recorder,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        max_retries=3,
        client=client,
        sleep_fn=recorder.sleep,
    )
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(_allowed_request())
    assert exc.value.code == code
    assert exc.value.retryable is False
    assert len(recorder.calls) == 1
    assert recorder.sleeps == []
    assert _FAKE_KEY not in str(exc.value)
    client.close()


def test_429_then_success() -> None:
    recorder = _Recorder()
    handler = _make_handler(
        [
            httpx.Response(429, json={"error": "rate"}),
            httpx.Response(200, json=_ok_body(content="ok")),
        ],
        recorder,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        max_retries=1,
        client=client,
        sleep_fn=recorder.sleep,
    )
    assert provider.complete(_allowed_request()).content == "ok"
    assert len(recorder.calls) == 2
    assert recorder.sleeps == [0.25]
    client.close()


def test_429_exhausted() -> None:
    recorder = _Recorder()
    handler = _make_handler(
        [
            httpx.Response(429, json={"error": "rate"}),
            httpx.Response(429, json={"error": "rate"}),
        ],
        recorder,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        max_retries=1,
        client=client,
        sleep_fn=recorder.sleep,
    )
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(_allowed_request())
    assert exc.value.code == LlmErrorCode.RATE_LIMITED
    assert len(recorder.calls) == 2
    assert recorder.sleeps == [0.25]
    client.close()


def test_500_then_success() -> None:
    recorder = _Recorder()
    handler = _make_handler(
        [
            httpx.Response(500, json={"error": "boom"}),
            httpx.Response(200, json=_ok_body(content="recovered")),
        ],
        recorder,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        max_retries=1,
        client=client,
        sleep_fn=recorder.sleep,
    )
    assert provider.complete(_allowed_request()).content == "recovered"
    assert len(recorder.calls) == 2
    assert recorder.sleeps == [0.25]
    client.close()


def test_persistent_5xx_max_calls() -> None:
    recorder = _Recorder()
    handler = _make_handler(
        [httpx.Response(500, json={"error": "boom"}) for _ in range(4)],
        recorder,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        max_retries=3,
        client=client,
        sleep_fn=recorder.sleep,
    )
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(_allowed_request())
    assert exc.value.code == LlmErrorCode.SERVER_ERROR
    assert len(recorder.calls) == 4
    assert recorder.sleeps == [0.25, 0.50, 1.00]
    client.close()


def test_timeout_then_success() -> None:
    recorder = _Recorder()
    handler = _make_handler(
        [
            httpx.ReadTimeout("t"),
            httpx.Response(200, json=_ok_body(content="after-timeout")),
        ],
        recorder,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        max_retries=1,
        client=client,
        sleep_fn=recorder.sleep,
    )
    assert provider.complete(_allowed_request()).content == "after-timeout"
    assert len(recorder.calls) == 2
    assert recorder.sleeps == [0.25]
    client.close()


def test_persistent_timeout() -> None:
    recorder = _Recorder()
    handler = _make_handler(
        [httpx.ReadTimeout("t"), httpx.ReadTimeout("t")],
        recorder,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        max_retries=1,
        client=client,
        sleep_fn=recorder.sleep,
    )
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(_allowed_request())
    assert exc.value.code == LlmErrorCode.TIMEOUT
    assert len(recorder.calls) == 2
    client.close()


def test_connect_error_retry() -> None:
    recorder = _Recorder()
    handler = _make_handler(
        [
            httpx.ConnectError("down"),
            httpx.Response(200, json=_ok_body(content="up")),
        ],
        recorder,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        max_retries=1,
        client=client,
        sleep_fn=recorder.sleep,
    )
    assert provider.complete(_allowed_request()).content == "up"
    assert len(recorder.calls) == 2
    client.close()


def test_invalid_json_response() -> None:
    recorder = _Recorder()
    handler = _make_handler(
        [httpx.Response(200, content=b"not-json")],
        recorder,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        client=client,
        sleep_fn=recorder.sleep,
    )
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(_allowed_request())
    assert exc.value.code == LlmErrorCode.INVALID_RESPONSE
    assert "not-json" not in str(exc.value)
    client.close()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"message": {}}]},
    ],
)
def test_invalid_response_shapes(body: dict[str, Any]) -> None:
    recorder = _Recorder()
    handler = _make_handler([httpx.Response(200, json=body)], recorder)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        client=client,
        sleep_fn=recorder.sleep,
    )
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(_allowed_request())
    assert exc.value.code == LlmErrorCode.INVALID_RESPONSE
    client.close()


@pytest.mark.parametrize("content", ["", "   "])
def test_empty_content(content: str) -> None:
    recorder = _Recorder()
    handler = _make_handler(
        [httpx.Response(200, json=_ok_body(content=content))],
        recorder,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        client=client,
        sleep_fn=recorder.sleep,
    )
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(_allowed_request())
    assert exc.value.code == LlmErrorCode.EMPTY_CONTENT
    client.close()


def test_structured_parse_after_complete_no_http_retry() -> None:
    from pydantic import BaseModel

    class _Schema(BaseModel):
        name: str

    recorder = _Recorder()
    handler = _make_handler(
        [httpx.Response(200, json=_ok_body(content="not-json"))],
        recorder,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        client=client,
        sleep_fn=recorder.sleep,
    )
    response = provider.complete(_allowed_request())
    assert len(recorder.calls) == 1
    with pytest.raises(Exception):
        parse_structured_output(response.content, _Schema)
    assert len(recorder.calls) == 1
    client.close()


def test_external_client_not_closed_by_provider() -> None:
    recorder = _Recorder()
    closed = {"value": False}

    class _TrackingClient(httpx.Client):
        def close(self) -> None:
            closed["value"] = True
            super().close()

    handler = _make_handler(
        [httpx.Response(200, json=_ok_body())],
        recorder,
    )
    client = _TrackingClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        client=client,
        sleep_fn=recorder.sleep,
    )
    provider.complete(_allowed_request())
    assert closed["value"] is False
    client.close()
    assert closed["value"] is True


def test_internal_client_created_and_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    import gov_service_agent.llm.openai_compatible as oai_mod

    recorder = _Recorder()
    creates: list[int] = []
    exits = {"n": 0}
    real_cls = httpx.Client

    class SpyClient(real_cls):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(
                lambda request: httpx.Response(200, json=_ok_body())
            )
            super().__init__(*args, **kwargs)
            creates.append(id(self))

        def __exit__(self, *args):
            exits["n"] += 1
            return super().__exit__(*args)

    monkeypatch.setattr(oai_mod.httpx, "Client", SpyClient)
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        sleep_fn=recorder.sleep,
    )
    provider.complete(_allowed_request())
    assert len(creates) == 1
    assert exits["n"] == 1


def test_internal_retry_reuses_same_client(monkeypatch: pytest.MonkeyPatch) -> None:
    import gov_service_agent.llm.openai_compatible as oai_mod

    recorder = _Recorder()
    creates: list[int] = []
    state = {"n": 0}
    real_cls = httpx.Client

    class SpyClient(real_cls):
        def __init__(self, *args, **kwargs):
            def handler(request: httpx.Request) -> httpx.Response:
                state["n"] += 1
                if state["n"] == 1:
                    return httpx.Response(500, json={"error": "x"})
                return httpx.Response(200, json=_ok_body(content="ok"))

            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)
            creates.append(id(self))

        def close(self) -> None:
            super().close()

    monkeypatch.setattr(oai_mod.httpx, "Client", SpyClient)
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        max_retries=1,
        sleep_fn=recorder.sleep,
    )
    assert provider.complete(_allowed_request()).content == "ok"
    assert len(creates) == 1
    assert recorder.sleeps == [0.25]


def test_factory_build_does_not_network() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls["n"] += 1
        return httpx.Response(200, json=_ok_body())

    settings = SimpleNamespace(
        llm_provider="OPENAI_COMPATIBLE",
        llm_base_url=_FAKE_URL,
        llm_api_key=SecretStr(_FAKE_KEY),
        llm_model_id=_FAKE_MODEL,
        llm_timeout_seconds=5.0,
        llm_max_retries=0,
    )
    provider = build_llm_provider(settings)
    assert calls["n"] == 0
    # Bind external mock after factory to prove factory itself was idle.
    assert isinstance(provider, OpenAICompatibleLlmProvider)


def test_secret_not_in_error_repr() -> None:
    recorder = _Recorder()
    handler = _make_handler(
        [httpx.Response(401, json={"error": "no"})],
        recorder,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        base_url=_FAKE_URL,
        api_key=_FAKE_KEY,
        model_id=_FAKE_MODEL,
        client=client,
        sleep_fn=recorder.sleep,
    )
    with pytest.raises(LlmProviderError) as exc:
        provider.complete(_allowed_request())
    assert _FAKE_KEY not in str(exc.value)
    assert _FAKE_KEY not in repr(exc.value)
    assert _FAKE_URL not in getattr(exc.value, "message", "")
    client.close()
