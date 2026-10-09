from fastapi.testclient import TestClient

from haggle_api.main import create_app


def test_healthz_reports_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "api"
    assert isinstance(body["version"], str)


def test_unknown_route_is_404() -> None:
    client = TestClient(create_app())

    assert client.get("/does-not-exist").status_code == 404
