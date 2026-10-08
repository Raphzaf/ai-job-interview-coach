"""FastAPI application: JSON API under /api, web UI at /, OpenAPI docs at /docs.

Run with:  uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.dependencies import Container, build_container
from app.api.routes import analysis, documents, health, interview
from app.core.config import Settings, get_settings
from app.core.errors import CoachError
from app.core.logging import get_logger, setup_logging

logger = get_logger(__name__)
STATIC_DIR = Path(__file__).parent / "ui" / "static"


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Load the embedding model/tokenizer once at startup rather than on the first request.
        if getattr(app.state, "container", None) is None:
            app.state.container = build_container(settings)
        pipeline = app.state.container.pipeline
        logger.info("Ready: embeddings=%s, llm=%s", pipeline.embedder.model_name, pipeline.llm_label)
        yield

    app = FastAPI(
        title="AI Job Interview & Application Coach",
        version=__version__,
        description="RAG-based CV/job matching, personalised interview questions and grounded answer feedback.",
        lifespan=lifespan,
    )
    app.state.container = container

    @app.exception_handler(CoachError)
    async def coach_error_handler(_: Request, exc: CoachError) -> JSONResponse:
        # Expected errors: the message is written for end users.
        logger.info("Handled %s: %s", exc.error_code, exc.message)
        return JSONResponse(status_code=exc.status_code, content={"error": exc.error_code, "message": exc.message})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = ", ".join(".".join(str(p) for p in e["loc"][1:]) or "body" for e in exc.errors())
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_request", "message": f"Invalid or missing fields: {fields}.",
                     "details": [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]},
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
        # Full traceback goes to the server log for developers; users get a
        # generic message (no stack traces, paths or configuration leaks).
        logger.exception("Unexpected error")
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "message": "Something went wrong on our side. Please try again."},
        )

    for router in (health.router, documents.router, analysis.router, interview.router):
        app.include_router(router, prefix="/api")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
