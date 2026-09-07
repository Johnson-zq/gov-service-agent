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


_EMBEDDING_ENV_KEYS = (
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL_ID",
    "EMBEDDING_MODEL_PATH",
    "EMBEDDING_DEVICE",
    "RETRIEVAL_TOP_K",
    "RETRIEVAL_MIN_SCORE",
)

_LLM_ENV_KEYS = (
    "LLM_PROVIDER",
    "LLM_MODEL_ID",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
)


@pytest.fixture(autouse=True)
def _clear_settings_cache(monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    for key in _EMBEDDING_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key in _LLM_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
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
    assert settings.embedding_provider is None
    assert settings.embedding_model_id is None
    assert settings.embedding_model_path is None
    assert settings.embedding_device == "auto"
    assert settings.retrieval_top_k == 5
    assert settings.retrieval_min_score == 0.50
    assert settings.llm_provider is None
    assert settings.llm_model_id is None
    assert settings.llm_base_url is None
    assert settings.llm_api_key is None
    assert settings.llm_timeout_seconds == 60.0
    assert settings.llm_max_retries == 1


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


def test_f06_embedding_keys_allowed_in_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=LOCAL\n"
        "LOG_LEVEL=INFO\n"
        "EMBEDDING_PROVIDER=LOCAL_SENTENCE_TRANSFORMER\n"
        "EMBEDDING_MODEL_ID=AI-ModelScope/gte-base-zh\n"
        "EMBEDDING_MODEL_PATH=models/placeholder\n"
        "EMBEDDING_DEVICE=cpu\n"
        "RETRIEVAL_TOP_K=5\n"
        "RETRIEVAL_MIN_SCORE=0.50\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=str(env_file))
    assert settings.embedding_provider == "LOCAL_SENTENCE_TRANSFORMER"
    assert settings.embedding_model_id == "AI-ModelScope/gte-base-zh"
    assert settings.embedding_model_path == "models/placeholder"
    assert settings.embedding_device == "cpu"
    assert "EMBEDDING_PROVIDER" in APPLICATION_DOTENV_KEYS


@pytest.mark.parametrize("device", ["auto", "cpu", "cuda"])
def test_valid_embedding_device(
    monkeypatch: pytest.MonkeyPatch, device: str
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("EMBEDDING_DEVICE", device)
    settings = Settings(_env_file=None)
    assert settings.embedding_device == device


def test_invalid_embedding_device_fail_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("EMBEDDING_DEVICE", "gpu")
    monkeypatch.setenv(
        "EMBEDDING_PROVIDER", "LOCAL_SENTENCE_TRANSFORMER"
    )
    monkeypatch.setenv("EMBEDDING_MODEL_ID", "fake-model")
    monkeypatch.setenv("EMBEDDING_MODEL_PATH", "secret-local-model-path")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    message = str(exc_info.value)
    assert "secret-local-model-path" not in message
    assert _VALID_DATABASE_URL not in message


@pytest.mark.parametrize("top_k", [1, 5, 50])
def test_valid_retrieval_top_k(
    monkeypatch: pytest.MonkeyPatch, top_k: int
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RETRIEVAL_TOP_K", str(top_k))
    settings = Settings(_env_file=None)
    assert settings.retrieval_top_k == top_k


@pytest.mark.parametrize("top_k", [0, 51])
def test_invalid_retrieval_top_k(
    monkeypatch: pytest.MonkeyPatch, top_k: int
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RETRIEVAL_TOP_K", str(top_k))
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("score", [-1.0, 0.0, 0.50, 1.0])
def test_valid_retrieval_min_score(
    monkeypatch: pytest.MonkeyPatch, score: float
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RETRIEVAL_MIN_SCORE", str(score))
    settings = Settings(_env_file=None)
    assert settings.retrieval_min_score == score


@pytest.mark.parametrize("score", [-1.01, 1.01])
def test_invalid_retrieval_min_score(
    monkeypatch: pytest.MonkeyPatch, score: float
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RETRIEVAL_MIN_SCORE", str(score))
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_partial_embedding_config_fail_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "LOCAL_SENTENCE_TRANSFORMER")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_llm_provider_blank_becomes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "  ")
    settings = Settings(_env_file=None)
    assert settings.llm_provider is None


@pytest.mark.parametrize("value", ["DEMO", "OPENAI_COMPATIBLE", "demo"])
def test_valid_llm_provider(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("LLM_PROVIDER", value)
    settings = Settings(_env_file=None)
    assert settings.llm_provider == value.upper()


def test_unknown_llm_provider_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "WEIRD")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_llm_model_id_blank_becomes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL_ID", " \t ")
    settings = Settings(_env_file=None)
    assert settings.llm_model_id is None


def test_llm_base_url_blank_becomes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "")
    settings = Settings(_env_file=None)
    assert settings.llm_base_url is None


@pytest.mark.parametrize(
    "url",
    [
        "http://llm.test/v1",
        "https://llm.test/v1",
        "http://127.0.0.1:8000/v1",
    ],
)
def test_valid_llm_base_url(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("LLM_BASE_URL", url)
    settings = Settings(_env_file=None)
    assert settings.llm_base_url == url


@pytest.mark.parametrize(
    "url",
    [
        "http://user:pass@llm.test/v1",
        "http://user@llm.test/v1",
        "http://llm.test/v1?x=1",
        "http://llm.test/v1#frag",
        "ftp://llm.test/v1",
        "http:///nohost",
    ],
)
def test_invalid_llm_base_url(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("LLM_BASE_URL", url)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    message = str(exc_info.value)
    assert "pass" not in message or "LLM_BASE_URL" in message
    assert "user:pass" not in message


def test_llm_api_key_blank_becomes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "  ")
    settings = Settings(_env_file=None)
    assert settings.llm_api_key is None


def test_llm_api_key_is_secret_str(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import SecretStr

    monkeypatch.setenv("LLM_API_KEY", "SUPER_SECRET_TEST_TOKEN")
    settings = Settings(_env_file=None)
    assert isinstance(settings.llm_api_key, SecretStr)
    assert "SUPER_SECRET_TEST_TOKEN" not in repr(settings)
    assert "SUPER_SECRET_TEST_TOKEN" not in str(settings)


@pytest.mark.parametrize("timeout", [1.0, 60.0, 300.0])
def test_valid_llm_timeout(monkeypatch: pytest.MonkeyPatch, timeout: float) -> None:
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", str(timeout))
    settings = Settings(_env_file=None)
    assert settings.llm_timeout_seconds == timeout


@pytest.mark.parametrize("timeout", [0.9, 300.1])
def test_invalid_llm_timeout(monkeypatch: pytest.MonkeyPatch, timeout: float) -> None:
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", str(timeout))
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("retries", [0, 1, 3])
def test_valid_llm_max_retries(monkeypatch: pytest.MonkeyPatch, retries: int) -> None:
    monkeypatch.setenv("LLM_MAX_RETRIES", str(retries))
    settings = Settings(_env_file=None)
    assert settings.llm_max_retries == retries


@pytest.mark.parametrize("retries", [-1, 4])
def test_invalid_llm_max_retries(monkeypatch: pytest.MonkeyPatch, retries: int) -> None:
    monkeypatch.setenv("LLM_MAX_RETRIES", str(retries))
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_llm_dotenv_keys_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=LOCAL\n"
        "LOG_LEVEL=INFO\n"
        "LLM_PROVIDER=DEMO\n"
        "LLM_MODEL_ID=test-model\n"
        "LLM_BASE_URL=http://llm.test/v1\n"
        "LLM_API_KEY=test-secret\n"
        "LLM_TIMEOUT_SECONDS=60\n"
        "LLM_MAX_RETRIES=1\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=str(env_file))
    assert settings.llm_provider == "DEMO"
    assert "LLM_PROVIDER" in APPLICATION_DOTENV_KEYS
    assert "LLM_PROVIDER" in KNOWN_DOTENV_KEYS


def test_typo_llm_dotenv_key_fail_fast(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=LOCAL\nLOG_LEVEL=INFO\nLLM_PROVIDERR=DEMO\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unknown settings keys"):
        Settings(_env_file=str(env_file))


def test_run_llm_real_not_in_settings_keys() -> None:
    assert "RUN_LLM_REAL" not in KNOWN_DOTENV_KEYS
    assert "RUN_LLM_REAL" not in APPLICATION_DOTENV_KEYS
    assert "run_llm_real" not in Settings.model_fields


def test_llm_api_key_validation_error_hides_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "WEIRD")
    monkeypatch.setenv("LLM_API_KEY", "SUPER_SECRET_TEST_TOKEN")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    message = str(exc_info.value)
    assert "SUPER_SECRET_TEST_TOKEN" not in message
