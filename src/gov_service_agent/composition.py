"""F12 application composition root: wire existing builders without business logic."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from redis import Redis

from gov_service_agent.agent.explanation import LlmExplanationService
from gov_service_agent.agent.interaction import LlmAnswerMapper
from gov_service_agent.agent.turn_processor import GovernmentAgentTurnProcessor
from gov_service_agent.agent.workflow import (
    SlotInteractionDependencies,
    TerminalConfirmationDependencies,
)
from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.business_graph.loader import load_decision_graph
from gov_service_agent.llm.provider import build_llm_provider
from gov_service_agent.retrieval.service import SemanticRetrievalService
from gov_service_agent.session.api import create_session_router
from gov_service_agent.session.service import SessionTurnService
from gov_service_agent.session.store import RedisSessionConfig, RedisSessionStore
from gov_service_agent.settings import Settings, get_settings

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_GRAPH_PATH = _REPO_ROOT / "data" / "graphs" / "demo" / "social_security.json"
_DEMO_BUSINESS_PATH = _REPO_ROOT / "data" / "demo" / "demo_ss_001.json"


def build_session_router(settings: Settings | None = None) -> APIRouter:
    """Assemble Production Session router with GovernmentAgentTurnProcessor."""
    resolved = settings if settings is not None else get_settings()

    decision_graph = load_decision_graph(_DEMO_GRAPH_PATH)
    business_repository = JsonBusinessRepository.from_paths([_DEMO_BUSINESS_PATH])

    llm_provider = build_llm_provider(resolved)
    slot_dependencies = SlotInteractionDependencies(
        answer_mapper=LlmAnswerMapper(llm_provider),
        explanation_service=LlmExplanationService(llm_provider),
        decision_graph=decision_graph,
        business_repository=business_repository,
    )
    terminal_dependencies = TerminalConfirmationDependencies(
        business_repository=business_repository,
    )
    retrieval_service = SemanticRetrievalService(settings=resolved)
    processor = GovernmentAgentTurnProcessor(
        decision_graph=decision_graph,
        business_repository=business_repository,
        retrieval_service=retrieval_service,
        slot_dependencies=slot_dependencies,
        terminal_dependencies=terminal_dependencies,
    )

    password: str | None = None
    if resolved.redis_password is not None:
        password = resolved.redis_password.get_secret_value()

    redis_client = Redis(
        host=resolved.redis_host,
        port=resolved.redis_port,
        db=resolved.redis_db,
        username=resolved.redis_username,
        password=password,
        decode_responses=True,
    )
    store = RedisSessionStore(
        redis_client,
        RedisSessionConfig(
            key_prefix=resolved.redis_key_prefix,
            session_ttl_seconds=resolved.session_ttl_seconds,
            session_expired_marker_ttl_seconds=(
                resolved.session_expired_marker_ttl_seconds
            ),
            audit_ttl_seconds=resolved.audit_ttl_seconds,
            request_dedup_ttl_seconds=resolved.request_dedup_ttl_seconds,
            request_lock_ttl_seconds=resolved.request_lock_ttl_seconds,
            session_lock_ttl_seconds=resolved.session_lock_ttl_seconds,
        ),
    )
    service = SessionTurnService(
        store=store,
        processor=processor,
        max_input_chars=resolved.session_max_input_chars,
        session_ttl_seconds=resolved.session_ttl_seconds,
    )
    return create_session_router(service)
