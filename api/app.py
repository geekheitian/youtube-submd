from __future__ import annotations

from typing import Any, Optional

from config import RuntimeConfig, load_runtime_config

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:
    FastAPI = Any
    Request = Any
    JSONResponse = Any
    _FASTAPI_IMPORT_ERROR = True
else:
    _FASTAPI_IMPORT_ERROR = False


def create_app(config: Optional[RuntimeConfig] = None) -> Any:
    if _FASTAPI_IMPORT_ERROR:
        raise RuntimeError(
            "FastAPI is not installed. Install project dependencies from pyproject.toml first."
        )
    runtime = config or load_runtime_config()

    app = FastAPI(
        title="youtube-submd API MVP",
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.state.runtime_config = runtime

    from api.routes.health import router as health_router

    app.include_router(health_router)

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        from api.errors.responses import ErrorResponse

        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="Internal server error",
                code="internal-error",
                detail=str(exc) if runtime.environment == "development" else None,
            ).model_dump(),
        )

    return app


app = create_app() if not _FASTAPI_IMPORT_ERROR else None
