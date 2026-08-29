"""Runtime settings: APP_ENV and LOG_LEVEL only."""

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


_ALLOWED_ENV_FILE_KEYS = frozenset({"APP_ENV", "LOG_LEVEL"})


class StrictDotEnvSettingsSource(DotEnvSettingsSource):
    """
    Project .env unknown keys fail-fast.

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
            # Same loader path as pydantic-settings DotEnvSettingsSource
            from dotenv import dotenv_values

            values = dotenv_values(path, encoding=encoding)
            for key in values:
                if key is None or key.strip() == "":
                    continue
                if key.upper() not in _ALLOWED_ENV_FILE_KEYS:
                    unknown.append(key)

        if unknown:
            sorted_unknown = ", ".join(sorted(set(unknown)))
            allowed = ", ".join(sorted(_ALLOWED_ENV_FILE_KEYS))
            raise ValueError(
                f"Unknown settings keys in env file: {sorted_unknown}. "
                f"Allowed keys: {allowed}."
            )
        return super().__call__()


class Settings(BaseSettings):
    """Minimal F01 runtime settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=False,
    )

    app_env: AppEnv = AppEnv.LOCAL
    log_level: LogLevel = LogLevel.INFO

    @field_validator("app_env", "log_level", mode="before")
    @classmethod
    def _normalize_upper(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().upper()
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
