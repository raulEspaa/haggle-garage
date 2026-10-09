from fastapi.testclient import TestClient

from haggle_api.main import create_app


def test_health_reports_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "api"
    assert isinstance(body["version"], str)


def test_unknown_route_is_404() -> None:
    client = TestClient(create_app())

    assert client.get("/does-not-exist").status_code == 404


def test_no_route_ends_in_z() -> None:
    # Cloud Run's front end reserves some paths ending in "z" (e.g. /healthz) and answers them
    # itself with a Google 404: the request never reaches the container.
    # https://docs.cloud.google.com/run/docs/issues
    paths = [getattr(route, "path", "") for route in create_app().routes]

    assert [p for p in paths if p.rstrip("/").endswith("z")] == []
