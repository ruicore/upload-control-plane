from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from upload_control_plane.api.auth import AuthenticatedActor, require_api_key
from upload_control_plane.api.datasets import router as datasets_router
from upload_control_plane.api.devices import router as devices_router
from upload_control_plane.api.errors import (
    ApiError,
    api_error_handler,
    http_error_handler,
    validation_error_handler,
)
from upload_control_plane.api.middleware import request_id_middleware
from upload_control_plane.api.projects import router as projects_router
from upload_control_plane.api.upload_sessions import router as upload_sessions_router
from upload_control_plane.api.upload_tasks import router as upload_tasks_router
from upload_control_plane.config import Settings, get_settings

AUTH_ACTOR = Depends(require_api_key)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(
        title="Upload Control Plane",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.api_cors_allowed_origins,
        allow_credentials=False,
        allow_methods=resolved_settings.api_cors_allowed_methods,
        allow_headers=resolved_settings.api_cors_allowed_headers,
        expose_headers=resolved_settings.api_cors_expose_headers,
    )
    app.middleware("http")(request_id_middleware)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(projects_router)
    app.include_router(datasets_router)
    app.include_router(devices_router)
    app.include_router(upload_tasks_router)
    app.include_router(upload_sessions_router)

    @app.get("/healthz", tags=["health"])
    def healthz() -> dict[str, str]:
        return {
            "status": "ok",
            "service": resolved_settings.app_name,
        }

    @app.get("/internal/auth-smoke", tags=["internal"])
    def auth_smoke(actor: AuthenticatedActor = AUTH_ACTOR) -> dict[str, object]:
        return {
            "authenticated": True,
            "tenant_id": str(actor.tenant_id),
            "api_key_id": str(actor.api_key_id) if actor.api_key_id is not None else None,
            "subject_id": str(actor.subject_id),
            "actor_type": actor.actor_type,
            "scopes": list(actor.scopes),
        }

    return app


app = create_app()
