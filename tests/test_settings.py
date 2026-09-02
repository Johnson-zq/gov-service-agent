"""Unit tests for F01 Settings + F05 DATABASE_URL / dotenv contract."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from gov_service_agent.settings import (
    APPLICATION_DOTENV_KEYS,
    AppEnv,
    KNOWN_DOTENV_KEYS,
    LogLevel,
    Settings,
    get_settings,
)

_VALID_DATABASE_URL = (
    "postgresql+psycopg://govagent:change_me_local_only@"
    "localhost:5432/gov_service_agent"
)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults_without_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.app_env == AppEnv.LOCAL
    assert settings.log_level == LogLevel.INFO
    assert settings.database_url is None


@pytest.mark.parametrize(
    "value,expected",
    [
        ("LOCAL", AppEnv.LOCAL),
        ("DEV", AppEnv.DEV),
        ("TEST", AppEnv.TEST),
        ("DEMO", AppEnv.DEMO),
        ("local", AppEnv.LOCAL),
        ("dev", AppEnv.DEV),
    ],
)
def test_valid_app_env(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: AppEnv
) -> None:
    monkeypatch.setenv("APP_ENV", value)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.app_env == expected


def test_invalid_app_env_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "PROD")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("DEBUG", LogLevel.DEBUG),
        ("INFO", LogLevel.INFO),
        ("WARNING", LogLevel.WARNING),
        ("ERROR", LogLevel.ERROR),
        ("CRITICAL", LogLevel.CRITICAL),
        ("info", LogLevel.INFO),
    ],
)
def test_valid_log_level(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: LogLevel
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("LOG_LEVEL", value)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.log_level == expected


def test_invalid_log_level_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_env_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "TEST")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.app_env == AppEnv.TEST
    assert settings.log_level == LogLevel.DEBUG


def test_unit_tests_do_not_read_real_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Even if a decoy .env exists in CWD, _env_file=None isolates the test."""
    decoy = tmp_path / ".env"
    decoy.write_text("APP_ENV=DEMO\nLOG_LEVEL=ERROR\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.app_env == AppEnv.LOCAL
    assert settings.log_level == LogLevel.INFO
    assert settings.database_url is None


def test_unknown_env_file_key_fail_fast(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=LOCAL\nLOG_LEVEL=INFO\nUNKNOWN_KEY=oops\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unknown settings keys"):
        Settings(_env_file=str(env_file))


def test_get_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "DEV")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second
    assert first.app_env == AppEnv.DEV


def test_valid_database_url_from_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"APP_ENV=LOCAL\nLOG_LEVEL=INFO\nDATABASE_URL={_VALID_DATABASE_URL}\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=str(env_file))
    assert settings.database_url == _VALID_DATABASE_URL


def test_postgres_keys_allowed_but_not_settings_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=LOCAL\n"
        "LOG_LEVEL=INFO\n"
        "POSTGRES_DB=gov_service_agent\n"
        "POSTGRES_USER=govagent\n"
        "POSTGRES_PASSWORD=change_me_local_only\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=str(env_file))
    assert not hasattr(settings, "postgres_db")
    assert not hasattr(settings, "postgres_user")
    assert not hasattr(settings, "postgres_password")
    assert "POSTGRES_DB" in KNOWN_DOTENV_KEYS
    assert "POSTGRES_DB" not in APPLICATION_DOTENV_KEYS


def test_test_database_url_allowed_but_not_settings_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=LOCAL\n"
        "LOG_LEVEL=INFO\n"
        "TEST_DATABASE_URL=postgresql+psycopg://govagent:change_me_local_only@"
        "localhost:5432/gov_service_agent_test\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=str(env_file))
    assert not hasattr(settings, "test_database_url")
    assert "TEST_DATABASE_URL" in KNOWN_DOTENV_KEYS
    assert "TEST_DATABASE_URL" not in APPLICATION_DOTENV_KEYS


def test_empty_database_url_becomes_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=LOCAL\nLOG_LEVEL=INFO\nDATABASE_URL=\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=str(env_file))
    assert settings.database_url is None


def test_whitespace_database_url_becomes_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "   \t  ")
    settings = Settings(_env_file=None)
    assert settings.database_url is None


@pytest.mark.parametrize(
    "bad_url",
    [
        "sqlite:///tmp.db",
        "mysql://localhost/db",
        "postgresql://localhost/db",
        "postgresql+psycopg2://localhost/db",
        "postgresql+asyncpg://localhost/db",
    ],
)
def test_illegal_database_url_scheme_fail_fast(
    monkeypatch: pytest.MonkeyPatch, bad_url: str
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.setenv("DATABASE_URL", bad_url)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    message = str(exc_info.value)
    assert "DATABASE_URL must be a valid postgresql+psycopg URL" in message
    assert bad_url not in message


def test_malformed_database_url_is_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "not-a-url")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    from sqlalchemy.exc import ArgumentError

    assert not isinstance(exc_info.value, ArgumentError)
    message = str(exc_info.value)
    assert "DATABASE_URL must be a valid postgresql+psycopg URL" in message
    assert "not-a-url" not in message


def test_os_env_noise_does_not_trigger_dotenv_fail_fast(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", "C:\\Windows\\System32")
    monkeypatch.setenv("CONDA_PREFIX", "C:\\conda\\envs\\govagent")
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "govagent")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("APP_ENV=LOCAL\nLOG_LEVEL=INFO\n", encoding="utf-8")
    settings = Settings(_env_file=str(env_file))
    assert settings.app_env == AppEnv.LOCAL
    assert settings.log_level == LogLevel.INFO
