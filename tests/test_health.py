from fastapi.testclient import TestClient

from gov_service_agent.main import app


def test_app_importable():
    assert app is not None


def test_health_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
