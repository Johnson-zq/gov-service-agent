"""Pure ASGI middleware: request_id, access log, X-Request-ID."""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any, Callable, MutableMapping

ACCESS_LOGGER = logging.getLogger("gov_service_agent.access")
APP_LOGGER = logging.getLogger("gov_service_agent")

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Return current request_id from ContextVar, if any."""
    return request_id_ctx.get()


class RequestContextMiddleware:
    """
    Pure ASGI middleware (not BaseHTTPMiddleware).

    - Always generates server-side UUID4 request_id (ignores client X-Request-ID)
    - Sets X-Request-ID on normal http.response.start
    - Writes access log on successful response completion path
    - On unhandled exception: error log + re-raise; does not force 500 headers
    """

    def __init__(self, app: Callable[..., Any]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: Callable[..., Any],
        send: Callable[..., Any],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        token = request_id_ctx.set(request_id)
        method = scope.get("method", "")
        path = scope.get("path", "")
        started = time.perf_counter()
        status_code: int | None = None

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
            duration_ms = int((time.perf_counter() - started) * 1000)
            if status_code is not None:
                ACCESS_LOGGER.info(
                    "request_id=%s method=%s path=%s status_code=%s duration_ms=%s",
                    request_id,
                    method,
                    path,
                    status_code,
                    duration_ms,
                )
        except Exception:
            duration_ms = int((time.perf_counter() - started) * 1000)
            APP_LOGGER.exception(
                "unhandled_exception request_id=%s method=%s path=%s duration_ms=%s",
                request_id,
                method,
                path,
                duration_ms,
            )
            raise
        finally:
            request_id_ctx.reset(token)
