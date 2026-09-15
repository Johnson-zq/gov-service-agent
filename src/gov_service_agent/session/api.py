"""F11 Session HTTP APIRouter factory (mountable capability; no main.py activation)."""

from __future__ import annotations

import json
import logging
from typing import Callable
from uuid import UUID

from fastapi import APIRouter, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from starlette.requests import Request

from gov_service_agent.session.models import (
    SessionDomainError,
    SessionErrorBody,
    SessionErrorCode,
    SessionTurnError,
    SessionTurnFailedStatus,
    SessionTurnRequest,
    SessionTurnSuccess,
    safe_error_message,
)
from gov_service_agent.session.service import SessionTurnService

logger = logging.getLogger("gov_service_agent")

_HTTP_STATUS_BY_CODE: dict[SessionErrorCode, int] = {
    SessionErrorCode.INVALID_REQUEST: 422,
    SessionErrorCode.SESSION_NOT_FOUND: 404,
    SessionErrorCode.SESSION_EXPIRED: 410,
    SessionErrorCode.SESSION_CONFLICT: 409,
    SessionErrorCode.REQUEST_ID_REUSE_CONFLICT: 409,
    SessionErrorCode.REQUEST_IN_PROGRESS: 409,
    SessionErrorCode.CHECKPOINT_INVALID: 500,
    SessionErrorCode.CHECKPOINT_VERSION_UNSUPPORTED: 500,
    SessionErrorCode.PERSISTENCE_UNAVAILABLE: 503,
    SessionErrorCode.AUDIT_PERSISTENCE_FAILED: 503,
    SessionErrorCode.AGENT_TURN_FAILED: 500,
    SessionErrorCode.UNEXPECTED_INTERNAL_ERROR: 500,
}


def _error_response(
    code: SessionErrorCode,
    *,
    request_id: str | None,
    session_id: str | None,
) -> JSONResponse:
    payload = SessionTurnError(
        request_id=request_id,
        session_id=session_id,
        status=SessionTurnFailedStatus.FAILED,
        error=SessionErrorBody(code=code, message=safe_error_message(code)),
    )
    return JSONResponse(
        status_code=_HTTP_STATUS_BY_CODE[code],
        content=payload.model_dump(mode="json"),
    )


def _optional_uuid4(value: object) -> str | None:
    if value is None:
        return None
    try:
        uuid_value = UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None
    if uuid_value.version != 4:
        return None
    return str(uuid_value)


def _safe_ids_from_request(request: Request) -> tuple[str | None, str | None]:
    """Extract UUID4 ids only; never echo raw input or validation details."""
    try:
        body = getattr(request, "_body", None)
        if not isinstance(body, (bytes, bytearray)) or not body:
            return None, None
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            return None, None
        request_id = _optional_uuid4(payload.get("request_id"))
        session_raw = payload.get("session_id")
        if isinstance(session_raw, str) and session_raw.strip() == "":
            session_id = None
        else:
            session_id = _optional_uuid4(session_raw)
        return request_id, session_id
    except Exception:
        return None, None


class SessionAPIRoute(APIRoute):
    """Route-local validation handling so F11 never echoes FastAPI default 422 input."""

    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            try:
                return await original_route_handler(request)
            except RequestValidationError:
                request_id, session_id = _safe_ids_from_request(request)
                return _error_response(
                    SessionErrorCode.INVALID_REQUEST,
                    request_id=request_id,
                    session_id=session_id,
                )

        return custom_route_handler


def create_session_router(service: SessionTurnService) -> APIRouter:
    if service is None:
        raise TypeError("service is required")

    router = APIRouter(route_class=SessionAPIRoute)

    @router.post(
        "/api/v1/session/turn",
        response_model=SessionTurnSuccess,
        responses={
            422: {"model": SessionTurnError},
            404: {"model": SessionTurnError},
            409: {"model": SessionTurnError},
            410: {"model": SessionTurnError},
            500: {"model": SessionTurnError},
            503: {"model": SessionTurnError},
        },
    )
    def session_turn(body: SessionTurnRequest) -> SessionTurnSuccess | Response:
        try:
            return service.handle_turn(body)
        except SessionDomainError as exc:
            return _error_response(
                exc.code,
                request_id=exc.request_id or body.request_id,
                session_id=exc.session_id,
            )
        except ValidationError:
            return _error_response(
                SessionErrorCode.INVALID_REQUEST,
                request_id=getattr(body, "request_id", None),
                session_id=getattr(body, "session_id", None),
            )
        except Exception:
            logger.exception(
                "message=session_turn_unexpected request_id=%s",
                getattr(body, "request_id", None),
            )
            return _error_response(
                SessionErrorCode.UNEXPECTED_INTERNAL_ERROR,
                request_id=getattr(body, "request_id", None),
                session_id=getattr(body, "session_id", None),
            )

    return router
