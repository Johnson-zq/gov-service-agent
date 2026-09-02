"""Database connectivity readiness (Local-First; not schema/migration status)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import text
from sqlalchemy.engine.url import make_url

from gov_service_agent.db.runtime import get_engine
from gov_service_agent.settings import Settings, get_settings

logger = logging.getLogger("gov_service_agent")


class DbReadinessStatus(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"
    READY = "READY"


@dataclass(frozen=True, slots=True)
class DbReadinessResult:
    status: DbReadinessStatus
    error_type: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None


@dataclass(frozen=True, slots=True)
class _SafeUrlParts:
    host: str | None
    port: int | None
    database: str | None


def _safe_url_parts(database_url: str) -> _SafeUrlParts:
    parsed = make_url(database_url)
    return _SafeUrlParts(
        host=parsed.host,
        port=parsed.port,
        database=parsed.database,
    )


def check_db(settings: Settings | None = None) -> DbReadinessResult:
    """
    Connectivity readiness only: configured URL + connect + SELECT 1.

    Does not inspect pg_extension or alembic_version.
    """
    resolved = settings or get_settings()
    if resolved.database_url is None:
        return DbReadinessResult(status=DbReadinessStatus.NOT_CONFIGURED)

    safe = _safe_url_parts(resolved.database_url)

    try:
        engine = get_engine(resolved)
        if engine is None:
            return DbReadinessResult(status=DbReadinessStatus.NOT_CONFIGURED)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return DbReadinessResult(
            status=DbReadinessStatus.READY,
            host=safe.host,
            port=safe.port,
            database=safe.database,
        )
    except Exception as exc:
        logger.warning(
            "message=db_readiness_unavailable error_type=%s host=%s port=%s database=%s",
            type(exc).__name__,
            safe.host,
            safe.port,
            safe.database,
        )
        return DbReadinessResult(
            status=DbReadinessStatus.UNAVAILABLE,
            error_type=type(exc).__name__,
            host=safe.host,
            port=safe.port,
            database=safe.database,
        )
