"""Runtime settings: APP_ENV, LOG_LEVEL, and optional DATABASE_URL."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Type

from pydantic import field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import ArgumentError


class AppEnv(str, Enum):
    LOCAL = "LOCAL"
    DEV = "DEV"
    TEST = "TEST"
    DEMO = "DEMO"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


KNOWN_DOTENV_KEYS = frozenset(
    {
        "APP_ENV",
        "LOG_LEVEL",
        "DATABASE_URL",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "TEST_DATABASE_URL",
    }
)

APPLICATION_DOTENV_KEYS = frozenset(
    {
        "APP_ENV",
        "LOG_LEVEL",
        "DATABASE_URL",
    }
)

# pydantic-settings DotEnv source returns model field names.
_APPLICATION_SETTINGS_FIELDS = frozenset(
    {
        "app_env",
        "log_level",
        "database_url",
    }
)


class StrictDotEnvSettingsSource(DotEnvSettingsSource):
    """
    Project .env unknown keys fail-fast (Stage 1), then only Application
    fields enter the Settings payload (Stage 2).

    Process environment remains field-scoped: unrelated vars such as PATH /
    CONDA_* are never bound to this model and do not cause errors.

    Uses DotEnvSettingsSource / dotenv_values (official stack), not a
    hand-written line parser.
    """

    def __call__(self) -> dict[str, Any]:
        env_file = self.env_file
        if env_file is None:
            return super().__call__()

        if isinstance(env_file, (str, Path)):
            files: list[Path] = [Path(env_file)]
        else:
            files = [Path(item) for item in env_file if item is not None]

        unknown: list[str] = []
        encoding = self.env_file_encoding or "utf-8"
        for path in files:
            if not path.is_file():
                continue
            # Stage 1: scan raw dotenv keys (must not rely on super().__call__).
            from dotenv import dotenv_values

            values = dotenv_values(path, encoding=encoding)
            for key in values:
                if key is None or key.strip() == "":
                    continue
                if key.upper() not in KNOWN_DOTENV_KEYS:
                    unknown.append(key)

        if unknown:
            sorted_unknown = ", ".join(sorted(set(unknown)))
            allowed = ", ".join(sorted(KNOWN_DOTENV_KEYS))
            raise ValueError(
                f"Unknown settings keys in env file: {sorted_unknown}. "
                f"Allowed keys: {allowed}."
            )

        # Stage 2: parent maps env aliases to field names; keep only app fields.
        payload = super().__call__()
        return {
            key: value
            for key, value in payload.items()
            if key in _APPLICATION_SETTINGS_FIELDS
        }


class Settings(BaseSettings):
    """F01 runtime settings plus optional F05 DATABASE_URL."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    app_env: AppEnv = AppEnv.LOCAL
    log_level: LogLevel = LogLevel.INFO
    database_url: str | None = None

    @field_validator("app_env", "log_level", mode="before")
    @classmethod
    def _normalize_upper(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "":
                return None
            return stripped
        return value

    @field_validator("database_url", mode="after")
    @classmethod
    def _validate_database_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = make_url(value)
        except ArgumentError:
            raise ValueError(
                "DATABASE_URL must be a valid postgresql+psycopg URL"
            ) from None
        if parsed.drivername != "postgresql+psycopg":
            raise ValueError(
                "DATABASE_URL must be a valid postgresql+psycopg URL"
            )
        return value

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        if isinstance(dotenv_settings, DotEnvSettingsSource):
            strict_kwargs: dict[str, Any] = {
                "env_file": dotenv_settings.env_file,
                "env_file_encoding": dotenv_settings.env_file_encoding,
                "case_sensitive": dotenv_settings.case_sensitive,
                "env_prefix": dotenv_settings.env_prefix,
                "env_nested_delimiter": dotenv_settings.env_nested_delimiter,
                "env_ignore_empty": dotenv_settings.env_ignore_empty,
                "env_parse_none_str": dotenv_settings.env_parse_none_str,
            }
            if hasattr(dotenv_settings, "env_parse_enums"):
                strict_kwargs["env_parse_enums"] = dotenv_settings.env_parse_enums
            strict_dotenv = StrictDotEnvSettingsSource(
                settings_cls,
                **strict_kwargs,
            )
            return (
                init_settings,
                env_settings,
                strict_dotenv,
                file_secret_settings,
            )
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton for application code."""
    return Settings()
