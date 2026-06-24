from fastapi.testclient import TestClient

from upload_control_plane.main import create_app


def test_healthz_returns_service_status() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "upload-control-plane",
    }
