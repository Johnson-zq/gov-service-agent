"""F11 Redis session store: keys, locks, checkpoint, audit, idempotency cache."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator, Protocol

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import LockError, RedisError, TimeoutError as RedisTimeoutError
from redis.exceptions import WatchError
from redis.lock import Lock

from gov_service_agent.session.models import (
    AUDIT_SCHEMA_VERSION,
    CHECKPOINT_SCHEMA_VERSION,
    REQUEST_RESULT_SCHEMA_VERSION,
    SESSION_META_SCHEMA_VERSION,
    AuditEvent,
    CachedRequestResult,
    SessionCheckpoint,
    SessionDomainError,
    SessionErrorCode,
    SessionMeta,
    SessionTurnSuccess,
)

logger = logging.getLogger("gov_service_agent")


@dataclass(frozen=True)
class RedisSessionConfig:
    key_prefix: str
    session_ttl_seconds: int
    session_expired_marker_ttl_seconds: int
    audit_ttl_seconds: int
    request_dedup_ttl_seconds: int
    request_lock_ttl_seconds: int
    session_lock_ttl_seconds: int


def dumps_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def loads_json(raw: str | bytes) -> Any:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


_ALLOWED_AUDIT_KEY_TYPES = frozenset({"none", "list"})


def _normalize_redis_type(raw: Any) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)


class SessionStore(Protocol):
    def get_cached_result(self, request_id: str) -> CachedRequestResult | None: ...

    def acquire_request_lock(self, request_id: str) -> Lock: ...

    def acquire_session_lock(self, session_id: str) -> Lock: ...

    def load_active_session(
        self,
        session_id: str,
        *,
        now: datetime,
    ) -> tuple[SessionMeta, SessionCheckpoint]: ...

    def meta_exists(self, session_id: str) -> bool: ...

    def commit_successful_turn(
        self,
        *,
        session_id: str,
        request_id: str,
        expected_revision: int,
        meta: SessionMeta,
        checkpoint: SessionCheckpoint,
        audit_event: AuditEvent,
        cached_result: CachedRequestResult,
    ) -> None: ...

    def append_failure_audit(
        self,
        *,
        session_id: str,
        audit_event: AuditEvent,
    ) -> None: ...


class RedisSessionStore:
    """Concrete Redis-backed SessionStore (HTTP-turn persistence only)."""

    def __init__(self, client: Redis, config: RedisSessionConfig) -> None:
        if client is None:
            raise TypeError("Redis client is required")
        if config is None:
            raise TypeError("RedisSessionConfig is required")
        self._client = client
        self._config = config
        prefix = config.key_prefix.rstrip(":")
        self._prefix = prefix

    def _meta_key(self, session_id: str) -> str:
        return f"{self._prefix}:session:{session_id}:meta"

    def _checkpoint_key(self, session_id: str) -> str:
        return f"{self._prefix}:session:{session_id}:checkpoint"

    def _audit_key(self, session_id: str) -> str:
        return f"{self._prefix}:session:{session_id}:audit"

    def _result_key(self, request_id: str) -> str:
        return f"{self._prefix}:request:{request_id}:result"

    def _request_lock_key(self, request_id: str) -> str:
        return f"{self._prefix}:lock:request:{request_id}"

    def _session_lock_key(self, session_id: str) -> str:
        return f"{self._prefix}:lock:session:{session_id}"

    def get_cached_result(self, request_id: str) -> CachedRequestResult | None:
        try:
            raw = self._client.get(self._result_key(request_id))
        except (RedisConnectionError, RedisTimeoutError, RedisError) as exc:
            logger.warning(
                "message=session_redis_error code=%s request_id=%s",
                SessionErrorCode.PERSISTENCE_UNAVAILABLE.value,
                request_id,
            )
            raise SessionDomainError(
                SessionErrorCode.PERSISTENCE_UNAVAILABLE,
                request_id=request_id,
            ) from exc
        if raw is None:
            return None
        try:
            payload = loads_json(raw)
            cached = CachedRequestResult.model_validate(payload)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.warning(
                "message=session_request_cache_invalid request_id=%s",
                request_id,
            )
            raise SessionDomainError(
                SessionErrorCode.PERSISTENCE_UNAVAILABLE,
                request_id=request_id,
            ) from exc
        if cached.schema_version != REQUEST_RESULT_SCHEMA_VERSION:
            raise SessionDomainError(
                SessionErrorCode.PERSISTENCE_UNAVAILABLE,
                request_id=request_id,
            )
        if cached.request_id != request_id:
            raise SessionDomainError(
                SessionErrorCode.PERSISTENCE_UNAVAILABLE,
                request_id=request_id,
            )
        return CachedRequestResult.model_validate(
            cached.model_dump(mode="json")
        )

    def acquire_request_lock(self, request_id: str) -> Lock:
        return Lock(
            self._client,
            name=self._request_lock_key(request_id),
            timeout=self._config.request_lock_ttl_seconds,
            blocking=False,
            thread_local=True,
        )

    def acquire_session_lock(self, session_id: str) -> Lock:
        return Lock(
            self._client,
            name=self._session_lock_key(session_id),
            timeout=self._config.session_lock_ttl_seconds,
            blocking=False,
            thread_local=True,
        )

    def meta_exists(self, session_id: str) -> bool:
        try:
            return bool(self._client.exists(self._meta_key(session_id)))
        except (RedisConnectionError, RedisTimeoutError, RedisError) as exc:
            raise SessionDomainError(
                SessionErrorCode.PERSISTENCE_UNAVAILABLE,
                session_id=session_id,
            ) from exc

    def load_active_session(
        self,
        session_id: str,
        *,
        now: datetime,
    ) -> tuple[SessionMeta, SessionCheckpoint]:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware UTC")
        meta_key = self._meta_key(session_id)
        checkpoint_key = self._checkpoint_key(session_id)
        try:
            meta_raw = self._client.get(meta_key)
        except (RedisConnectionError, RedisTimeoutError, RedisError) as exc:
            raise SessionDomainError(
                SessionErrorCode.PERSISTENCE_UNAVAILABLE,
                session_id=session_id,
            ) from exc

        if meta_raw is None:
            raise SessionDomainError(
                SessionErrorCode.SESSION_NOT_FOUND,
                session_id=session_id,
            )

        try:
            meta = SessionMeta.model_validate(loads_json(meta_raw))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SessionDomainError(
                SessionErrorCode.CHECKPOINT_INVALID,
                session_id=session_id,
            ) from exc

        if meta.schema_version != SESSION_META_SCHEMA_VERSION:
            raise SessionDomainError(
                SessionErrorCode.CHECKPOINT_VERSION_UNSUPPORTED,
                session_id=session_id,
            )
        if meta.session_id != session_id:
            raise SessionDomainError(
                SessionErrorCode.CHECKPOINT_INVALID,
                session_id=session_id,
            )
        if now > meta.expires_at:
            raise SessionDomainError(
                SessionErrorCode.SESSION_EXPIRED,
                session_id=session_id,
            )

        try:
            checkpoint_raw = self._client.get(checkpoint_key)
        except (RedisConnectionError, RedisTimeoutError, RedisError) as exc:
            raise SessionDomainError(
                SessionErrorCode.PERSISTENCE_UNAVAILABLE,
                session_id=session_id,
            ) from exc

        if checkpoint_raw is None:
            raise SessionDomainError(
                SessionErrorCode.CHECKPOINT_INVALID,
                session_id=session_id,
            )

        try:
            payload = loads_json(checkpoint_raw)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SessionDomainError(
                SessionErrorCode.CHECKPOINT_INVALID,
                session_id=session_id,
            ) from exc

        schema_version = payload.get("schema_version") if isinstance(payload, dict) else None
        if schema_version != CHECKPOINT_SCHEMA_VERSION:
            raise SessionDomainError(
                SessionErrorCode.CHECKPOINT_VERSION_UNSUPPORTED,
                session_id=session_id,
            )

        try:
            checkpoint = SessionCheckpoint.model_validate(payload)
        except (TypeError, ValueError) as exc:
            raise SessionDomainError(
                SessionErrorCode.CHECKPOINT_INVALID,
                session_id=session_id,
            ) from exc

        if checkpoint.session_id != session_id:
            raise SessionDomainError(
                SessionErrorCode.CHECKPOINT_INVALID,
                session_id=session_id,
            )
        if checkpoint.revision != meta.checkpoint_revision:
            raise SessionDomainError(
                SessionErrorCode.CHECKPOINT_INVALID,
                session_id=session_id,
            )
        return meta, checkpoint

    def commit_successful_turn(
        self,
        *,
        session_id: str,
        request_id: str,
        expected_revision: int,
        meta: SessionMeta,
        checkpoint: SessionCheckpoint,
        audit_event: AuditEvent,
        cached_result: CachedRequestResult,
    ) -> None:
        if meta.schema_version != SESSION_META_SCHEMA_VERSION:
            raise SessionDomainError(
                SessionErrorCode.CHECKPOINT_INVALID,
                session_id=session_id,
                request_id=request_id,
            )
        if checkpoint.schema_version != CHECKPOINT_SCHEMA_VERSION:
            raise SessionDomainError(
                SessionErrorCode.CHECKPOINT_VERSION_UNSUPPORTED,
                session_id=session_id,
                request_id=request_id,
            )
        if audit_event.schema_version != AUDIT_SCHEMA_VERSION:
            raise SessionDomainError(
                SessionErrorCode.AUDIT_PERSISTENCE_FAILED,
                session_id=session_id,
                request_id=request_id,
            )
        if cached_result.schema_version != REQUEST_RESULT_SCHEMA_VERSION:
            raise SessionDomainError(
                SessionErrorCode.PERSISTENCE_UNAVAILABLE,
                session_id=session_id,
                request_id=request_id,
            )
        if meta.session_id != session_id or checkpoint.session_id != session_id:
            raise SessionDomainError(
                SessionErrorCode.CHECKPOINT_INVALID,
                session_id=session_id,
                request_id=request_id,
            )
        if checkpoint.revision != meta.checkpoint_revision:
            raise SessionDomainError(
                SessionErrorCode.CHECKPOINT_INVALID,
                session_id=session_id,
                request_id=request_id,
            )
        if expected_revision == 0:
            if meta.checkpoint_revision != 1 or checkpoint.revision != 1:
                raise SessionDomainError(
                    SessionErrorCode.CHECKPOINT_INVALID,
                    session_id=session_id,
                    request_id=request_id,
                )
        elif checkpoint.revision != expected_revision + 1:
            raise SessionDomainError(
                SessionErrorCode.CHECKPOINT_INVALID,
                session_id=session_id,
                request_id=request_id,
            )

        meta_key = self._meta_key(session_id)
        checkpoint_key = self._checkpoint_key(session_id)
        audit_key = self._audit_key(session_id)
        result_key = self._result_key(request_id)
        session_ttl = self._config.session_ttl_seconds
        meta_ttl = (
            self._config.session_ttl_seconds
            + self._config.session_expired_marker_ttl_seconds
        )
        audit_ttl = self._config.audit_ttl_seconds
        result_ttl = self._config.request_dedup_ttl_seconds

        meta_json = dumps_json(meta.model_dump(mode="json"))
        checkpoint_json = dumps_json(checkpoint.model_dump(mode="json"))
        audit_json = dumps_json(audit_event.model_dump(mode="json"))
        result_json = dumps_json(cached_result.model_dump(mode="json"))

        try:
            with self._client.pipeline(True) as pipe:
                while True:
                    try:
                        # Watch meta + audit so TYPE/revision checks stay race-safe.
                        pipe.watch(meta_key, audit_key)
                        current_raw = pipe.get(meta_key)
                        if expected_revision == 0:
                            if current_raw is not None:
                                pipe.unwatch()
                                raise SessionDomainError(
                                    SessionErrorCode.SESSION_CONFLICT,
                                    session_id=session_id,
                                    request_id=request_id,
                                )
                        else:
                            if current_raw is None:
                                pipe.unwatch()
                                raise SessionDomainError(
                                    SessionErrorCode.SESSION_CONFLICT,
                                    session_id=session_id,
                                    request_id=request_id,
                                )
                            current_meta = SessionMeta.model_validate(
                                loads_json(current_raw)
                            )
                            if current_meta.checkpoint_revision != expected_revision:
                                pipe.unwatch()
                                raise SessionDomainError(
                                    SessionErrorCode.SESSION_CONFLICT,
                                    session_id=session_id,
                                    request_id=request_id,
                                )
                        audit_type = _normalize_redis_type(pipe.type(audit_key))
                        if audit_type not in _ALLOWED_AUDIT_KEY_TYPES:
                            pipe.unwatch()
                            raise SessionDomainError(
                                SessionErrorCode.AUDIT_PERSISTENCE_FAILED,
                                session_id=session_id,
                                request_id=request_id,
                            )
                        pipe.multi()
                        pipe.set(meta_key, meta_json, ex=meta_ttl)
                        pipe.set(checkpoint_key, checkpoint_json, ex=session_ttl)
                        pipe.rpush(audit_key, audit_json)
                        pipe.expire(audit_key, audit_ttl)
                        pipe.set(result_key, result_json, ex=result_ttl)
                        pipe.execute()
                        return
                    except WatchError as exc:
                        raise SessionDomainError(
                            SessionErrorCode.SESSION_CONFLICT,
                            session_id=session_id,
                            request_id=request_id,
                        ) from exc
        except SessionDomainError:
            raise
        except (RedisConnectionError, RedisTimeoutError, RedisError) as exc:
            logger.warning(
                "message=session_commit_failed code=%s session_id=%s request_id=%s",
                SessionErrorCode.PERSISTENCE_UNAVAILABLE.value,
                session_id,
                request_id,
            )
            raise SessionDomainError(
                SessionErrorCode.PERSISTENCE_UNAVAILABLE,
                session_id=session_id,
                request_id=request_id,
            ) from exc

    def append_failure_audit(
        self,
        *,
        session_id: str,
        audit_event: AuditEvent,
    ) -> None:
        if audit_event.schema_version != AUDIT_SCHEMA_VERSION:
            raise SessionDomainError(
                SessionErrorCode.AUDIT_PERSISTENCE_FAILED,
                session_id=session_id,
                request_id=audit_event.request_id,
            )
        audit_key = self._audit_key(session_id)
        audit_json = dumps_json(audit_event.model_dump(mode="json"))
        try:
            with self._client.pipeline(True) as pipe:
                while True:
                    try:
                        pipe.watch(audit_key)
                        audit_type = _normalize_redis_type(pipe.type(audit_key))
                        if audit_type not in _ALLOWED_AUDIT_KEY_TYPES:
                            pipe.unwatch()
                            raise SessionDomainError(
                                SessionErrorCode.AUDIT_PERSISTENCE_FAILED,
                                session_id=session_id,
                                request_id=audit_event.request_id,
                            )
                        pipe.multi()
                        pipe.rpush(audit_key, audit_json)
                        pipe.expire(audit_key, self._config.audit_ttl_seconds)
                        pipe.execute()
                        return
                    except WatchError as exc:
                        raise SessionDomainError(
                            SessionErrorCode.AUDIT_PERSISTENCE_FAILED,
                            session_id=session_id,
                            request_id=audit_event.request_id,
                        ) from exc
        except SessionDomainError:
            raise
        except (RedisConnectionError, RedisTimeoutError, RedisError) as exc:
            logger.warning(
                "message=session_failure_audit_failed code=%s session_id=%s request_id=%s",
                SessionErrorCode.AUDIT_PERSISTENCE_FAILED.value,
                session_id,
                audit_event.request_id,
            )
            raise SessionDomainError(
                SessionErrorCode.AUDIT_PERSISTENCE_FAILED,
                session_id=session_id,
                request_id=audit_event.request_id,
            ) from exc


@contextmanager
def hold_lock(lock: Lock, *, code_on_busy: SessionErrorCode, request_id: str | None = None, session_id: str | None = None) -> Iterator[None]:
    acquired = False
    try:
        acquired = bool(lock.acquire(blocking=False))
        if not acquired:
            raise SessionDomainError(
                code_on_busy,
                request_id=request_id,
                session_id=session_id,
            )
        yield
    finally:
        if acquired:
            try:
                lock.release()
            except LockError:
                logger.warning(
                    "message=session_lock_release_failed request_id=%s session_id=%s",
                    request_id,
                    session_id,
                )
