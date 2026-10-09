"""F13-Preview composition activation. No real Redis, database, embedding, or LLM."""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from gov_service_agent.agent.materials_preview import (
    ConfirmedBusinessMaterialsPreviewProcessor,
)
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


def _capture_processor(router: object) -> ConfirmedBusinessMaterialsPreviewProcessor:
    turn_routes = [
        route
        for route in router.routes  # type: ignore[attr-defined]
        if getattr(route, "path", None) == "/api/v1/session/turn"
    ]
    assert len(turn_routes) == 1
    closure = turn_routes[0].endpoint.__closure__
    processor = None
    if closure is not None:
        for cell in closure:
            value = cell.cell_contents
            if hasattr(value, "_processor"):
                processor = value._processor
    assert isinstance(processor, ConfirmedBusinessMaterialsPreviewProcessor)
    return processor


def test_composition_wraps_f12_processor_and_reuses_repository(monkeypatch) -> None:
    """T-F13P-014."""
    import gov_service_agent.composition as composition
    from gov_service_agent.llm.provider import build_llm_provider
    from gov_service_agent.retrieval.service import SemanticRetrievalService
    from gov_service_agent.settings import Settings

    SpyRedis.commands.clear()
    monkeypatch.setattr(composition, "Redis", SpyRedis)
    lookup_calls = {"business": 0, "materials": 0}
    original_business = composition.JsonBusinessRepository.get_business
    original_materials = composition.JsonBusinessRepository.get_materials

    def counting_business(self, business_id: str):  # type: ignore[no-untyped-def]
        lookup_calls["business"] += 1
        return original_business(self, business_id)

    def counting_materials(self, business_id: str, **kwargs: object):  # type: ignore[no-untyped-def]
        lookup_calls["materials"] += 1
        return original_materials(self, business_id, **kwargs)

    monkeypatch.setattr(
        composition.JsonBusinessRepository,
        "get_business",
        counting_business,
    )
    monkeypatch.setattr(
        composition.JsonBusinessRepository,
        "get_materials",
        counting_materials,
    )

    def guard_provider(settings: object):  # type: ignore[no-untyped-def]
        provider = build_llm_provider(settings)

        def _complete(request: object) -> object:
            raise AssertionError("provider.complete must not run during composition")

        provider.complete = _complete  # type: ignore[method-assign]
        return provider

    class GuardRetrieval(SemanticRetrievalService):
        def retrieve(self, query: str | None):  # type: ignore[no-untyped-def]
            raise AssertionError("retrieve must not run during composition")

    monkeypatch.setattr(composition, "build_llm_provider", guard_provider)
    monkeypatch.setattr(composition, "SemanticRetrievalService", GuardRetrieval)
    router = composition.build_session_router(Settings(_env_file=None))
    processor = _capture_processor(router)
    assert isinstance(processor._base_processor, GovernmentAgentTurnProcessor)
    assert (
        processor._business_repository
        is processor._base_processor._business_repository
    )
    assert lookup_calls == {"business": 0, "materials": 0}
    assert SpyRedis.commands == []
    schema = router.routes
    assert any(getattr(route, "path", None) == "/api/v1/session/turn" for route in schema)
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


def test_health_and_public_schema_stay_unchanged(monkeypatch) -> None:
    import gov_service_agent.composition as composition

    SpyRedis.commands.clear()
    monkeypatch.setattr(composition, "Redis", SpyRedis)
    import gov_service_agent.main as main

    main = importlib.reload(main)
    schema = main.app.openapi()
    operation = schema["paths"]["/api/v1/session/turn"]["post"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/SessionTurnSuccess")
    component = schema["components"]["schemas"]["SessionTurnSuccess"]["properties"]
    assert set(component) == {
        "session_id",
        "request_id",
        "status",
        "response_text",
        "requires_user_input",
    }
    client = TestClient(main.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert SpyRedis.commands == []
