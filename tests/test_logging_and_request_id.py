"""Tests for F01 logging, request_id, and access log."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gov_service_agent.logging_config import (
    ACCESS_LOGGER_NAME,
    APP_LOGGER_NAME,
    setup_logging,
)
from gov_service_agent.main import app
from gov_service_agent.middleware.request_context import (
    RequestContextMiddleware,
    get_request_id,
)
from gov_service_agent.settings import Settings, get_settings

_HANDLER_OWNED_ATTR = "_gov_service_agent_owned"


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _owned_handlers(logger: logging.Logger) -> list[logging.Handler]:
    return [
        handler
        for handler in logger.handlers
        if getattr(handler, _HANDLER_OWNED_ATTR, False)
    ]


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def log_capture() -> Iterator[_ListHandler]:
    handler = _ListHandler()
    handler.setLevel(logging.DEBUG)
    logger = logging.getLogger(APP_LOGGER_NAME)
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)


def test_health_response_has_x_request_id() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    request_id = response.headers.get("x-request-id")
    assert request_id is not None
    uuid.UUID(request_id)


def test_two_requests_have_different_request_ids() -> None:
    client = TestClient(app)
    first = client.get("/health").headers["x-request-id"]
    second = client.get("/health").headers["x-request-id"]
    assert first != second


def test_client_x_request_id_is_ignored() -> None:
    client = TestClient(app)
    client_id = str(uuid.uuid4())
    response = client.get("/health", headers={"X-Request-ID": client_id})
    server_id = response.headers["x-request-id"]
    assert server_id != client_id
    uuid.UUID(server_id)


def test_access_log_fields(log_capture: _ListHandler) -> None:
    client = TestClient(app)
    response = client.get("/health")
    request_id = response.headers["x-request-id"]
    messages = [record.getMessage() for record in log_capture.records]
    access_lines = [msg for msg in messages if "status_code=" in msg]
    assert access_lines, f"no access log in {messages}"
    line = access_lines[-1]
    assert f"request_id={request_id}" in line
    assert "method=GET" in line
    assert "path=/health" in line
    assert "status_code=200" in line
    assert "duration_ms=" in line


def test_access_log_path_excludes_query_string(log_capture: _ListHandler) -> None:
    client = TestClient(app)
    client.get("/health?x=1")
    messages = [record.getMessage() for record in log_capture.records]
    access_lines = [msg for msg in messages if "path=" in msg and "status_code=" in msg]
    assert access_lines
    line = access_lines[-1]
    assert "path=/health" in line
    assert "x=1" not in line
    assert "?" not in line


def test_contextvar_reset_after_request() -> None:
    client = TestClient(app)
    client.get("/health")
    assert get_request_id() is None


def test_unhandled_exception_logs_request_id_and_resets(
    log_capture: _ListHandler,
) -> None:
    boom_app = FastAPI()
    boom_app.add_middleware(RequestContextMiddleware)

    @boom_app.get("/boom")
    def boom() -> None:
        raise RuntimeError("boom")

    setup_logging(Settings(_env_file=None))
    client = TestClient(boom_app, raise_server_exceptions=True)
    with pytest.raises(RuntimeError, match="boom"):
        client.get("/boom")

    assert get_request_id() is None
    error_messages = [
        record.getMessage()
        for record in log_capture.records
        if "unhandled_exception" in record.getMessage()
    ]
    assert error_messages
    assert "request_id=" in error_messages[-1]
    assert "method=GET" in error_messages[-1]
    assert "path=/boom" in error_messages[-1]
    assert "duration_ms=" in error_messages[-1]


def test_setup_logging_is_idempotent() -> None:
    """Design contract: repeated setup_logging keeps one owned StreamHandler."""
    settings = Settings(_env_file=None)
    setup_logging(settings)
    setup_logging(settings)
    setup_logging(settings)

    app_logger = logging.getLogger(APP_LOGGER_NAME)
    access_logger = logging.getLogger(ACCESS_LOGGER_NAME)

    assert len(_owned_handlers(app_logger)) == 1
    assert len(access_logger.handlers) == 0

    probe = _ListHandler()
    probe.setLevel(logging.DEBUG)
    app_logger.addHandler(probe)
    try:
        app_logger.info("idempotency_probe message=once")
        probe_messages = [
            record.getMessage()
            for record in probe.records
            if "idempotency_probe" in record.getMessage()
        ]
        assert len(probe_messages) == 1
    finally:
        app_logger.removeHandler(probe)
