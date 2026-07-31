from fastapi.testclient import TestClient

from backend.src.api.server import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "Brand Guardian AI"}


def test_frontend_routes_are_not_served():
    # server.py deliberately has zero HTML routes — pure JSON API only.
    response = client.get("/")
    assert response.status_code == 404


def test_openapi_schema_loads():
    response = client.get("/openapi.json")
    assert response.status_code == 200
