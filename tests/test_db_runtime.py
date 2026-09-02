"""Unit tests for F05 DB runtime and readiness (no Docker)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gov_service_agent.db.readiness import (
    DbReadinessResult,
    DbReadinessStatus,
    check_db,
)
from gov_service_agent.db.runtime import (
    _reset_db_runtime_for_tests,
    get_engine,
    get_session_factory,
)
from gov_service_agent.settings import Settings, get_settings

_URL_A = (
    "postgresql+psycopg://govagent:change_me_local_only@"
    "localhost:5432/gov_service_agent"
)
_URL_B = (
    "postgresql+psycopg://govagent:change_me_local_only@"
    "localhost:5432/gov_service_agent_alt"
)


@pytest.fixture(autouse=True)
def _reset_runtime_and_settings():
    get_settings.cache_clear()
    _reset_db_runtime_for_tests()
    yield
    _reset_db_runtime_for_tests()
    get_settings.cache_clear()


def _settings_with_url(url: str | None) -> Settings:
    return Settings(
        _env_file=None,
        app_env="LOCAL",
        log_level="INFO",
        database_url=url,
    )


def test_check_db_not_configured_without_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = _settings_with_url(None)
    result = check_db(settings)
    assert result.status == DbReadinessStatus.NOT_CONFIGURED
    assert result.error_type is None


def test_get_engine_without_url_does_not_create_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[str] = []

    def _fake_create_engine(url: str, **kwargs):  # type: ignore[no-untyped-def]
        created.append(url)
        return MagicMock(name="engine")

    monkeypatch.setattr(
        "gov_service_agent.db.runtime.create_engine",
        _fake_create_engine,
    )
    assert get_engine(_settings_with_url(None)) is None
    assert created == []


def test_get_engine_lazy_creates_and_reuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engines: list[MagicMock] = []

    def _fake_create_engine(url: str, **kwargs):  # type: ignore[no-untyped-def]
        engine = MagicMock(name=f"engine:{url}")
        engines.append(engine)
        return engine

    monkeypatch.setattr(
        "gov_service_agent.db.runtime.create_engine",
        _fake_create_engine,
    )
    settings = _settings_with_url(_URL_A)
    first = get_engine(settings)
    second = get_engine(settings)
    assert first is second
    assert len(engines) == 1


def test_url_change_disposes_old_engine_and_invalidates_session_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engines: list[MagicMock] = []

    def _fake_create_engine(url: str, **kwargs):  # type: ignore[no-untyped-def]
        engine = MagicMock(name=f"engine:{url}")
        engines.append(engine)
        return engine

    monkeypatch.setattr(
        "gov_service_agent.db.runtime.create_engine",
        _fake_create_engine,
    )
    first_settings = _settings_with_url(_URL_A)
    first_engine = get_engine(first_settings)
    first_factory = get_session_factory(first_settings)
    assert first_engine is not None
    assert first_factory is not None

    second_settings = _settings_with_url(_URL_B)
    second_engine = get_engine(second_settings)
    second_factory = get_session_factory(second_settings)

    first_engine.dispose.assert_called_once()
    assert second_engine is not first_engine
    assert second_factory is not first_factory
    assert len(engines) == 2


def test_reset_helper_disposes_and_clears_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = MagicMock(name="engine")

    def _fake_create_engine(url: str, **kwargs):  # type: ignore[no-untyped-def]
        return engine

    monkeypatch.setattr(
        "gov_service_agent.db.runtime.create_engine",
        _fake_create_engine,
    )
    settings = _settings_with_url(_URL_A)
    assert get_engine(settings) is engine
    assert get_session_factory(settings) is not None

    _reset_db_runtime_for_tests()
    engine.dispose.assert_called()
    assert get_engine(_settings_with_url(None)) is None


def test_get_session_factory_without_url_returns_none() -> None:
    assert get_session_factory(_settings_with_url(None)) is None


def test_session_factory_binds_current_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = MagicMock(name="engine")
    captured: dict[str, object] = {}

    def _fake_create_engine(url: str, **kwargs):  # type: ignore[no-untyped-def]
        return engine

    def _fake_sessionmaker(*, bind):  # type: ignore[no-untyped-def]
        captured["bind"] = bind
        return MagicMock(name="sessionmaker")

    monkeypatch.setattr(
        "gov_service_agent.db.runtime.create_engine",
        _fake_create_engine,
    )
    monkeypatch.setattr(
        "gov_service_agent.db.runtime.sessionmaker",
        _fake_sessionmaker,
    )
    factory = get_session_factory(_settings_with_url(_URL_A))
    assert factory is not None
    assert captured["bind"] is engine


def test_check_db_unavailable_on_connect_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = MagicMock(name="engine")
    engine.connect.side_effect = OSError("connection refused")

    monkeypatch.setattr(
        "gov_service_agent.db.runtime.create_engine",
        lambda *args, **kwargs: engine,
    )
    result = check_db(_settings_with_url(_URL_A))
    assert result.status == DbReadinessStatus.UNAVAILABLE
    assert result.error_type == "OSError"
    assert result.host == "localhost"
    assert result.port == 5432
    assert result.database == "gov_service_agent"
    assert not hasattr(result, "database_url")
    assert "password" not in result.__dataclass_fields__


def test_check_db_ready_on_select_one_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = MagicMock(name="connection")
    connection.__enter__.return_value = connection
    connection.__exit__.return_value = False
    connection.execute.return_value = None

    engine = MagicMock(name="engine")
    engine.connect.return_value = connection

    monkeypatch.setattr(
        "gov_service_agent.db.runtime.create_engine",
        lambda *args, **kwargs: engine,
    )
    result = check_db(_settings_with_url(_URL_A))
    assert result.status == DbReadinessStatus.READY
    assert result.error_type is None
    sql = connection.execute.call_args.args[0]
    assert str(sql) == "SELECT 1"


def test_check_db_does_not_query_extension_or_alembic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = MagicMock(name="connection")
    connection.__enter__.return_value = connection
    connection.__exit__.return_value = False
    executed: list[str] = []

    def _capture(statement):  # type: ignore[no-untyped-def]
        executed.append(str(statement))
        return None

    connection.execute.side_effect = _capture
    engine = MagicMock(name="engine")
    engine.connect.return_value = connection
    monkeypatch.setattr(
        "gov_service_agent.db.runtime.create_engine",
        lambda *args, **kwargs: engine,
    )

    check_db(_settings_with_url(_URL_A))
    assert executed == ["SELECT 1"]
    joined = " ".join(executed).lower()
    assert "pg_extension" not in joined
    assert "alembic_version" not in joined


def test_readiness_result_excludes_secrets() -> None:
    result = DbReadinessResult(
        status=DbReadinessStatus.READY,
        host="localhost",
        port=5432,
        database="gov_service_agent",
    )
    fields = set(result.__dataclass_fields__)
    assert "database_url" not in fields
    assert "username" not in fields
    assert "password" not in fields
    assert "error_message" not in fields


def test_unavailable_log_avoids_url_and_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = MagicMock(name="engine")
    engine.connect.side_effect = RuntimeError("boom")
    monkeypatch.setattr(
        "gov_service_agent.db.runtime.create_engine",
        lambda *args, **kwargs: engine,
    )
    records: list[str] = []

    def _capture(msg: str, *args):  # type: ignore[no-untyped-def]
        records.append(msg % args if args else msg)

    monkeypatch.setattr(
        "gov_service_agent.db.readiness.logger.warning",
        _capture,
    )
    check_db(_settings_with_url(_URL_A))
    joined = " ".join(records)
    assert "change_me_local_only" not in joined
    assert _URL_A not in joined
    assert "error_type=RuntimeError" in joined
    assert "host=localhost" in joined


def test_import_main_does_not_create_engine_or_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    def _fake_create_engine(*args, **kwargs):  # type: ignore[no-untyped-def]
        called.append("create_engine")
        return MagicMock()

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        "gov_service_agent.db.runtime.create_engine",
        _fake_create_engine,
    )
    import importlib

    import gov_service_agent.main as main_module

    importlib.reload(main_module)
    assert called == []
    assert main_module.app is not None
