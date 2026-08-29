"""Unit tests for F01 Settings (isolated from real .env)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from gov_service_agent.settings import AppEnv, LogLevel, Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults_without_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.app_env == AppEnv.LOCAL
    assert settings.log_level == LogLevel.INFO


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
    settings = Settings(_env_file=None)
    assert settings.app_env == expected


def test_invalid_app_env_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "PROD")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
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
    settings = Settings(_env_file=None)
    assert settings.log_level == expected


def test_invalid_log_level_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_env_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "TEST")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
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
    settings = Settings(_env_file=None)
    assert settings.app_env == AppEnv.LOCAL
    assert settings.log_level == LogLevel.INFO


def test_unknown_env_file_key_fail_fast(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
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
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second
    assert first.app_env == AppEnv.DEV
