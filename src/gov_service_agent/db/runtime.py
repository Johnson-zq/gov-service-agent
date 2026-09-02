"""SQLAlchemy engine and session factory (lazy, Local-First)."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from gov_service_agent.settings import Settings, get_settings

_engine: Engine | None = None
_engine_bound_url: str | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine(settings: Settings | None = None) -> Engine | None:
    """Return a cached Engine for the current DATABASE_URL, or None if unset."""
    global _engine, _engine_bound_url, _session_factory

    resolved = settings or get_settings()
    database_url = resolved.database_url
    if database_url is None:
        return None

    if _engine is not None and _engine_bound_url == database_url:
        return _engine

    if _engine is not None:
        _engine.dispose()
    _engine = None
    _engine_bound_url = None
    _session_factory = None

    _engine = create_engine(database_url, pool_pre_ping=True)
    _engine_bound_url = database_url
    return _engine


def get_session_factory(
    settings: Settings | None = None,
) -> sessionmaker[Session] | None:
    """Return a sessionmaker bound to the current Engine, or None if no DB URL."""
    global _session_factory

    engine = get_engine(settings)
    if engine is None:
        return None

    if _session_factory is not None:
        return _session_factory

    _session_factory = sessionmaker(bind=engine)
    return _session_factory


def _reset_db_runtime_for_tests() -> None:
    """Dispose engine and clear module caches (tests only; not a public API)."""
    global _engine, _engine_bound_url, _session_factory

    if _engine is not None:
        _engine.dispose()
    _engine = None
    _engine_bound_url = None
    _session_factory = None
