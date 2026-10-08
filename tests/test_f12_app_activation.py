"""F12 composition activation tests. No Redis, PostgreSQL, embedding, or LLM calls."""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from gov_service_agent.agent.turn_processor import GovernmentAgentTurnProcessor
from gov_service_agent.session.models import SessionTurnRequest, SessionTurnSuccess


class SpyRedis:
    """Records construction only. Any command fails the test."""

    commands: list[str] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.args = args
        self.kwargs = kwargs

    def __getattr__(self, name: str) -> object:
        SpyRedis.commands.append(name)
        raise AssertionError(f"unexpected Redis command: {name}")


def test_composition_uses_production_processor_without_eager_io(
    monkeypatch,
) -> None:
    import gov_service_agent.composition as composition
    from gov_service_agent.llm.provider import build_llm_provider
    from gov_service_agent.retrieval.service import SemanticRetrievalService
    from gov_service_agent.settings import Settings

    SpyRedis.commands.clear()
    monkeypatch.setattr(composition, "Redis", SpyRedis)
    retrieve_calls = {"n": 0}
    complete_calls = {"n": 0}

    class GuardRetrieval(SemanticRetrievalService):
        def retrieve(self, query: str | None):  # type: ignore[no-untyped-def]
            retrieve_calls["n"] += 1
            raise AssertionError("retrieve must not run during composition")

    def guard_provider(settings: object):  # type: ignore[no-untyped-def]
        provider = build_llm_provider(settings)

        def _complete(request: object) -> object:
            complete_calls["n"] += 1
            raise AssertionError("provider.complete must not run during composition")

        provider.complete = _complete  # type: ignore[method-assign]
        return provider

    monkeypatch.setattr(composition, "SemanticRetrievalService", GuardRetrieval)
    monkeypatch.setattr(composition, "build_llm_provider", guard_provider)
    settings = Settings(_env_file=None)
    router = composition.build_session_router(settings)
    captured = router.routes
    turn_routes = [
        route
        for route in captured
        if getattr(route, "path", None) == "/api/v1/session/turn"
    ]
    assert len(turn_routes) == 1
    assert "POST" in turn_routes[0].methods
    assert turn_routes[0].response_model is SessionTurnSuccess
    assert turn_routes[0].body_field is not None
    service = turn_routes[0].endpoint.__closure__
    processor = None
    if service is not None:
        for cell in service:
            value = cell.cell_contents
            if hasattr(value, "_processor"):
                processor = value._processor
    assert isinstance(processor, GovernmentAgentTurnProcessor)
    assert retrieve_calls["n"] == 0
    assert complete_calls["n"] == 0
    assert SpyRedis.commands == []
    assert set(SessionTurnRequest.model_fields) == {
        "request_id",
        "session_id",
        "input_text",
    }
    assert set(SessionTurnSuccess.model_fields) == {
        "session_id",
        "request_id",
        "status",
        "response_text",
        "requires_user_input",
    }


def test_main_registers_session_route_and_preserves_health(monkeypatch) -> None:
    import gov_service_agent.composition as composition

    SpyRedis.commands.clear()
    monkeypatch.setattr(composition, "Redis", SpyRedis)
    import gov_service_agent.main as main

    main = importlib.reload(main)
    paths = {
        (method, route.path)
        for route in main.app.routes
        for method in getattr(route, "methods", set())
    }
    schema = main.app.openapi()
    assert "/api/v1/session/turn" in schema["paths"]
    assert "post" in schema["paths"]["/api/v1/session/turn"]
    assert ("GET", "/health") in paths
    client = TestClient(main.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert SpyRedis.commands == []
