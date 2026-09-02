"""Integration tests for F05 PostgreSQL + pgvector + Alembic (Docker required)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"
_REQUIRED_TEST_DATABASE = "gov_service_agent_test"


def _validate_test_database_url(test_url: str) -> None:
    """
    Guard destructive migration tests.

    Must run before any Alembic upgrade/downgrade.
    Fail (never skip) when the target is not the frozen test database name.
    """
    parsed = make_url(test_url)
    if parsed.drivername != "postgresql+psycopg":
        pytest.fail(
            "TEST_DATABASE_URL driver must be postgresql+psycopg "
            f"(got {parsed.drivername!r})"
        )
    if parsed.database != _REQUIRED_TEST_DATABASE:
        pytest.fail(
            "TEST_DATABASE_URL database must be "
            f"{_REQUIRED_TEST_DATABASE!r} (got {parsed.database!r})"
        )


def _vector_extension_exists(database_url: str) -> bool:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                )
            ).first()
            return row is not None
    finally:
        engine.dispose()


def _connectivity_ok(database_url: str) -> bool:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    finally:
        engine.dispose()


def test_validate_test_database_url_rejects_dev_database() -> None:
    """Guard must FAIL before any migration when URL points at the dev DB."""
    bad_url = (
        "postgresql+psycopg://govagent:change_me_local_only@"
        f"localhost:5432/gov_service_agent"
    )
    with pytest.raises(pytest.fail.Exception, match=_REQUIRED_TEST_DATABASE):
        _validate_test_database_url(bad_url)


def test_validate_test_database_url_rejects_wrong_driver() -> None:
    bad_url = (
        "postgresql+asyncpg://govagent:change_me_local_only@"
        f"localhost:5432/{_REQUIRED_TEST_DATABASE}"
    )
    with pytest.raises(pytest.fail.Exception, match="postgresql\\+psycopg"):
        _validate_test_database_url(bad_url)


@pytest.mark.integration
def test_migration_round_trip_on_test_database() -> None:
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url or not test_url.strip():
        pytest.skip("TEST_DATABASE_URL is not set")

    # Guard BEFORE any Alembic command.
    _validate_test_database_url(test_url)

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", test_url)
    # Skip Alembic fileConfig so pytest process loggers are not disabled.
    cfg.attributes["configure_logger"] = False

    # env.py must respect Config URL (not Settings.database_url).
    command.upgrade(cfg, "head")
    assert _vector_extension_exists(test_url)

    command.downgrade(cfg, "base")
    assert _connectivity_ok(test_url)
    # Intentional: baseline downgrade does not DROP vector extension.
    assert _vector_extension_exists(test_url)

    command.upgrade(cfg, "head")
    assert _vector_extension_exists(test_url)
