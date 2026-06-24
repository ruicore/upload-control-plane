from fastapi import FastAPI

from upload_control_plane.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(
        title="Upload Control Plane",
        version="0.1.0",
    )

    @app.get("/healthz", tags=["health"])
    def healthz() -> dict[str, str]:
        return {
            "status": "ok",
            "service": resolved_settings.app_name,
        }

    return app


app = create_app()
