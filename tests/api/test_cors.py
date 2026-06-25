from fastapi.testclient import TestClient

from upload_control_plane.config import Settings
from upload_control_plane.main import create_app


def test_manual_uploader_origin_preflight_is_allowed() -> None:
    client = TestClient(
        create_app(
            Settings(
                api_cors_allowed_origins=["http://localhost:5173"],
                api_cors_allowed_headers=[
                    "authorization",
                    "content-type",
                    "idempotency-key",
                    "x-request-id",
                ],
            )
        )
    )

    response = client.options(
        "/v1/projects/020500f8-920c-5a49-bf01-0eca416b8ddf/upload-tasks",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "authorization,content-type,idempotency-key,x-request-id"
            ),
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in response.headers["access-control-allow-methods"]
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers
    assert "idempotency-key" in allowed_headers
    assert "x-request-id" in allowed_headers


def test_unconfigured_browser_origin_preflight_is_not_allowed() -> None:
    client = TestClient(create_app(Settings(api_cors_allowed_origins=["http://localhost:5173"])))

    response = client.options(
        "/v1/projects/020500f8-920c-5a49-bf01-0eca416b8ddf/upload-tasks",
        headers={
            "Origin": "https://example.invalid",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
